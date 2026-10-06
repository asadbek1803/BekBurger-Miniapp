"""
Dashboard statik audit: HTML id vs JS muroajati, endpointlar, methodlar.

Server kerak emas — faqat dashboard.html ni o'qib tekshiradi.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, 'miniapp', 'templates', 'miniapp', 'director', 'dashboard.html')
URLS = os.path.join(ROOT, 'bek_burger', 'urls.py')
API = os.path.join(ROOT, 'miniapp', 'dashboard_api.py')

html = open(TPL, encoding='utf-8').read()
urls = open(URLS, encoding='utf-8').read()
api_src = open(API, encoding='utf-8').read()

fails = []
oks = []


def check(name, cond, extra=''):
    (oks if cond else fails).append(name)
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{(' — ' + str(extra)) if extra else ''}")


# ── 1. HTML'dagi id'lar ──────────────────────────────────────────────────
html_ids = set(re.findall(r'\bid="([^"]+)"', html))

# ── 2. JS'dagi getElementById muroajatlari ───────────────────────────────
js_ids = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", html))

missing = sorted(js_ids - html_ids)
check(f"JS getElementById({len(js_ids)} ta) — hammasi HTML'da bor", not missing, missing)

# ── 3. querySelector('#id') va $('#id') ───────────────────────────────────
sel_ids = set(re.findall(r"""querySelector\(['"]#([A-Za-z0-9_-]+)['"]\)""", html))
missing2 = sorted(sel_ids - html_ids)
check(f"querySelector('#id') ({len(sel_ids)} ta) — hammasi HTML'da bor", not missing2, missing2)

# ── 4. Sahifa bo'limlari: SECTION_TITLES vs navigatsiya ─────────────────
titles_blk = html[html.find('const SECTION_TITLES'):html.find('const SECTION_ICONS')]
titles = set(re.findall(r"(\w+):\s*'", titles_blk))
show_fn = html[html.find('function showSection'):]
show_fn = show_fn[:show_fn.find('\n}')]
sec_fn = set(re.findall(r"if\s*\(\s*name\s*===?\s*'([^']+)'", show_fn))
nav = set(re.findall(r"data-section=\"(\w+)\"", html))
print(f'  [info] titles={sorted(titles)}')
print(f'  [info] showSection={sorted(sec_fn)}')
print(f'  [info] nav(data-section)={sorted(nav)}')
check("SECTION_TITLES == showSection shartlari", titles == sec_fn,
      f"faqat titles'da: {sorted(titles - sec_fn)} / faqat showSection'da: {sorted(sec_fn - titles)}")
check("Har bir nav elementi showSection'da ishlovchi", nav <= (sec_fn | titles),
      f"ishlanmaydigan: {sorted(nav - (sec_fn | titles))}")

# ── 5. Frontend chaqiradigan endpointlar URLconf'da bormi ───────────────
called = set()
for m in re.finditer(r"""['"`](/api/dashboard/[^'"`]*)['"`]""", html):
    called.add(m.group(1))
# query string'ni olib tashlaymiz, ${...} ni __var__ ga
norm = set()
for c in called:
    c = c.split('?')[0]
    c = re.sub(r'\$\{[^}]+\}', '__var__', c)
    norm.add(c)

# URLconf satrlarini tekislash
flat = re.sub(r'\s+', '', urls)
route_paths = {r.lstrip('/') for r in re.findall(r"path\('([^']+)'", flat)}
route_paths |= {r.lstrip('/') for r in re.findall(r"path\(\s*'([^']+)'", open(URLS, encoding='utf-8').read())}


def urlconf_has(path):
    p = path.lstrip('/')
    if p in route_paths:
        return True
    if '__var__' in p:
        prefix, _, suffix = p.partition('__var__')
        for r in route_paths:
            if r.startswith(prefix) and r.endswith(suffix):
                return True
    return False


for p in sorted(norm):
    check(f"URLconf'da bor: {p}", urlconf_has(p))

# Teskari: URLconf'da bor, lekin dashboard ishlatmaydi
used = {p.lstrip('/') for p in norm}
for r in sorted(route_paths):
    if not r.startswith('api/dashboard/'):
        continue
    if '<' in r:
        prefix, _, rest = r.partition('<')       # 'api/x/<int:id>/'
        suffix = rest.partition('>')[2]           # '/'
        if any(u.startswith(prefix) and u.endswith(suffix) for u in used):
            continue
        check(f"URLconf'da bor lekin dashboard ishlatmaydi: /{r}", False)
        continue
    if r.rstrip('/') in {u.rstrip('/') for u in used}:
        continue
    check(f"URLconf'da bor lekin dashboard ishlatmaydi: /{r}", False)

# ── 6. method mosligi: api()/fetch() da ishlatilgan method backend'da bormi ─
detail_methods = {
    '/api/dashboard/orders/': ('GET', 'POST'),
    '/api/dashboard/menu/items/': ('GET', 'POST'),
    '/api/dashboard/menu/categories/': ('GET', 'POST'),
    '/api/dashboard/banners/': ('GET', 'POST'),
    '/api/dashboard/users/': ('GET', 'POST'),
    '/api/dashboard/settings/': ('GET', 'POST'),
}
detail = {
    'order_status': ("request.method == 'POST'", ['POST']),
    'menu_item_detail': ("request.method in ('PUT', 'PATCH', 'POST')", ['PUT', 'PATCH', 'POST']),
    'category_detail': (None, None),
    'user_detail': (None, None),
}

print()
print('=== Methodlar ===')
# toggleAvail PUT -> item detail PUT qabul qiladi (POST ham) — OK
check("toggleAvail PUT -> menu_item_detail PUT qabul qiladi",
      "request.method in ('PUT', 'PATCH', 'POST')" in api_src)
# toggleCatActive POST -> category detail
cat_fn = api_src[api_src.find('def dashboard_category_detail'):]
cat_fn = cat_fn[:cat_fn.find('\ndef ')]
check("toggleCatActive POST -> category_detail POST qabul qiladi",
      "'POST'" in cat_fn and "'PUT'" in cat_fn, f"accepted: {re.findall(r'.*method.*', cat_fn)[:2]}")
# user detail PUT/DELETE
usr_fn = api_src[api_src.find('def dashboard_user_detail'):]
usr_fn = usr_fn[:usr_fn.find('\ndef ')]
check("saveStaff PUT -> user_detail PUT qabul qiladi", "'PUT'" in usr_fn)
check("deactivateUser DELETE -> user_detail DELETE qabul qiladi", "'DELETE'" in usr_fn)

print()
print('=== Xavfsizlik ===')
check("Barcha dashboard API'lar @csrf_exempt (Telegram Mini App token orqali)",
      api_src.count('@csrf_exempt') >= 10, f"{api_src.count('@csrf_exempt')} ta")
check("require_admin barcha dashboard view'larda", api_src.count('@require_admin') >= 10,
      f"{api_src.count('@require_admin')} ta")

# CSRF: require_admin + csrf_exempt birga — himoya qayerda?
check("require_admin ichida CSRF/rol tekshiruvi bor",
      'CSRF' in api_src or 'staff_required' in api_src or 'role' in api_src)

print()
print(f"Audit: {len(oks)} / {len(oks) + len(fails)} passed")
if fails:
    print('\nMUAMMOLAR:')
    for f in fails:
        print(f'  - {f}')
sys.exit(1 if fails else 0)
