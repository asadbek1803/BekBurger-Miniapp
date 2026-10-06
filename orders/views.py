"""
Cart & Order API views.

Xavfsizlik: savatda FAQAT mahsulot id va miqdor saqlanadi.
Narx serverda ma'lumotlar bazadan olinadi — mijoz narxini
o'zgartirib yubora olmaydi.
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction

from menu.models import MenuItem
from .models import Order, OrderItem, OrderStatusHistory

CART_SESSION_KEY = 'bekburger_cart'

# ── Cart helpers ──────────────────────────────────────
def get_cart(request):
    """Savatni session'dan oladi (har doim dict)."""
    cart = request.session.get(CART_SESSION_KEY)
    return cart if isinstance(cart, dict) else {}


def save_cart(request, cart):
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def build_cart_response(cart):
    """
    Savatni DB ma'lumotlari asosida qayta hisoblaydi va to'liq javob qaytaradi.

    Bu funksiya narx manbasini YAGONA database'ga bog'laydi —
    session ichidagi narxlarga ishonilmaydi.
    """
    ids = []
    for raw_id in cart.keys():
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    items = {mi.id: mi for mi in MenuItem.objects.filter(id__in=ids).select_related('category')}

    result = []
    subtotal = 0
    count = 0
    changed = False

    for raw_id, data in list(cart.items()):
        menu_item = items.get(int(raw_id)) if str(raw_id).lstrip('-').isdigit() else None

        # Mahsulot o'chirilgan yoki mavjud emas — savatdan chiqaramiz
        if menu_item is None or not menu_item.is_available:
            cart.pop(raw_id, None)
            changed = True
            continue

        try:
            qty = max(1, int(data.get('quantity', 1)))
        except (TypeError, ValueError):
            qty = 1

        price = int(menu_item.price)
        line_total = price * qty

        result.append({
            'id': menu_item.id,
            'name': menu_item.name,
            'price': price,
            'quantity': qty,
            'subtotal': line_total,
            'image_url': menu_item.image_url,
            'is_available': menu_item.is_available,
        })
        subtotal += line_total
        count += qty

        # Narx yoki miqdor o'zgargan bo'lsa — session'ni yangilaymiz
        if data.get('price') != price or data.get('quantity') != qty:
            changed = True

    if changed:
        for entry in result:
            cart[str(entry['id'])] = {'quantity': entry['quantity']}

    return result, subtotal, count


def delivery_fee_for(subtotal: int) -> int:
    """Yetkazib berish narxi — bepul yetkazib berish chegarasini hisobga oladi."""
    from accounts import settings_service
    free_from = settings_service.free_delivery_from()
    if free_from and subtotal >= free_from:
        return 0
    return settings_service.delivery_fee()


def cart_payload(request):
    """Frontend'ga yuboriladigan to'liq savat javobi."""
    cart = get_cart(request)
    items, subtotal, count = build_cart_response(cart)
    save_cart(request, cart)  # tozalangan cartni saqlash

    fee = delivery_fee_for(subtotal) if count else 0
    return {
        'items': items,
        'subtotal': subtotal,
        'delivery_fee': fee,
        'total': subtotal + fee,
        'count': count,
    }


# ── Cart views ────────────────────────────────────────
@require_GET
def cart_view(request):
    """GET /api/cart/ — savat mazmuni (narxlar DB dan)."""
    return JsonResponse(cart_payload(request))


@csrf_exempt
@require_POST
def cart_add(request):
    """POST /api/cart/add/ — {item_id, quantity}"""
    try:
        body = json.loads(request.body)
        item_id = int(body.get('item_id'))
        quantity = int(body.get('quantity', 1))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    if quantity < 1:
        return JsonResponse({'error': 'Miqdor 1 dan kam bo\'lishi mumkin emas'}, status=400)

    try:
        menu_item = MenuItem.objects.select_related('category').get(
            id=item_id, is_available=True
        )
    except MenuItem.DoesNotExist:
        return JsonResponse({'error': 'Mahsulot topilmadi yoki hozircha mavjud emas'}, status=404)

    cart = get_cart(request)
    key = str(menu_item.id)
    current = cart.get(key, {}).get('quantity', 0)
    cart[key] = {'quantity': current + quantity}
    save_cart(request, cart)

    return JsonResponse({'success': True, **cart_payload(request)})


