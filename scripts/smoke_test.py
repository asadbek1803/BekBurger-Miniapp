"""
Production smoke test — barcha asosiy endpoint'lar, rollar va narx himoyasi.

Ishga tushirish:  python scripts/smoke_test.py

Xavfsizlik:
  * Faqat o'zi yaratgan ma'lumotlarni o'chiradi (buyurtma, banner, savat).
  * Mavjud foydalanuvchi ma'lumotlariga tegmaydi — bekor qilish/review
    tekshiruvlari FAQAT test buyurtmasi ustida bajariladi.
  * O'zgartirilgan sozlamalarni oxirida tiklaydi.
"""
import json
import os
import sys

# Loyiha ildizi sys.path ga (skript scripts/ ichidan ishga tushirilganda)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()

PASS, FAIL = [], []

# Test yaratgan va O'ZINI tozalashi kerak bo'lgan obyektlar
CREATED_ORDERS = []
CREATED_BANNERS = []
SAVED_SETTINGS = {}


def check(name, cond, extra=''):
    (PASS if cond else FAIL).append(name)
    print(('  OK   ' if cond else '  FAIL ') + name + ((' — ' + str(extra)) if extra and not cond else ''))


def login(username, password):
    c = Client()
    ok = c.login(username=username, password=password)
    return c, ok


def cleanup():
    """Test qoldiqlarini tozalash."""
    from menu.models import Banner
    from orders.models import Order

    deleted = 0
    for bid in CREATED_BANNERS:
        deleted += Banner.objects.filter(pk=bid).delete()[0]
    for oid in CREATED_ORDERS:
        deleted += Order.objects.filter(pk=oid).delete()[0]
    print('\n=== Tozalash ===')
    print('  test ma\'lumotlari o\'chirildi:', deleted)


print('\n=== 1. Config & menyu ===')
anon = Client()
r = anon.get('/api/config/')
cfg = r.json()['config']
check('/api/config/ 200', r.status_code == 200)
check('restaurant_name = BekBurger', cfg['restaurant_name'] == 'BekBurger', cfg['restaurant_name'])
check('currency bor', bool(cfg.get('currency')))
check('banner_interval > 0', cfg.get('banner_interval', 0) > 0)

r = anon.get('/api/menu/categories/')
check('categories 200', r.status_code == 200)
check('categories da banners bor', 'banners' in r.json())

r = anon.get('/api/menu/items/?q=burger')
items = r.json()['items']
check('items?q= ishlaydi', r.status_code == 200 and isinstance(items, list))
check('q faqat mos itemlarni qaytaradi',
      all('burger' in (i['name'] + ' ' + i['description']).lower() for i in items),
      [i['name'] for i in items])

r = anon.get('/api/menu/items/?max=3')
check('items?max= limit ishlaydi', len(r.json()['items']) <= 3)

print('\n=== 2. Role himoyasi ===')
for url in ('/api/dashboard/stats/', '/api/dashboard/banners/', '/api/staff/chef/orders/',
            '/api/staff/courier/orders/', '/api/orders/my/'):
    r = anon.get(url)
    check(f'anon {url} rad etildi ({r.status_code})', r.status_code in (302, 401, 403))

chef_c, ok = login('dev_chef', 'chef123')
check('dev_chef login', ok)
r = chef_c.get('/api/dashboard/stats/')
check('oshpaz dashboard API dan rad etildi', r.status_code in (401, 403), r.status_code)
r = chef_c.get('/api/staff/chef/orders/')
check('oshpaz o\'z API sidan foydalana oladi', r.status_code == 200, r.status_code)

coup_c, ok2 = login('dev_courier', 'courier123')
check('dev_courier login', ok2)
r = coup_c.get('/api/staff/courier/orders/')
check('kuryer o\'z API sidan foydalana oladi', r.status_code == 200, r.status_code)

cust_c, ok3 = login('dev_customer', 'customer123')
check('dev_customer login', ok3)
r = cust_c.get('/api/staff/chef/orders/')
check('mijoz chef API siga kira olmaydi', r.status_code in (401, 403), r.status_code)

admin_c, ok4 = login('admin', 'admin123')
check('admin login', ok4)
r = admin_c.get('/api/dashboard/stats/')
check('admin dashboard stats 200', r.status_code == 200, r.status_code)

print('\n=== 3. Savat + narx himoyasi ===')
from menu.models import MenuItem
item = MenuItem.objects.filter(is_available=True).first()
check('test uchun mahsulot bor', item is not None)
created_id = None

