"""
Order broadcast over Channels.

Buyurtma holati o'zgarganda oshpaz va kuryer panelariga avtomatik
xabar yuboriladi — ular qo'lda yangilashni kutmasdan ko'radi.
"""
import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

STAFF_GROUP = 'bb_staff_orders'


def _payload(order):
    from .models import Order
    now_labels = {
        'yangi': '🔔 Yangi buyurtma!',
        'qabul_qilindi': '✅ Qabul qilindi',
        'tayyorlanmoqda': '👨‍🍳 Tayyorlanmoqda',
        'tayyor': '📦 Tayyor',
        'yolda': '🛵 Yo\'lda',
        'yetkazildi': '🎉 Yetkazildi',
        'bekor_qilindi': '❌ Bekor qilindi',
    }
    return {
        'action': 'order_update',
        'id': order.id,
        'status': order.status,
        'status_display': order.get_status_display(),
        'label': now_labels.get(order.status, order.get_status_display()),
        'total': int(order.total_price),
        'customer': order.customer.display_name if order.customer else '—',
        'customer_phone': (order.customer.phone if order.customer else '') or '—',
        'items_count': sum(i.quantity for i in order.items.all()),
        'address': order.address,
        'note': order.note,
        'valid_transitions': Order.VALID_TRANSITIONS.get(order.status, []),
        'created_at': order.created_at.strftime('%H:%M'),
    }


def broadcast_order_update(order):
    """Buyurtma holatini staff panelalariga yuboradi. Xato bo'lsa jim qoladi."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            STAFF_GROUP,
            {'type': 'staff.order_update', 'data': _payload(order)},
        )
    except Exception as e:
        print(f'Order broadcast error: {e}')


def broadcast_settings_update():
    """Sozlamalar yangilanganda mijoz app'ini xabardor qiladi."""
    try:
        from accounts.settings_service import public_config
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            'bb_customers',
            {'type': 'customer.config_update', 'data': public_config()},
        )
    except Exception as e:
        print(f'Settings broadcast error: {e}')


def broadcast_menu_update():
    """Menyu yoki bannerlar o'zgarganda mijoz app'ini yangilashga undaydi."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            'bb_customers',
            {'type': 'customer.menu_update', 'data': {}},
        )
    except Exception as e:
        print(f'Menu broadcast error: {e}')