"""
Staff API — Chef (Oshpaz) and Courier (Kuryer) specific views.
Both panels use Telegram Mini App and require role-based access.
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from functools import wraps

from orders.models import Order, OrderItem


# ── Role decorator ────────────────────────────────────
def require_role(*roles):
    """
    Superuser yoki ko'rsatilgan rollardan biriga ruxsat beradi.

    DIQQAT: DEV_MODE rol tekshiruvini OCHMAYDI — u autentifikatsiyani
    tekshirishni o'chiradi xolos. Aks holda production'da oshpaz paneli
    har kimga ochiq bo'lib qoladi.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)

            # DEV_MODE + DEBUG: lokal ishlab chiqarishda o'tkazib yuboramiz
            from django.conf import settings as dj_settings
            if getattr(dj_settings, 'DEV_MODE', False) and dj_settings.DEBUG:
                return view_func(request, *args, **kwargs)

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            if request.user.role not in roles:
                return JsonResponse({
                    'error': f'Bu panel faqat {", ".join(roles)} uchun',
                    'role': request.user.role,
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def order_to_dict_full(o):
    """Full order serialization for staff panels."""
    now = timezone.now()
    elapsed = int((now - o.created_at).total_seconds())
    return {
        'id': o.id,
        'status': o.status,
        'status_display': o.get_status_display(),
        'status_icon': o.status_icon,
        'subtotal': int(o.subtotal),
        'delivery_fee': int(o.delivery_fee),
        'total_price': int(o.total_price),
        'payment_method': o.payment_method,
        'payment_display': o.get_payment_method_display(),
        'is_paid': o.is_paid,
        'address': o.address,
        'note': o.note,
        'latitude': o.latitude,
        'longitude': o.longitude,
        'customer_name': o.customer.display_name if o.customer else '—',
        'customer_phone': o.customer.phone or '—',
        'customer_tg_id': o.customer.telegram_id,
        'chef': o.assigned_chef.display_name if o.assigned_chef else None,
        'courier': o.assigned_courier.display_name if o.assigned_courier else None,
        'items': [
            {
                'name': it.menu_item.name,
                'quantity': it.quantity,
                'price': int(it.price),
                'subtotal': int(it.price * it.quantity),
                'weight': getattr(it.menu_item, 'weight', ''),
                'preparation_time': getattr(it.menu_item, 'preparation_time', 10),
            }
            for it in o.items.select_related('menu_item').all()
        ],
        'created_at': o.created_at.strftime('%H:%M'),
        'created_at_iso': o.created_at.isoformat(),
        'elapsed_seconds': elapsed,
        'valid_transitions': Order.VALID_TRANSITIONS.get(o.status, []),
    }


# ══════════════════════════════════════════════════════
# CHEF (OSHPAZ) API
# ══════════════════════════════════════════════════════

@require_role('chef', 'director')
def chef_orders(request):
    """
    GET /api/staff/chef/orders/
    Returns orders grouped by status for the chef panel.
    """
    today = timezone.now().date()

    # New orders waiting to be accepted
    yangi = Order.objects.filter(
        status='yangi'
    ).select_related('customer', 'assigned_chef').prefetch_related('items__menu_item').order_by('created_at')

    # Accepted orders
    qabul = Order.objects.filter(
        status='qabul_qilindi'
    ).select_related('customer', 'assigned_chef').prefetch_related('items__menu_item').order_by('created_at')

    # Being cooked
    pishir = Order.objects.filter(
        status='tayyorlanmoqda'
    ).select_related('customer', 'assigned_chef').prefetch_related('items__menu_item').order_by('created_at')

    # Ready for courier (oshpaz tomonidan tayyor deb belgilangan)
    tayyor = Order.objects.filter(
        status='tayyor'
    ).select_related('customer', 'assigned_chef').prefetch_related('items__menu_item').order_by('-created_at')

    # Today's completed or ready — chef sees all he cooked today
    chef_user = request.user
    if chef_user.is_superuser:
        today_done_qs = Order.objects.filter(
            status__in=['tayyor', 'yolda', 'yetkazildi'],
            created_at__date=today,
        )
        today_done_count = Order.objects.filter(
            status='yetkazildi', created_at__date=today
        ).count()
    else:
        today_done_qs = Order.objects.filter(
            status__in=['tayyor', 'yolda', 'yetkazildi'],
            created_at__date=today,
            assigned_chef=chef_user,
        )
        today_done_count = Order.objects.filter(
            status='yetkazildi', created_at__date=today,
            assigned_chef=chef_user,
        ).count()

    today_done_qs = today_done_qs.select_related('customer').prefetch_related('items__menu_item').order_by('-created_at')

    return JsonResponse({
        'yangi': [order_to_dict_full(o) for o in yangi],
        'qabul_qilindi': [order_to_dict_full(o) for o in qabul],
        'tayyorlanmoqda': [order_to_dict_full(o) for o in pishir],
        'tayyor': [order_to_dict_full(o) for o in today_done_qs],
        'stats': {
            'yangi_count': yangi.count(),
            'active_count': qabul.count() + pishir.count(),
            'tayyor_count': tayyor.count(),
            'today_done': today_done_count,
        },
    })


@csrf_exempt
@require_role('chef', 'director')
def chef_update_status(request, order_id):
    """
    POST /api/staff/chef/orders/<id>/status/
    Chef accepts, starts cooking, or marks ready.
    """
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

    # Assign chef when accepting
    if new_status == 'qabul_qilindi' and not order.assigned_chef:
        if request.user.role == 'chef':
            order.assigned_chef = request.user
        else:
            # Bo'sh oshpazlardan eng kam ishi borini tanlaymiz
            from django.contrib.auth import get_user_model
            User = get_user_model()
            order.assigned_chef = User.objects.filter(
                role='chef', is_active=True
            ).order_by('chef_orders__count', 'id').first()
        order.save(update_fields=['assigned_chef'])

    try:
        if order.status == 'yangi' and new_status == 'tayyorlanmoqda':
            order.transition_to('qabul_qilindi', changed_by=request.user)
        order.transition_to(new_status, changed_by=request.user)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({
        'success': True,
        'order_id': order.id,
        'status': order.status,
        'status_display': order.get_status_display(),
        'chef': order.assigned_chef.display_name if order.assigned_chef else None,
    })


# ══════════════════════════════════════════════════════
# COURIER (KURYER) API
# ══════════════════════════════════════════════════════

@require_role('courier', 'director')
def courier_orders(request):
    """
    GET /api/staff/courier/orders/
    Returns orders for the courier panel.
    """
    today = timezone.now().date()
    courier_user = request.user

    # Available for pickup (tayyor, not yet assigned or not assigned to someone else)
    available = Order.objects.filter(
        status='tayyor'
    ).select_related('customer', 'assigned_courier', 'assigned_chef').prefetch_related('items__menu_item').order_by('created_at')

    # My active deliveries (yolda and assigned to me)
    if courier_user.is_superuser:
        my_active = Order.objects.filter(status='yolda')
    else:
        my_active = Order.objects.filter(
            status='yolda',
            assigned_courier=courier_user,
        )
    my_active = my_active.select_related('customer', 'assigned_courier').prefetch_related('items__menu_item').order_by('created_at')

    # Completed today by me
    if courier_user.is_superuser:
        today_done = Order.objects.filter(status='yetkazildi', created_at__date=today)
    else:
        today_done = Order.objects.filter(
            status='yetkazildi',
            assigned_courier=courier_user,
            created_at__date=today,
        )
    today_done = today_done.select_related('customer').prefetch_related('items__menu_item').order_by('-created_at')

    return JsonResponse({
        'available': [order_to_dict_full(o) for o in available],
        'my_active': [order_to_dict_full(o) for o in my_active],
        'today_done': [order_to_dict_full(o) for o in today_done],
        'stats': {
            'available_count': available.count(),
            'active_count': my_active.count(),
            'today_done_count': today_done.count(),
        },
    })


@csrf_exempt
@require_role('courier', 'director')
def courier_update_status(request, order_id):
    """
    POST /api/staff/courier/orders/<id>/status/
    Courier picks up or delivers an order.
    """
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

    # Assign courier when picking up
    if new_status == 'yolda' and not order.assigned_courier:
        order.assigned_courier = request.user
        order.save(update_fields=['assigned_courier'])

    try:
        order.transition_to(new_status, changed_by=request.user)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({
        'success': True,
        'order_id': order.id,
        'status': order.status,
        'status_display': order.get_status_display(),
        'courier': order.assigned_courier.display_name if order.assigned_courier else None,
    })


@csrf_exempt
@require_role('courier', 'director')
def courier_location(request, order_id):
    """
    POST /api/staff/courier/orders/<id>/location/
    Body: { latitude, longitude, heading, accuracy }
    Kuryer joylashuvini saqlaydi va mijozga yuboradi.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST talab qilinadi'}, status=405)

    try:
        body = json.loads(request.body)
        lat = float(body.get('latitude'))
        lng = float(body.get('longitude'))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': "Noto'g'ri koordinatalar"}, status=400)

    # O'zbekiston chegaralarida bo'lishi kerak (juda yaxshi himoya)
    if not (37.2 <= lat <= 45.6 and 56.0 <= lng <= 73.2):
        return JsonResponse({'error': 'Koordinatalar noto\'g\'ri'}, status=400)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Buyurtma topilmadi'}, status=404)

    if order.status != 'yolda':
        return JsonResponse({
            'error': 'Joylashuv yuborish uchun buyurtma "yo\'lda" holatida bo\'lishi kerak'
        }, status=400)

    from orders.models import CourierLocation
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    location, _ = CourierLocation.objects.update_or_create(
        order=order,
        defaults={
            'courier': request.user if request.user.role == 'courier' else order.assigned_courier,
            'latitude': lat,
            'longitude': lng,
            'heading': body.get('heading'),
            'accuracy': body.get('accuracy'),
        },
    )

    # Mijozga real-time yuborish
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'order_track_{order_id}',
            {'type': 'location_message', 'lat': lat, 'lng': lng},
        )
    except Exception as e:
        print(f'Location broadcast error: {e}')

    return JsonResponse({'success': True, 'lat': lat, 'lng': lng})