@csrf_exempt
@require_POST
def cart_update(request):
    """POST /api/cart/update/ — {item_id, quantity}"""
    try:
        body = json.loads(request.body)
        item_id = int(body.get('item_id'))
        quantity = int(body.get('quantity', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    cart = get_cart(request)
    key = str(item_id)

    if quantity <= 0:
        cart.pop(key, None)
    elif key in cart:
        cart[key] = {'quantity': quantity}
    else:
        return JsonResponse({'error': 'Mahsulot savatda yo\'q'}, status=404)

    save_cart(request, cart)
    return JsonResponse({'success': True, **cart_payload(request)})


@csrf_exempt
@require_POST
def cart_remove(request):
    """POST /api/cart/remove/ — {item_id}"""
    try:
        body = json.loads(request.body)
        item_id = int(body.get('item_id'))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    cart = get_cart(request)
    cart.pop(str(item_id), None)
    save_cart(request, cart)
    return JsonResponse({'success': True, **cart_payload(request)})


@csrf_exempt
@require_POST
def cart_clear(request):
    """POST /api/cart/clear/ — savatni tozalash."""
    save_cart(request, {})
    return JsonResponse({'success': True, 'items': [], 'subtotal': 0,
                         'delivery_fee': 0, 'total': 0, 'count': 0})


# ── Order views ───────────────────────────────────────
@csrf_exempt
@require_POST
@transaction.atomic
def create_order(request):
    """
    POST /api/orders/create/
    Body: { address, note, latitude, longitude, payment_method }
    Narxlar FAQAT serverda hisoblanadi.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)

    cart = get_cart(request)
    if not cart:
        return JsonResponse({'error': 'Savat bo\'sh'}, status=400)

    try:
        body = json.loads(request.body)
        address = (body.get('address') or '').strip()
        note = (body.get('note') or '').strip()
        latitude = body.get('latitude')
        longitude = body.get('longitude')
        payment_method = body.get('payment_method') or 'naqd'
    except json.JSONDecodeError:
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    if not address:
        return JsonResponse({'error': 'Manzilni kiriting'}, status=400)

    if payment_method not in dict(Order.PAYMENT_CHOICES):
        return JsonResponse({'error': 'Noto\'g\'ri to\'lov turi'}, status=400)

    # ── Ish vaqti tekshiruvi ──
    from accounts import settings_service
    if not settings_service.is_open_now():
        return JsonResponse({
            'error': f'Hozir restoran yopiq. Ish vaqti: {settings_service.working_hours()}'
        }, status=400)

    # ── Narxlar serverda hisoblanadi ──
    items, subtotal, count = build_cart_response(cart)
    if not items:
        save_cart(request, {})
        return JsonResponse({'error': 'Savatdagi mahsulotlar endi mavjud emas'}, status=400)

    # ── Minimal summa tekshiruvi ──
    min_amount = settings_service.min_order_amount()
    if min_amount and subtotal < min_amount:
        return JsonResponse({
            'error': 'Minimal buyurtma summasi: {} {}'.format(
                f'{min_amount:,}'.replace(',', ' '),
                settings_service.get('currency', "so'm"),
            ),
        }, status=400)

    fee = delivery_fee_for(subtotal)
    total = subtotal + fee

    order = Order.objects.create(
        customer=request.user,
        status='yangi',
        subtotal=subtotal,
        delivery_fee=fee,
        total_price=total,
        payment_method=payment_method,
        address=address,
        note=note,
        latitude=latitude,
        longitude=longitude,
    )

    OrderItem.objects.bulk_create([
        OrderItem(
            order=order,
            menu_item_id=entry['id'],
            quantity=entry['quantity'],
            price=entry['price'],
        )
        for entry in items
    ])

    OrderStatusHistory.objects.create(
        order=order, old_status='', new_status='yangi',
        changed_by=request.user, note='Buyurtma yaratildi',
    )

    save_cart(request, {})

    # Yangi buyurtmani oshpaz/kuryer panellari darhol ko'rsin
    try:
        from .broadcast import broadcast_order_update
        broadcast_order_update(order)
    except Exception:
        pass

    # Avtomatik kuryer belgilash
    if settings_service.get_bool('auto_assign_courier', False):
        _auto_assign_courier(order)

    return JsonResponse({
        'success': True,
        'order': {
            'id': order.id,
            'status': order.status,
            'status_display': order.get_status_display(),
            'subtotal': int(order.subtotal),
            'delivery_fee': int(order.delivery_fee),
            'total_price': int(order.total_price),
            'payment_display': order.get_payment_method_display(),
            'eta_minutes': order.eta_minutes,
            'address': order.address,
            'created_at': order.created_at.isoformat(),
        }
    }, status=201)


def _auto_assign_courier(order):
    """Birinchi bo'sh kuryerni avtomatik biriktiradi."""
    try:
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        User = get_user_model()
        courier = User.objects.filter(
            role='courier', is_active=True
        ).order_by('courier_orders__count', 'id').first()
        if courier:
            order.assigned_courier = courier
            order.save(update_fields=['assigned_courier'])
    except Exception:
        pass


@require_GET
def my_orders(request):
    """GET /api/orders/my/ — mijozning buyurtmalari (holat tarixi bilan)."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)

    orders = Order.objects.filter(
        customer=request.user
    ).select_related('assigned_chef', 'assigned_courier').prefetch_related(
        'items__menu_item', 'history'
    ).order_by('-created_at')[:30]

    return JsonResponse({
        'orders': [o.to_dict(with_history=True) for o in orders]
    })


@csrf_exempt
@require_POST
def cancel_order(request, order_id):
    """POST /api/orders/<id>/cancel/ — {reason}"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)

    try:
        order = Order.objects.get(id=order_id, customer=request.user)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Buyurtma topilmadi'}, status=404)

    if not order.can_customer_cancel:
        return JsonResponse({
            'error': 'Bu buyurtmani bekor qilib bo\'lmaydi. Qo\'ng\'iroq qiling.'
        }, status=400)

    reason = 'Mijoz tomondan bekor qilindi'
    try:
        body = json.loads(request.body)
        if (body.get('reason') or '').strip():
            reason = body['reason'].strip()[:200]
    except (json.JSONDecodeError, TypeError):
        pass

    order.cancel_reason = reason
    order.save(update_fields=['cancel_reason'])

    try:
        order.transition_to('bekor_qilindi', changed_by=request.user, note=reason)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'success': True, 'order': order.to_dict()})


@csrf_exempt
@require_POST
def review_order(request, order_id):
    """POST /api/orders/<id>/review/ — {rating, review}"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)

    try:
        order = Order.objects.get(id=order_id, customer=request.user)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Buyurtma topilmadi'}, status=404)

    if not order.can_review:
        return JsonResponse({'error': 'Reyting qo\'yish hozircha mumkin emas'}, status=400)

    try:
        body = json.loads(request.body)
        rating = int(body.get('rating', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'error': "Noto'g'ri ma'lumot"}, status=400)

    if rating < 1 or rating > 5:
        return JsonResponse({'error': 'Reyting 1 dan 5 gacha bo\'lishi kerak'}, status=400)

    order.rating = rating
    order.review = (body.get('review') or '').strip()[:1000]
    order.save(update_fields=['rating', 'review'])

    return JsonResponse({'success': True, 'rating': order.rating})