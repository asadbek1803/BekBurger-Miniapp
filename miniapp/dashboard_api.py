"""
Dashboard API views for the Director panel.
All views require director role or superuser.
"""
import json
import re
from datetime import date, timedelta
from urllib.parse import urlparse

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Q

from accounts.models import AppSettings, DEFAULT_SETTINGS
from accounts.settings_service import public_config
from menu.models import Category, MenuItem, Banner
from orders.models import Order, OrderItem

User = get_user_model()


def require_admin(view_func):
    """Decorator: require authenticated director/superuser."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)
        if not (request.user.is_superuser or request.user.role == 'director'):
            return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Stats ─────────────────────────────────────────────
@require_GET
@require_admin
def dashboard_stats(request):
    """GET /api/dashboard/stats/ — today's overview statistics."""
    today = timezone.now().date()
    week_ago = today - timedelta(days=6)

    today_orders = Order.objects.filter(created_at__date=today)
    total_orders_today = today_orders.count()
    revenue_today = today_orders.filter(
        status='yetkazildi'
    ).aggregate(total=Sum('total_price'))['total'] or 0

    pending = Order.objects.filter(status__in=['yangi', 'qabul_qilindi']).count()
    in_progress = Order.objects.filter(status__in=['tayyorlanmoqda', 'tayyor', 'yolda']).count()
    delivered_today = today_orders.filter(status='yetkazildi').count()

    # Last 7 days chart data
    chart_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Order.objects.filter(created_at__date=day).count()
        rev = Order.objects.filter(
            created_at__date=day, status='yetkazildi'
        ).aggregate(total=Sum('total_price'))['total'] or 0
        chart_data.append({
            'date': day.strftime('%d/%m'),
            'orders': count,
            'revenue': int(rev),
        })

    # Active couriers
    active_couriers = User.objects.filter(role='courier', is_active=True).count()

    # Recent orders (last 10)
    recent = Order.objects.select_related('customer').prefetch_related(
        'items__menu_item'
    ).order_by('-created_at')[:10]

    return JsonResponse({
        'today': {
            'orders': total_orders_today,
            'revenue': int(revenue_today),
            'pending': pending,
            'in_progress': in_progress,
            'delivered': delivered_today,
        },
        'active_couriers': active_couriers,
        'chart': chart_data,
        'recent_orders': [
            {
                'id': o.id,
                'customer': o.customer.display_name,
                'status': o.status,
                'status_display': o.get_status_display(),
                'status_icon': o.status_icon,
                'total': int(o.total_price),
                'items_count': sum(i.quantity for i in o.items.all()),
                'created_at': o.created_at.strftime('%H:%M'),
            }
            for o in recent
        ],
    })


# ── Orders ────────────────────────────────────────────
@require_GET
@require_admin
def dashboard_orders(request):
    """GET /api/dashboard/orders/?status=all&date=today"""
    status_filter = request.GET.get('status', 'all')
    date_filter = request.GET.get('date', 'today')

    qs = Order.objects.select_related(
        'customer', 'assigned_chef', 'assigned_courier'
    ).prefetch_related('items__menu_item').order_by('-created_at')

    if status_filter != 'all':
        qs = qs.filter(status=status_filter)

    if date_filter == 'today':
        qs = qs.filter(created_at__date=timezone.now().date())
    elif date_filter == 'week':
        qs = qs.filter(created_at__date__gte=timezone.now().date() - timedelta(days=7))

    orders = []
    for o in qs[:100]:
        orders.append({
            'id': o.id,
            'customer_name': o.customer.display_name,
            'customer_phone': o.customer.phone or '—',
            'status': o.status,
            'status_display': o.get_status_display(),
            'status_icon': o.status_icon,
            'total': int(o.total_price),
            'address': o.address,
            'note': o.note,
            'chef': o.assigned_chef.display_name if o.assigned_chef else None,
            'courier': o.assigned_courier.display_name if o.assigned_courier else None,
            'items': [item.to_dict() for item in o.items.all()],
            'created_at': o.created_at.strftime('%d.%m.%Y %H:%M'),
            'valid_transitions': Order.VALID_TRANSITIONS.get(o.status, []),
        })

    return JsonResponse({'orders': orders})


