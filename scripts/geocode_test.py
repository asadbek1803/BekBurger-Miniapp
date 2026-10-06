"""Geokodlash proksi testi — fake Nominatim upstream bilan."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')

SEEN = []


class Fake(BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN.append((self.path, self.headers.get('User-Agent')))
        body = json.dumps({'display_name': 'Toshkent, Chilanzar tumani, Ozbekiston'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(('127.0.0.1', 8099), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()

os.environ['GEOCODER_URL'] = 'http://127.0.0.1:8099/search'

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402

c = Client()
ok = 0
fail = 0


def check(name, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{(' — ' + str(extra)) if extra else ''}")


print('=== Geokodlash proksi ===')
for i in range(3):
    r = c.get('/api/geocode/reverse/?lat=41.299512&lon=69.240133')
    data = r.json()
    check(f'call {i+1}: 200 + manzil', r.status_code == 200 and data.get('address', '').startswith('Toshkent'),
          f"{r.status_code} source={data.get('source')}")

check('3-cha chaqiruv keshdan (upstream faqat 1 marta)', len(SEEN) == 1, f'upstream so\'rovlari: {len(SEEN)}')
check('User-Agent yuborilgan (nominatim talabi)',
      bool(SEEN and SEEN[0][1] and 'BekBurger' in SEEN[0][1]), SEEN[0][1] if SEEN else None)
check('zoom va accept-language so\'rovgа kiritilgan',
      bool(SEEN and 'zoom=18' in SEEN[0][0] and 'accept-language=uz' in SEEN[0][0]), SEEN[0][0] if SEEN else None)

# Boshqa kordinat — keshga tushmadi, upstream ga boradi
r = c.get('/api/geocode/reverse/?lat=41.311081&lon=69.279797')
check('boshqa kordinat ham ishlaydi', r.status_code == 200 and r.json().get('source') == 'live',
      f"source={r.json().get('source')}")
check('upstream ga jami 2 ta so\'rov', len(SEEN) == 2, f'upstream so\'rovlari: {len(SEEN)}')

print('\n=== Validatsiya ===')
check('lat yo\'q -> 400', c.get('/api/geocode/reverse/').status_code == 400)
check('lat noto\'g\'ri -> 400', c.get('/api/geocode/reverse/?lat=abc&lon=1').status_code == 400)
check('lat 999 -> 400', c.get('/api/geocode/reverse/?lat=999&lon=1').status_code == 400)
check('lon 999 -> 400', c.get('/api/geocode/reverse/?lat=41&lon=999').status_code == 400)
check('lat=0, lon=0 -> 200 (Gulf of Guinea)', c.get('/api/geocode/reverse/?lat=0&lon=0').status_code == 200)

# GEOCODER_URL bo'sh bo'lgan holat
import accounts.geocode as gc  # noqa: E402

saved = gc.settings.GEOCODER_URL
gc.settings.GEOCODER_URL = ''
r = c.get('/api/geocode/reverse/?lat=41.3&lon=69.2')
check('GEOCODER_URL yo\'q -> 503 (frontend koordinatga qaytadi)', r.status_code == 503, r.json())
gc.settings.GEOCODER_URL = saved

# upstream o'lganda
gc.settings.GEOCODER_URL = 'http://127.0.0.1:9/search'
r = c.get('/api/geocode/reverse/?lat=41.4&lon=69.3')
check('upstream o\'lsa -> 502 (500 emas)', r.status_code == 502, r.json())

srv.shutdown()
print(f'\nGeokodlash: {ok} / {ok + fail} passed')
raise SystemExit(1 if fail else 0)
