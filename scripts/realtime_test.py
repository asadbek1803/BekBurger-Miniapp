import os
import sys

# Loyiha ildizi sys.path ga (skript scripts/ ichidan ishga tushirilganda)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')
"""Real-time broadcast test: WS klient ulangan holda broadcast yetkazilishini tekshiradi."""
import os

import django


django.setup()

import asyncio
import concurrent.futures

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from orders.models import Order, OrderStatusHistory
from orders.routing import websocket_urlpatterns

U = get_user_model()
app = URLRouter(websocket_urlpatterns)
pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

_created = []   # test yaratgan buyurtmalar
_undo = []      # (order_id, eski_status) — qaytarish uchun
_saved_settings = []  # (settings_id, eski_value|None) — qaytarish uchun


def run_sync(fn, *a, **kw):
    return pool.submit(fn, *a, **kw).result()


def _pick_order():
    from orders.models import Order
    for o in Order.objects.select_related('customer').exclude(status__in=('yetkazildi', 'bekor_qilindi')):
        return o
    return None


async def main():
    chef = run_sync(U.objects.get, username='dev_chef')
    order = await asyncio.wrap_future(pool.submit(_pick_order))
    if order is None:
        print('O\'tirishga yaroqli buyurtma topilmadi (barchasi yetkazilgan/bekor qilingan).')
        return

    results = []

    def report(name, ok, extra=''):
        results.append(ok)
        print('  {} {}{}'.format('OK  ' if ok else 'FAIL', name, (' — ' + str(extra)) if extra else ''))

    # 1) Mijoz kanali: sozlamalar yangilandi
    cfg_c = WebsocketCommunicator(app, '/ws/config/')
    await cfg_c.connect()
    await cfg_c.receive_json_from()  # boshlang'ich xabar
    await asyncio.wrap_future(pool.submit(_change_setting))
    msg = await cfg_c.receive_json_from(timeout=5)
    report('sozlama o\'zgarishi config WS ga yetkazildi',
           msg.get('action') == 'config_update', msg.get('action'))
    await cfg_c.disconnect()

    # 2) Mijoz kanali: menyu/banner yangilandi
    cfg_c = WebsocketCommunicator(app, '/ws/config/')
    await cfg_c.connect()
    await cfg_c.receive_json_from()
    await asyncio.wrap_future(pool.submit(_touch_banner))
    msg = await cfg_c.receive_json_from(timeout=5)
    report('banner yangilanishi menu_update yuborildi', msg.get('action') == 'menu_update', msg.get('action'))
    await cfg_c.disconnect()

    # 3) Staff kanali: buyurtma holati o'zgarishi
    staff_c = WebsocketCommunicator(app, '/ws/staff/orders/')
    staff_c.scope['user'] = chef
    await staff_c.connect()

    before = run_sync(Order.objects.get, pk=order.pk).status
    await asyncio.wrap_future(pool.submit(_bump_status, order.pk))
    try:
        msg = await staff_c.receive_json_from(timeout=5)
        ok = (msg.get('action') == 'order_update'
              and msg.get('id') == order.id
              and msg.get('status') != before
              and 'valid_transitions' in msg)
        report('holat o\'zgarishi staff WS ga yetkazildi', ok, msg)
    except asyncio.TimeoutError:
        report('holat o\'zgarishi staff WS ga yetkazildi', False, 'timeout')

    # 4) Yangi buyurtma xabari
    await asyncio.wrap_future(pool.submit(_make_order))
    try:
        msg = await staff_c.receive_json_from(timeout=5)
        report('yangi buyurtma xabari', msg.get('action') == 'order_update' and msg.get('id') is not None, msg)
    except asyncio.TimeoutError:
        report('yangi buyurtma xabari', False, 'timeout')

    await staff_c.disconnect()

    # 5) Kuryer kuzatuv kanali
    track_c = WebsocketCommunicator(app, '/ws/orders/{}/track/'.format(order.id))
    ok, _ = await track_c.connect()
    report('kuryer kuzatuv kanali ulandi', ok)
    await track_c.send_json_to({'action': 'update_location', 'lat': 41.31, 'lng': 69.24})
    msg = await track_c.receive_json_from(timeout=5)
    report('joylashuv xabari', msg.get('action') == 'location_update', msg)
    await track_c.disconnect()

    await asyncio.wrap_future(pool.submit(_cleanup))

    print()
    print('Real-time: {} / {} passed'.format(sum(results), len(results)))


def _noop():
    pass


def _change_setting():
    from accounts.models import AppSettings
    s, created = AppSettings.objects.get_or_create(key='app_tagline', defaults={'label': 'Slogan'})
    old = None if created else s.value
    _saved_settings.append((s.pk, old))
    s.value = 'Real-time test'
    s.save()
    return old


def _touch_banner():
    from menu.models import Banner
    b = Banner.objects.first()
    if b:
        b.save()  # updated_at yangilanadi


def _bump_status(pk):
    o = Order.objects.get(pk=pk)
    nxt = (Order.VALID_TRANSITIONS.get(o.status) or [])[0]
    old = o.status
    o.transition_to(nxt, changed_by=None, note='ws-test')
    _undo.append((o.pk, old))
    return nxt


def _restore():
    """Test qilgan o'zgarishlarni qaytarish."""
    from accounts.models import AppSettings
    for pk, old in reversed(_saved_settings):
        s = AppSettings.objects.filter(pk=pk).first()
        if not s:
            continue
        if old is None:      # test yaratgan sozlamani butunlay o'chiramiz
            s.delete()
        else:
            s.value = old
            s.save()
    _saved_settings.clear()
    for pk, old in reversed(_undo):
        o = Order.objects.filter(pk=pk).first()
        if not o:
            continue
        o.status = old
        o.save()
        OrderStatusHistory.objects.filter(order=o, note='ws-test').delete()
    _undo.clear()


def _make_order():
    from menu.models import MenuItem
    from orders.models import Order, OrderItem
    u = U.objects.filter(username='dev_customer').first()
    it = MenuItem.objects.filter(is_available=True).first()
    o = Order.objects.create(customer=u, status='yangi', address='Toshkent, test',
                            subtotal=it.price, delivery_fee=0, total_price=it.price)
    OrderItem.objects.create(order=o, menu_item=it, quantity=1, price=it.price)
    _created.append(o.id)
    from orders.broadcast import broadcast_order_update
    broadcast_order_update(o)
    return o.id


def _cleanup():
    from orders.models import Order
    for pk in _created:
        Order.objects.filter(pk=pk).delete()
    _created.clear()
    _restore()


asyncio.run(main())