if item:
    cust_c.post('/api/cart/clear/', content_type='application/json')

    r = cust_c.post('/api/cart/add/', data=json.dumps({'item_id': item.id, 'quantity': 2}),
                    content_type='application/json')
    check('cart add 200', r.status_code == 200, (r.status_code, r.content[:120]))
    payload = cust_c.get('/api/cart/').json()
    check('cart da item bor', any(i['id'] == item.id and i['quantity'] == 2 for i in payload['items']),
          payload)
    check('cart subtotal serverdan hisoblangan',
          payload['subtotal'] == int(item.price) * 2, (payload['subtotal'], int(item.price) * 2))

    # Narxni o'zgartirib yuborishga urinish — server DB narxini ishlatishi kerak
    r = cust_c.post('/api/cart/add/', data=json.dumps({'item_id': item.id, 'quantity': 1, 'price': 1}),
                    content_type='application/json')
    payload2 = cust_c.get('/api/cart/').json()
    row = next(i for i in payload2['items'] if i['id'] == item.id)
    check('server narxi DB dan (injection muvaffaqiyatsiz)', row['price'] == int(item.price),
          (row['price'], int(item.price)))
    check('miqdor 2 + 1 = 3', row['quantity'] == 3, row['quantity'])
    payload = payload2

    # Manzil yo'q — xato berishi kerak
    r = cust_c.post('/api/orders/create/', data=json.dumps({'payment_method': 'naqd'}),
                    content_type='application/json')
    check('manzil yo\'qda create rad etildi', r.status_code == 400, (r.status_code, r.content[:140]))

    # To'g'ri create (narx faqat serverda hisoblanadi)
    r = cust_c.post('/api/orders/create/', data=json.dumps({
        'address': 'Toshkent, Amir Temur 1', 'note': 'smoke-test', 'payment_method': 'naqd',
        'latitude': 41.311081, 'longitude': 69.240562,
    }), content_type='application/json')
    check('orders/create 201', r.status_code == 201, (r.status_code, r.content[:200]))
    created_id = r.json().get('order', {}).get('id') if r.status_code == 201 else None
    if created_id:
        CREATED_ORDERS.append(created_id)
        from orders.models import Order
        o = Order.objects.get(id=created_id)
        check('subtotal DB da to\'g\'ri', o.subtotal == payload['subtotal'], (o.subtotal, payload['subtotal']))
        check('delivery_fee hisoblangan', o.delivery_fee == payload['delivery_fee'],
              (o.delivery_fee, payload['delivery_fee']))
        check('total = subtotal + fee', o.total_price == o.subtotal + o.delivery_fee,
              (o.total_price, o.subtotal, o.delivery_fee))
        check('payment_method = naqd', o.payment_method == 'naqd', o.payment_method)
        check('OrderItem yaratilgan', o.items.exists())
        check('buyurtma tarixi yozildi', o.history.exists())
        d = o.to_dict()
        check('to_dict ishlaydi', isinstance(d, dict) and d.get('id') == created_id)

    cust_c.post('/api/cart/clear/', content_type='application/json')
    check('cart clear 200',
          cust_c.post('/api/cart/clear/', content_type='application/json').status_code == 200)

print('\n=== 4. Sozlamalar (dinamik) ===')
r = admin_c.get('/api/dashboard/settings/')
check('settings GET 200', r.status_code == 200)
settings = r.json()['settings']
keys = {s['key'] for s in settings}
need = {'restaurant_name', 'app_tagline', 'restaurant_address', 'currency', 'delivery_fee',
        'free_delivery_from', 'min_order_amount', 'max_delivery_km', 'auto_assign_courier',
        'banner_autoplay', 'banner_interval', 'order_cancel_allowed', 'working_hours',
        'phone', 'dev_mode', 'telegram_bot_token', 'telegram_miniapp_url'}
check('barcha 18 sozlama mavjud', need <= keys, sorted(need - keys))
for k in ('app_tagline', 'banner_interval'):
    SAVED_SETTINGS[k] = next(s['value'] for s in settings if s['key'] == k)

r = admin_c.post('/api/dashboard/settings/',
                 data=json.dumps({'app_tagline': 'Smoke test', 'banner_interval': '7'}),
                 content_type='application/json')
check('settings POST 200', r.status_code == 200, (r.status_code, r.content[:160]))
cfg2 = Client().get('/api/config/').json()['config']
check('config darhol yangilandi (kesh buzildi)', cfg2['banner_interval'] == 7, cfg2['banner_interval'])

r = admin_c.post('/api/dashboard/settings/', data=json.dumps({'banner_interval': 'abc'}),
                 content_type='application/json')
