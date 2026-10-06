import os
import sys

# Loyiha ildizi sys.path ga (skript scripts/ ichidan ishga tushirilganda)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')
"""
Dinamik brendlashuvni jonli HTTP orqali tekshiradi:
admin panel orqali restoran nomi/valyutani o'zgartirib, BARCHA sahifalarda
darhol aks etishini va keyin tiklanishini tekshiradi.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = os.getenv('TEST_BASE_URL', 'http://127.0.0.1:8010')
ADMIN_USER = os.getenv('TEST_ADMIN_USERNAME', 'admin')
ADMIN_PASS = os.getenv('TEST_ADMIN_PASSWORD', 'admin123')

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

results = []


def report(name, ok, extra=''):
    results.append(ok)
    print('  {} {}{}'.format('OK  ' if ok else 'FAIL', name, (' — ' + str(extra)) if extra else ''))


def get(path):
    with opener.open(BASE + path, timeout=15) as r:
        return r.status, r.read().decode('utf-8', 'ignore')


def csrf():
    for c in jar:
        if c.name == 'csrftoken':
            return c.value
    return ''


def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path, data=data, method='POST',
        headers={'Content-Type': 'application/json', 'X-CSRFToken': csrf(),
                 'Referer': BASE + '/dashboard/'},
    )
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


PAGES = {
    'customer': '/miniapp/customer/',
    'chef': '/miniapp/chef/',
    'courier': '/miniapp/courier/',
    'dashboard': '/dashboard/',
}

NEW_NAME = 'Pizza Kingdom'
NEW_CUR = '$'

print('=== Boshlang\'ich holat ===')
status, cfg = get('/api/config/')
cfg = json.loads(cfg)['config']
print('  restaurant_name =', cfg['restaurant_name'], '| currency =', cfg['currency'])
report('boshlang\'ich nom BekBurger', cfg['restaurant_name'] == 'BekBurger')

print('\n=== Admin sifatida kiramiz ===')
import base64

req = urllib.request.Request(BASE + '/admin/login/')
with opener.open(req, timeout=15) as r:
    html = r.read().decode()
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
data = urllib.parse.urlencode({
    'username': ADMIN_USER, 'password': ADMIN_PASS,
    'csrfmiddlewaretoken': token, 'next': '/admin/',
}).encode()
req = urllib.request.Request(
    BASE + '/admin/login/', data=data,
    headers={'Referer': BASE + '/admin/login/', 'Content-Type': 'application/x-www-form-urlencoded'},
)
with opener.open(req, timeout=15) as r:
    ok = '/admin/' in r.geturl() and 'logout' in r.read().decode().lower()
report('admin login muvaffaqiyatli', ok)

status, body = get('/api/dashboard/settings/')
report('dashboard settings 200', status == 200, status)

print('\n=== Nom va valyutani o\'zgartiramiz ===')
status, body = post('/api/dashboard/settings/',
                    {'restaurant_name': NEW_NAME, 'currency': NEW_CUR,
                     'app_tagline': 'Test sarlavhasi'})
report('settings POST 200', status == 200, body)

status, raw = get('/api/config/')
cfg = json.loads(raw)['config']
report('/api/config/ darhol yangilandi',
       cfg['restaurant_name'] == NEW_NAME and cfg['currency'] == NEW_CUR, cfg)

print('\n=== Barcha sahifalar yangilanganmi? ===')
CHECKS = [
    ('customer header', '/miniapp/customer/', r'id="headerName"[^>]*>([^<]+)<', NEW_NAME),
    ('customer footer', '/miniapp/customer/', r'id="footerBrand"[^>]*>([^<]+)<', '\U0001F354 ' + NEW_NAME),
    ('chef title', '/miniapp/chef/', r'<title>([^<]+)</title>', NEW_NAME + ' — Oshpaz'),
    ('courier title', '/miniapp/courier/', r'<title>([^<]+)</title>', NEW_NAME + ' — Kuryer'),
    ('dashboard title', '/dashboard/', r'<title id="pageTabTitle">([^<]+)</title>', NEW_NAME + ' — Admin Dashboard'),
    ('dashboard sidebar', '/dashboard/', r'id="sidebarRestName">([^<]+)<', NEW_NAME + ' Admin'),
    ('django admin title', '/admin/', r'<title>([^<]+)</title>', 'Boshqaruv paneli | ' + NEW_NAME),
    ('django admin brand', '/admin/', r'id="site-name">.*?>([^<]+)<', NEW_NAME + ' — Boshqaruv'),
]
for label, path, pattern, expected in CHECKS:
    status, html = get(path)
    m = re.search(pattern, html, re.S)
    actual = m.group(1).strip() if m else '(topilmadi)'
    report(label + ' = ' + expected, actual == expected, actual)

print('\n=== Mijoz ilovasi konfiguratsiyasi ===')
m = re.search(r'<script id="app-config" type="application/json">(.*?)</script>', get('/miniapp/customer/')[1], re.S)
inline = json.loads(m.group(1)) if m else {}
report('inline config yangilandi',
       inline.get('restaurant_name') == NEW_NAME and inline.get('currency') == NEW_CUR, inline)

print('\n=== Tiklash ===')
status, body = post('/api/dashboard/settings/',
                    {'restaurant_name': 'BekBurger', 'currency': "so'm",
                     'app_tagline': 'Tez va mazali yetkazib beramiz'})
report('tiklash 200', status == 200, body)
status, raw = get('/api/config/')
cfg = json.loads(raw)['config']
report('nom BekBurger ga qaytdi', cfg['restaurant_name'] == 'BekBurger', cfg['restaurant_name'])
for label, path in PAGES.items():
    status, html = get(path)
    report('{} sahifasi tiklangan'.format(label), 'BekBurger' in html and NEW_NAME not in html)

print()
print('Dinamik brendlashuv: {} / {} o\'tgan'.format(sum(results), len(results)))
sys.exit(0 if all(results) else 1)