@csrf_exempt
@require_admin
def dashboard_order_status(request, order_id):
    """POST /api/dashboard/orders/<id>/status/ — {status: 'qabul_qilindi'}"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST talab qilinadi'}, status=405)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Buyurtma topilmadi'}, status=404)

    try:
        body = json.loads(request.body)
        new_status = body.get('status')
    except json.JSONDecodeError:
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    try:
        order.transition_to(new_status, changed_by=request.user)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({
        'success': True,
        'order_id': order.id,
        'status': order.status,
        'status_display': order.get_status_display(),
    })


# ── Menu Management ───────────────────────────────────
@csrf_exempt
@require_admin
def dashboard_menu_items(request):
    """GET/POST /api/dashboard/menu/items/"""
    if request.method == 'GET':
        items = MenuItem.objects.select_related('category').order_by('category__order', 'order')
        return JsonResponse({
            'items': [item.to_dict() for item in items],
            'categories': list(Category.objects.filter(is_active=True).values('id', 'name', 'icon')),
        })

    elif request.method == 'POST':
        try:
            # Handle both JSON and form data
            if request.content_type and 'application/json' in request.content_type:
                body = json.loads(request.body)
            else:
                body = request.POST.dict()

            category_id = body.get('category_id') or body.get('category')
            name = body.get('name', '').strip()
            price = body.get('price', 0)
            description = body.get('description', '')
            is_available = str(body.get('is_available', 'true')).lower() in ('true', '1', 'on')
            is_popular = str(body.get('is_popular', 'false')).lower() in ('true', '1', 'on')
            preparation_time = int(body.get('preparation_time', 10))
            order_num = int(body.get('order', 0))

            if not name:
                return JsonResponse({'error': 'Mahsulot nomi kiritilmagan'}, status=400)
            if not category_id:
                return JsonResponse({'error': 'Kategoriya tanlanmagan'}, status=400)

            category = Category.objects.get(id=category_id)
            item = MenuItem.objects.create(
                category=category,
                name=name,
                description=description,
                price=int(price),
                is_available=is_available,
                is_popular=is_popular,
                preparation_time=preparation_time,
                order=order_num,
            )

            # Handle image upload
            if 'image' in request.FILES:
                item.image = request.FILES['image']
                item.save(update_fields=['image'])

            return JsonResponse({'success': True, 'item': item.to_dict()}, status=201)

        except Category.DoesNotExist:
            return JsonResponse({'error': 'Kategoriya topilmadi'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@require_admin
def dashboard_menu_item_detail(request, item_id):
    """PUT/DELETE /api/dashboard/menu/items/<id>/"""
    try:
        item = MenuItem.objects.select_related('category').get(id=item_id)
    except MenuItem.DoesNotExist:
        return JsonResponse({'error': 'Mahsulot topilmadi'}, status=404)

    if request.method in ('PUT', 'PATCH', 'POST'):
        try:
            if request.content_type and 'application/json' in request.content_type:
                body = json.loads(request.body)
            else:
                body = request.POST.dict()

            if 'name' in body: item.name = body['name']
            if 'description' in body: item.description = body['description']
            if 'price' in body: item.price = int(body['price'])
            if 'is_available' in body:
                item.is_available = str(body['is_available']).lower() in ('true', '1', 'on')
            if 'is_popular' in body:
                item.is_popular = str(body['is_popular']).lower() in ('true', '1', 'on')
            if 'preparation_time' in body:
                item.preparation_time = int(body['preparation_time'])
            if 'order' in body:
                item.order = int(body['order'])
            if 'category_id' in body or 'category' in body:
                cat_id = body.get('category_id') or body.get('category')
                item.category = Category.objects.get(id=cat_id)
            if 'image' in request.FILES:
                item.image = request.FILES['image']

            item.save()
            return JsonResponse({'success': True, 'item': item.to_dict()})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    elif request.method == 'DELETE':
        item_name = item.name
        item.delete()
        return JsonResponse({'success': True, 'message': f'"{item_name}" o\'chirildi'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ── Categories ────────────────────────────────────────
@csrf_exempt
@require_admin
def dashboard_categories(request):
    """GET/POST /api/dashboard/menu/categories/"""
    if request.method == 'GET':
        cats = Category.objects.annotate(item_count=Count('items')).order_by('order')
        return JsonResponse({'categories': [
            {'id': c.id, 'name': c.name, 'icon': c.icon, 'order': c.order,
             'is_active': c.is_active, 'item_count': c.item_count}
            for c in cats
        ]})

    elif request.method == 'POST':
        try:
            if request.content_type and 'application/json' in request.content_type:
                body = json.loads(request.body)
            else:
                body = request.POST.dict()
                
            name = (body.get('name') or '').strip()
            if not name:
                return JsonResponse({'error': 'Kategoriya nomi kiritilmagan'}, status=400)
            if len(name) > 100:
                return JsonResponse({'error': 'Kategoriya nomi juda uzun (100 belgidan ko\'p)'}, status=400)

            cat = Category.objects.create(
                name=name[:100],
                icon=(body.get('icon') or '🍽️')[:8],
                order=int(body.get('order') or 0),
                is_active=bool(body.get('is_active', True)),
            )
            
            if 'image' in request.FILES:
                cat.image = request.FILES['image']
                cat.save(update_fields=['image'])
                
            return JsonResponse({'success': True, 'category': {'id': cat.id, 'name': cat.name, 'icon': cat.icon}}, status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@require_admin
def dashboard_category_detail(request, cat_id):
    """PUT/DELETE /api/dashboard/menu/categories/<id>/"""
    try:
        cat = Category.objects.get(id=cat_id)
    except Category.DoesNotExist:
        return JsonResponse({'error': 'Kategoriya topilmadi'}, status=404)

    if request.method in ('PUT', 'PATCH', 'POST'):
        try:
            if request.content_type and 'application/json' in request.content_type:
                body = json.loads(request.body)
            else:
                body = request.POST.dict()
                
            if 'name' in body:
                cat.name = body['name'].strip()[:100]
                if not cat.name:
                    return JsonResponse({'error': 'Kategoriya nomi kiritilmagan'}, status=400)
            if 'icon' in body: cat.icon = body['icon'][:8]
            if 'order' in body: cat.order = int(body['order'] or 0)
            if 'is_active' in body: cat.is_active = str(body['is_active']).lower() in ('true', '1', 'on')
            
            if 'image' in request.FILES:
                cat.image = request.FILES['image']
                
            cat.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    elif request.method == 'DELETE':
        if cat.items.exists():
            return JsonResponse({'error': 'Bu kategoriyada mahsulotlar bor, avval ularni o\'chiring'}, status=400)
        cat.delete()
        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ── Users / Staff ─────────────────────────────────────
@csrf_exempt
@require_admin
def dashboard_users(request):
    """GET/POST /api/dashboard/users/"""
    if request.method == 'GET':
        role = request.GET.get('role', 'all')
        qs = User.objects.all().order_by('role', 'first_name')
        if role != 'all':
            qs = qs.filter(role=role)

        users = []
        for u in qs:
            orders_count = 0
            if u.role == 'customer':
                orders_count = u.orders.count()
            elif u.role == 'chef':
                orders_count = u.chef_orders.count()
            elif u.role == 'courier':
                orders_count = u.courier_orders.count()

            users.append({
                'id': u.id,
                'name': u.display_name,
                'username': u.telegram_username or u.username,
                'telegram_id': u.telegram_id,
                'role': u.role,
                'role_display': u.get_role_display(),
                'phone': u.phone or '—',
                'is_active': u.is_active,
                'orders_count': orders_count,
                'joined': u.created_at.strftime('%d.%m.%Y'),
            })
        return JsonResponse({'users': users})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            telegram_id = body.get('telegram_id')
            first_name = body.get('first_name', '').strip()
            last_name = body.get('last_name', '').strip()
            role = body.get('role', 'customer')
            phone = body.get('phone', '').strip()

            if not telegram_id:
                return JsonResponse({'error': 'Telegram ID kiritilmagan'}, status=400)
            if not first_name:
                return JsonResponse({'error': 'Ism kiritilmagan'}, status=400)

            if User.objects.filter(telegram_id=telegram_id).exists():
                return JsonResponse({'error': 'Bu Telegram ID allaqachon ro\'yxatda'}, status=400)

            user = User.objects.create_user(
                username=f'tg_{telegram_id}',
                telegram_id=int(telegram_id),
                first_name=first_name,
                last_name=last_name,
                role=role,
                phone=phone,
            )
            return JsonResponse({
                'success': True,
                'user': {'id': user.id, 'name': user.display_name, 'role': user.role}
            }, status=201)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@require_admin
def dashboard_user_detail(request, user_id):
    """PUT/DELETE /api/dashboard/users/<id>/"""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Foydalanuvchi topilmadi'}, status=404)

    if request.method in ('PUT', 'PATCH'):
        try:
            body = json.loads(request.body)
            if 'first_name' in body: user.first_name = body['first_name']
            if 'last_name' in body: user.last_name = body['last_name']
            if 'role' in body: user.role = body['role']
            if 'phone' in body: user.phone = body['phone']
            if 'is_active' in body: user.is_active = bool(body['is_active'])
            user.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    elif request.method == 'DELETE':
        user.is_active = False
        user.save(update_fields=['is_active'])
        return JsonResponse({'success': True, 'message': 'Foydalanuvchi o\'chirildi (deaktivatsiya)'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ── Settings ──────────────────────────────────────────
@csrf_exempt
@require_admin
def dashboard_settings(request):
    """GET/POST /api/dashboard/settings/"""
    if request.method == 'GET':
        # Yangi qo'shilgan default sozlamalarni avtomatik yaratish
        AppSettings.seed_defaults()

        settings_data = []
        for s in AppSettings.objects.all().order_by('key'):
            # Parol turidagi qiymatni yashiramiz (lekin saqlashda saqlaymiz)
            display_val = s.value
            if s.setting_type == 'password' and s.value:
                display_val = s.value[:8] + '...' + s.value[-4:] if len(s.value) > 12 else '***'

            settings_data.append({
                'key': s.key,
                'value': s.value,
                'display_value': display_val,
                'label': s.label,
                'description': s.description,
                'setting_type': s.setting_type,
                'updated_at': s.updated_at.strftime('%d.%m.%Y %H:%M'),
            })

        return JsonResponse({
            'settings': settings_data,
            'config': public_config(),
        })

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

        errors = []
        updated = []

        for setting in AppSettings.objects.all():
            key = setting.key
            if key not in body:
                continue

            value = body[key]

            # ── Turga mos tekshirish ──
            if setting.setting_type == 'boolean':
                value = 'True' if _to_bool(value) else 'False'

            elif setting.setting_type == 'number':
                try:
                    number = float(str(value).strip())
                except (TypeError, ValueError):
                    errors.append(f'{setting.label}: raqam kiriting')
                    continue
                if number < 0:
                    errors.append(f'{setting.label}: manfiy bo\'lmaydi')
                    continue
                value = str(int(number))

            elif setting.setting_type == 'password':
                # Bo'sh qoldirilsa — eski token saqlanadi
                if not str(value).strip():
                    continue
                value = str(value).strip()

            else:
                value = str(value).strip()

            # Bo'sh qiymatli majburiy sozlamalarni bo'sh qoldirishga ruxsat bermaymiz
            if not value and key == 'restaurant_name':
                errors.append('Restoran nomi bo\'sh bo\'lmaydi')
                continue

            # Uzunlik cheklovi — har sahifada ko'rsatiladigan matn
            limit = SETTING_MAX_LENGTH.get(key)
            if limit and len(value) > limit:
                errors.append(f'{setting.label}: juda uzun ({limit} belgidan ko\'p)')
                continue

            if value != setting.value:
                setting.value = value
                setting.save(update_fields=['value', 'updated_at'])
                updated.append(key)

        if errors:
            return JsonResponse({'error': '; '.join(errors), 'updated': updated}, status=400)

        # Frontend'ni darhol yangilashga undash
        try:
            from orders.broadcast import broadcast_settings_update
            broadcast_settings_update()
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'updated': updated,
            'config': public_config(),
            'message': f'{len(updated)} ta sozlama saqlandi',
        })

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ── Banners ───────────────────────────────────────────
# Har bir sozlama uchun ruxsat etilgan maksimal uzunlik.
# Maqsad: xotira/DB va render xarajatidan himoya qilish.
SETTING_MAX_LENGTH = {
    'restaurant_name': 100,
    'app_tagline': 200,
    'restaurant_address': 300,
    'currency': 10,
    'working_hours': 50,
    'phone': 30,
    'telegram_miniapp_url': 300,
    'telegram_bot_token': 200,
    'telegram_bot_chat_id': 30,
}


def _parse_body(request):
    """JSON yoki form-data'ni bir xil dict ko'rinishida qaytaradi."""
    if request.POST:
        return request.POST.dict()
    if not request.body:
        return {}
    if request.content_type and 'application/json' in request.content_type:
        return json.loads(request.body)
    return {}


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('true', '1', 'on', 'yes', 'ha')


HEX_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')
BANNER_LAYOUTS = {c[0] for c in Banner.LAYOUT_CHOICES}
BANNER_ACTIONS = {c[0] for c in Banner.ACTION_CHOICES}


def _clean_color(value, fallback):
    """Rang qiymatini tekshiradi (CSS injection himoyasi)."""
    value = (value or '').strip()
    return value if HEX_RE.match(value) else fallback


def _clean_choice(value, allowed, fallback):
    value = (value or '').strip()
    return value if value in allowed else fallback


def _clean_delay(value):
    """Autoplay kechikishini 0..60 oralig'ida ushlab turadi (0 = umumiy sozlama)."""
    try:
        return max(0, min(60, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def _clean_button_value(value, action):
    """
    Tugma qiymatini tozalaydi.

    `open_url` banner tugmasi mijoz ilovasida `window.open(value, '_blank')`
    orqali ochiladi. `javascript:` / `data:` shema bilan XSS va
    phishing imkoniyati tug'iladi, shuning uchun faqat http(s) qabul qilinadi.
    Boshqa amallarda qiymat bo'sh qoldiriladi.
    """
    value = (value or '').strip()
    if action != 'open_url':
        return ''
    if not value:
        return ''
    # "tel:+998..." kabi qiymatlar ham bo'lishi mumkin
    if value.startswith('tel:'):
        return value[:300]
    try:
        parsed = urlparse(value)
    except ValueError:
        return ''
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return ''
    return value[:300]


@csrf_exempt
@require_admin
def dashboard_banners(request):
    """GET/POST /api/dashboard/banners/"""
    if request.method == 'GET':
        from accounts import settings_service
        default_interval = settings_service.banner_interval()
        banners = Banner.objects.all().order_by('order', '-created_at')
        return JsonResponse({'banners': [
            {
                'id': b.id,
                'title': b.title,
                'subtitle': b.subtitle,
                'label': b.label,
                'image_url': b.image_url,
                'gradient': b.gradient,
                'color_start': b.color_start,
                'color_end': b.color_end,
                'text_color': b.text_color,
                'layout': b.layout,
                'button_text': b.button_text,
                'button_action': b.button_action,
                'button_value': b.button_value,
                'autoplay_delay': b.autoplay_delay,
                'order': b.order,
                'is_active': b.is_active,
                'created_at': b.created_at.strftime('%d.%m.%Y'),
            }
            for b in banners
        ]})

    elif request.method == 'POST':
        try:
            body = _parse_body(request)

            title = (body.get('title') or '').strip()
            if not title:
                return JsonResponse({'error': 'Sarlavha kiritilmagan'}, status=400)

            banner = Banner.objects.create(
                title=title,
                subtitle=body.get('subtitle', ''),
                label=body.get('label') or '🔥 BUGUNGI TAVSIYA',
                color_start=_clean_color(body.get('color_start'), '#E63946'),
                color_end=_clean_color(body.get('color_end'), '#F4A261'),
                text_color=_clean_color(body.get('text_color'), '#FFFFFF'),
                layout=_clean_choice(body.get('layout'), BANNER_LAYOUTS, 'image_right'),
                button_text=body.get('button_text', '')[:50],
                button_action=_clean_choice(body.get('button_action'), BANNER_ACTIONS, 'none'),
                button_value=_clean_button_value(body.get('button_value'),
                                                  _clean_choice(body.get('button_action'),
                                                                BANNER_ACTIONS, 'none')),
                order=int(body.get('order') or 0),
                autoplay_delay=_clean_delay(body.get('autoplay_delay')),
                is_active=_to_bool(body.get('is_active'), True),
            )
            if 'image' in request.FILES:
                banner.image = request.FILES['image']
                banner.save(update_fields=['image'])

            _notify_menu_update()
            return JsonResponse({'success': True, 'banner': {
                'id': banner.id, 'title': banner.title, 'image_url': banner.image_url,
                'is_active': banner.is_active, 'order': banner.order,
            }}, status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@require_admin
def dashboard_banner_detail(request, banner_id):
    """POST/PUT/DELETE /api/dashboard/banners/<id>/"""
    try:
        banner = Banner.objects.get(id=banner_id)
    except Banner.DoesNotExist:
        return JsonResponse({'error': 'Banner topilmadi'}, status=404)

    if request.method in ('PUT', 'PATCH', 'POST'):
        try:
            body = _parse_body(request)

            if 'title' in body: banner.title = body['title'][:100]
            if 'subtitle' in body: banner.subtitle = body['subtitle'][:200]
            if 'label' in body: banner.label = body['label'][:50]
            if 'color_start' in body: banner.color_start = _clean_color(body['color_start'], banner.color_start)
            if 'color_end' in body: banner.color_end = _clean_color(body['color_end'], banner.color_end)
            if 'text_color' in body: banner.text_color = _clean_color(body['text_color'], banner.text_color)
            if 'layout' in body: banner.layout = _clean_choice(body['layout'], BANNER_LAYOUTS, banner.layout)
            if 'button_text' in body: banner.button_text = body['button_text'][:50]
            if 'button_action' in body: banner.button_action = _clean_choice(body['button_action'], BANNER_ACTIONS, banner.button_action)
            if 'button_value' in body: banner.button_value = _clean_button_value(body['button_value'], banner.button_action)
            elif 'button_action' in body and banner.button_action != 'open_url':
                # Amal o'zgarganda eski havola qolmasin
                banner.button_value = ''
            if 'autoplay_delay' in body: banner.autoplay_delay = _clean_delay(body['autoplay_delay'])
            if 'order' in body: banner.order = int(body['order'] or 0)
            if 'is_active' in body: banner.is_active = _to_bool(body['is_active'], True)
            if 'image' in request.FILES: banner.image = request.FILES['image']

            banner.save()
            _notify_menu_update()
            return JsonResponse({'success': True, 'banner': {
                'id': banner.id, 'title': banner.title, 'image_url': banner.image_url,
                'is_active': banner.is_active, 'order': banner.order,
            }})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    elif request.method == 'DELETE':
        title = banner.title
        banner.delete()
        _notify_menu_update()
        return JsonResponse({'success': True, 'message': f'"{title}" banneri o\'chirildi'})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _notify_menu_update():
    """Mijoz ilovasini menyu/banner o'zgarganini bilishga undaydi."""
    try:
        from orders.broadcast import broadcast_menu_update
        broadcast_menu_update()
    except Exception:
        pass


# ── Reviews ───────────────────────────────────────────
@require_GET
@require_admin
def dashboard_reviews(request):
    """GET /api/dashboard/reviews/ — mijoz reytinglari va izohlari."""
    from orders.models import Order
    orders = Order.objects.exclude(rating=None).select_related('customer').order_by('-updated_at')

    reviews = [{
        'order_id': o.id,
        'customer': o.customer.display_name,
        'rating': o.rating,
        'review': o.review,
        'created_at': o.updated_at.strftime('%d.%m.%Y %H:%M'),
    } for o in orders[:100]]

    rated = list(orders.values_list('rating', flat=True))
    avg = round(sum(rated) / len(rated), 1) if rated else 0

    return JsonResponse({
        'reviews': reviews,
        'stats': {'total': len(rated), 'average': avg},
    })
