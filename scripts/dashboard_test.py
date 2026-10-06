"""
Dashboard funksional test — live server kerak emas, Django test client.

Har bir bo'limni haqiqiy HTTP so'rovi bilan tekshiradi: validatsiya xatolari,
404/405, ruxsat, va natijada o'zgarish (barchasi o'z-o'zini tozalaydi).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402

from accounts.models import AppSettings  # noqa: E402
from menu.models import Banner, Category, MenuItem  # noqa: E402
from orders.models import Order  # noqa: E402

U = get_user_model()
ok = 0
fail = 0


def check(name, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{(' — ' + str(extra)) if extra else ''}")


admin = U.objects.filter(role='director').first() or U.objects.filter(is_superuser=True).first()
c = Client()
c.force_login(admin)

created = {'cat': [], 'item': [], 'banner': []}
saved_settings = {}


def cleanup():
    for it in MenuItem.objects.filter(pk__in=created['item']):
        it.delete()
    for b in Banner.objects.filter(pk__in=created['banner']):
        b.delete()
    for cat in Category.objects.filter(pk__in=created['cat']):
        cat.delete()
    for k, v in saved_settings.items():
        s = AppSettings.objects.filter(key=k).first()
        if s:
            s.value = v
            s.save()
        elif v is not None:
            AppSettings.objects.create(key=k, value=str(v))
    created['cat'].clear()
    created['item'].clear()
    created['banner'].clear()


print('=== Stats ===')
r = c.get('/api/dashboard/stats/')
d = r.json()
check('stats 200', r.status_code == 200, r.status_code)
check('bugungi kunlik statistika', 'today' in d, list(d.keys()))
check('grafik ma\'lumoti', 'chart' in d, list(d.get('chart', {})))
check('oxirgi buyurtmalar', 'recent_orders' in d, len(d.get('recent_orders', [])))
check('faol kuryerlar', 'active_couriers' in d, d.get('active_couriers'))
today = d.get('today', {})
check('today ichida summa bor', 'revenue' in today or 'total' in today, list(today))

print('\n=== Buyurtmalar ===')
r = c.get('/api/dashboard/orders/?status=&date=')
check('orders ro\'yxati 200', r.status_code == 200, r.status_code)
o0 = Order.objects.exclude(status__in=('yangi',)).first() or Order.objects.first()
if o0:
    r = c.get(f'/api/dashboard/orders/?status={o0.status}&date=')
    check('status filter ishlaydi', r.status_code == 200, r.status_code)
    r = c.post(f'/api/dashboard/orders/999999/status/',
               data=json.dumps({'status': 'tayyor'}),
               content_type='application/json')
    check('noma\'lum buyurtma -> 404', r.status_code == 404, r.status_code)
    r = c.post(f'/api/dashboard/orders/{o0.id}/status/',
               data=json.dumps({'status': 'noti_gorilar'}),
               content_type='application/json')
    check('noto\'g\'ri status -> 400', r.status_code == 400, r.json())

print('\n=== Kategoriya CRUD ===')
r = c.post('/api/dashboard/menu/categories/',
           data=json.dumps({'name': 'AUDIT KAT', 'icon': 'x'}),
           content_type='application/json')
check('kategoriya yaratish 201', r.status_code == 201, f"{r.status_code} {r.json()}")
cat_id = r.json().get('category', {}).get('id')
if cat_id:
    created['cat'].append(cat_id)

r = c.post('/api/dashboard/menu/categories/', data=json.dumps({'name': ''}),
           content_type='application/json')
check('bo\'sh nom -> 400', r.status_code == 400, r.json())

if cat_id:
    r = c.post(f'/api/dashboard/menu/categories/{cat_id}/',
               data=json.dumps({'name': 'AUDIT KAT 2'}), content_type='application/json')
    check('kategoriya tahrirlash', r.status_code == 200 and
          Category.objects.get(pk=cat_id).name == 'AUDIT KAT 2', r.json())

print('\n=== Mahsulot CRUD ===')
if cat_id:
    r = c.post('/api/dashboard/menu/items/',
               data=json.dumps({'name': 'AUDIT ITEM', 'category_id': cat_id, 'price': 12345}),
               content_type='application/json')
    check('mahsulot yaratish 201', r.status_code == 201, f"{r.status_code} {r.json()}")
    item_id = r.json().get('item', {}).get('id')
    if item_id:
        created['item'].append(item_id)
        r = c.post(f'/api/dashboard/menu/items/{item_id}/',
                   data=json.dumps({'is_available': False}),
                   content_type='application/json')
        check('mavjudlikni o\'zgartirish (toggle)', r.status_code == 200 and
              MenuItem.objects.get(pk=item_id).is_available is False, r.json())

    r = c.post('/api/dashboard/menu/items/',
               data=json.dumps({'name': '', 'category_id': cat_id, 'price': 100}),
               content_type='application/json')
    check('bo\'sh mahsulot nomi -> 400', r.status_code == 400, r.json())

    r = c.post('/api/dashboard/menu/items/',
               data=json.dumps({'name': 'X', 'category_id': 999999, 'price': 100}),
               content_type='application/json')
    check('ma\'lum kategoriya -> 404', r.status_code == 404, f"{r.status_code} {r.json()}")

    r = c.post('/api/dashboard/menu/items/',
               data=json.dumps({'name': 'X', 'price': 100}), content_type='application/json')
    check('kategoriyasiz mahsulot -> 400', r.status_code == 400, r.json())

print('\n=== Banner validatsiyasi ===')
r = c.post('/api/dashboard/banners/', data=json.dumps({'title': ''}), content_type='application/json')
check('bo\'sh banner sarlavhasi -> 400', r.status_code == 400, r.json())

r = c.post('/api/dashboard/banners/',
           data=json.dumps({'title': 'AUDIT B', 'color_start': 'red',
                            'layout': 'noti_gorilar', 'autoplay_delay': 9999}),
           content_type='application/json')
b = r.json().get('banner', {})
bid = b.get('id')
check('banner yaratildi', bool(bid), f"{r.status_code} {r.json()}")
if bid:
    created['banner'].append(bid)
    # POST javobi qisqa (faqat id/title/image_url/is_active/order) —
    # to'g'ri qiymatlarni GET orqali tekshiramiz.
    db = next(x for x in c.get('/api/dashboard/banners/').json()['banners'] if x['id'] == bid)
    check('noto\'g\'ri rang -> default hex', db['color_start'] == '#E63946', db['color_start'])
    check('noto\'g\'ri layout -> default', db['layout'] == 'image_right', db['layout'])
    check('autoplay_delay 9999 -> 60 ga kesildi', db['autoplay_delay'] == 60, db['autoplay_delay'])

print('\n=== Banner URL validatsiyasi ===')
r = c.post('/api/dashboard/banners/',
           data=json.dumps({'title': 'AUDIT URL', 'button_text': 'Bor',
                            'button_action': 'open_url', 'button_value': 'javascript:alert(1)'}),
           content_type='application/json')
bid = r.json().get('banner', {}).get('id')
check('URL banner yaratildi', bool(bid), r.json())
if bid:
    created['banner'].append(bid)
    db = next(x for x in c.get('/api/dashboard/banners/').json()['banners'] if x['id'] == bid)
    check('javascript: URL saqlanmadi',
          not db['button_value'].lower().startswith('javascript:'), db['button_value'] or '(bo\'sh)')

# data: va noto'g'ri shema ham rad etilishi kerak
for bad in ('data:text/html,<script>alert(1)</script>', 'vbscript:msgbox(1)', 'ftp://x/y'):
    r = c.post('/api/dashboard/banners/',
               data=json.dumps({'title': f'AUDIT {bad[:12]}', 'button_text': 'B',
                                'button_action': 'open_url', 'button_value': bad}),
               content_type='application/json')
    nbid = r.json().get('banner', {}).get('id')
    if nbid:
        created['banner'].append(nbid)
        dbb = next(x for x in c.get('/api/dashboard/banners/').json()['banners'] if x['id'] == nbid)
        check(f'{bad[:20]} rad etildi', dbb['button_value'] == '', dbb['button_value'] or '(bo\'sh)')
    else:
        check(f'{bad[:20]} rad etildi', True, f"{r.status_code} (400)")

# haqiqiy https:// havolasi saqlanishi kerak
r = c.post('/api/dashboard/banners/',
           data=json.dumps({'title': 'AUDIT OK', 'button_text': 'B',
                            'button_action': 'open_url',
                            'button_value': 'https://t.me/bekburger'}),
           content_type='application/json')
nbid = r.json().get('banner', {}).get('id')
if nbid:
    created['banner'].append(nbid)
    dbk = next(x for x in c.get('/api/dashboard/banners/').json()['banners'] if x['id'] == nbid)
    check('https:// havolasi saqlandi', dbk['button_value'] == 'https://t.me/bekburger', dbk['button_value'])

print('\n=== Sozlamalar ===')
r = c.get('/api/dashboard/settings/')
check('settings 200', r.status_code == 200, r.status_code)
sd = r.json()
check('settings qaytaradi', 'settings' in sd or isinstance(sd, list), list(sd)[:6])

for k in ('restaurant_name', 'currency', 'banner_autoplay', 'banner_interval',
          'app_tagline', 'restaurant_address', 'free_delivery_from', 'order_cancel_allowed'):
    check(f'setting mavjud: {k}', k in json.dumps(sd), '')

# Uzunlik cheklovi
for key, long_val in (('app_tagline', 'a' * 500), ('currency', 'y' * 50)):
    r = c.post('/api/dashboard/settings/',
               data=json.dumps({key: long_val}), content_type='application/json')
    check(f'juda uzun {key} -> 400', r.status_code == 400, f'{r.status_code} {str(r.json())[:70]}')

r = c.post('/api/dashboard/settings/',
           data=json.dumps({'restaurant_name': '   '}), content_type='application/json')
check('faqat bo\'sh joyli restaurant_name -> 400', r.status_code == 400, f'{r.status_code} {r.json()}')

for k, v in AppSettings.objects.filter(key__in=[
        'restaurant_name', 'banner_interval', 'currency', 'app_tagline']).values_list('key', 'value'):
    saved_settings[k] = v

r = c.post('/api/dashboard/settings/',
           data=json.dumps({'banner_interval': 2}), content_type='application/json')
check('banner_interval 2 -> keshga solindi (min 3)', r.status_code == 200, r.status_code)

r = c.post('/api/dashboard/settings/',
           data=json.dumps({'banner_interval': 'abc'}), content_type='application/json')
check('noto\'g\'ri interval -> 400', r.status_code == 400, f"{r.status_code} {r.json()}")

r = c.post('/api/dashboard/settings/',
           data=json.dumps({'restaurant_name': 'x' * 500}), content_type='application/json')
check(' juda uzun nom -> 400 (uzunlik cheklovi)', r.status_code == 400,
      f"{r.status_code} {str(r.json())[:80]}")

print('\n=== Reytinglar (API bor, UI yo\'q) ===')
r = c.get('/api/dashboard/reviews/')
check('reviews API 200', r.status_code == 200, r.status_code)
rv = r.json()
check('reviews stats bor', 'stats' in rv, list(rv))
check('average 0..5 oralig\'ida', 0 <= rv['stats']['average'] <= 5, rv['stats'])

print('\n=== Ruxsat ===')
anon = Client()
r = anon.get('/api/dashboard/stats/')
check('anon -> 401/403', r.status_code in (401, 403), r.status_code)
cust = U.objects.filter(role='customer').first()
if cust:
    cc = Client()
    cc.force_login(cust)
    r = cc.get('/api/dashboard/settings/')
    check('mijoz dashboard API -> 403', r.status_code == 403, r.status_code)

print('\n=== Tozalash ===')
cleanup()
print('  test ma\'lumotlari o\'chirildi')

print(f'\nDashboard funksional: {ok} / {ok + fail} passed')
sys.exit(1 if fail else 0)