check('noto\'g\'ri number rad etildi', r.status_code == 400, r.status_code)

r = admin_c.post('/api/dashboard/settings/', data=json.dumps(SAVED_SETTINGS),
                 content_type='application/json')
check('sozlamalar tiklandi', r.status_code == 200, r.status_code)

print('\n=== 5. Bannerlar ===')
r = admin_c.post('/api/dashboard/banners/', data={
    'title': 'SMOKE banner', 'subtitle': 'test', 'label': 'TEST',
    'color_start': '#112233', 'color_end': 'javascript:alert(1)', 'text_color': '#ffffff',
    'layout': 'background', 'button_text': 'Menyu', 'button_action': 'open_url',
    'button_value': 'https://example.com', 'autoplay_delay': '9', 'order': '99',
})
check('banner create 201', r.status_code == 201, (r.status_code, r.content[:200]))
bid = r.json()['banner']['id'] if r.status_code == 201 else None

if bid:
    CREATED_BANNERS.append(bid)
    r = admin_c.get('/api/dashboard/banners/')
    b = next((x for x in r.json()['banners'] if x['id'] == bid), None)
    check('banner gradient to\'g\'ri', b and b['color_start'] == '#112233', b)
    check('zararli CSS rang rad etildi', b and b['color_end'] == '#F4A261', b)
    check('banner delay saqlandi', b and b['autoplay_delay'] == 9, b)
    check('banner layout saqlandi', b and b['layout'] == 'background', b)

    r = admin_c.post(f'/api/dashboard/banners/{bid}/', data={'autoplay_delay': '999', 'layout': 'hacked'},
                     content_type='application/json')
    check('banner update 200', r.status_code == 200 and r.json().get('success') is True,
          (r.status_code, r.content[:120]))
    r = admin_c.get('/api/dashboard/banners/')
    b = next((x for x in r.json()['banners'] if x['id'] == bid), {})
    check('autoplay_delay 60 ga qisqarldi', b.get('autoplay_delay') == 60, b.get('autoplay_delay'))
    check('noto\'g\'ri layout rad etildi', b.get('layout') == 'background', b.get('layout'))

print('\n=== 6. Buyurtma hayoti (faqat test buyurtmasi) ===')
from orders.models import Order, OrderStatusHistory
check('test buyurtmasi yaratildi', created_id is not None)
if created_id:
    o = Order.objects.get(id=created_id)
    check('history mavjud', OrderStatusHistory.objects.filter(order=o).exists())
    check('can_customer_cancel (yangi holatda)', o.can_customer_cancel is True)

    r = cust_c.post(f'/api/orders/{created_id}/cancel/', data=json.dumps({'reason': 'smoke-test'}),
                    content_type='application/json')
    check('cancel ishladi', r.status_code == 200, (r.status_code, r.content[:140]))
    o.refresh_from_db()
    check('bekor_qilindi holati', o.status == 'bekor_qilindi', o.status)
    check('cancelled_at qo\'yildi', o.cancelled_at is not None)
    check('can_customer_cancel (bekor qilinganda)', o.can_customer_cancel is False)

    r = cust_c.post(f'/api/orders/{created_id}/review/',
                    data=json.dumps({'rating': 5, 'review': 'zo\'r'}),
                    content_type='application/json')
    check('bekor qilinganga review rad etildi', r.status_code == 400, r.status_code)

    # Yana bir marta bekor qilish mumkin emas
    r = cust_c.post(f'/api/orders/{created_id}/cancel/', data=json.dumps({'reason': 'smoke'}),
                    content_type='application/json')
    check('qayta bekor qilish rad etildi', r.status_code == 400, r.status_code)

print('\n=== 7. Sahifalar ===')
pages = {
    '/miniapp/customer/': Client(),
    '/miniapp/chef/': chef_c,
    '/miniapp/courier/': coup_c,
    '/dashboard/': admin_c,
}
for url, c in pages.items():
    r = c.get(url)
    html = r.content.decode('utf-8', 'ignore')
    check(f'{url} 200', r.status_code == 200, r.status_code)
    check(f'{url} BekBurger bor', 'BekBurger' in html)

r = Client().get('/admin/login/')
check('/admin/login/ 200', r.status_code == 200, r.status_code)

cleanup()

print('\n' + '=' * 56)
print(f'PASS: {len(PASS)}   FAIL: {len(FAIL)}')
if FAIL:
    print('MUAMMOLAR:')
    for f in FAIL:
        print('  -', f)
sys.exit(1 if FAIL else 0)
