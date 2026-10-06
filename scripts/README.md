# Test va tekshiruv skriptlari

Bular ishlab chiqarish uchun mo'ljallangan tezkor tekshiruv skriptlari
(avtomatlashtirilgan CI emas — qo'lda ishga tushiriladi).

Har bir skript o'zini tozalaydi: yaratgan test ma'lumotlarini o'chiradi va
asli sozlamalarni tiklaydi. Shuning uchun xavfsiz, ko'p marta ishga tushirsa
bo'ladi.

| Skript | Nima tekshiradi | Qayerda ishlaydi |
|---|---|---|
| `smoke_test.py` | Barcha API endpoint'lar, rollar, narx himoyasi, buyurtma hayoti | Django test client (server kerak emas) |
| `ws_test.py` | WebSocket endpoint'lar: ruxsat, rad etish, ping/pong | Channels test communicator (server kerak emas) |
| `realtime_test.py` | Jonli broadcast: sozlamalar, banner, buyurtma holati, kuryer joylashuvi | Channels test communicator (server kerak emas) |
| `geocode_test.py` | Reverse geokodlash proksi: kesh, User-Agent, validatsiya, 502/503 holatlari | Fake Nominatim upstream (server kerak emas) |
| `dashboard_test.py` | Direktor paneli: stats, buyurtma holati, menyu/kategoriya/banner CRUD, validatsiya, reytinglar, ruxsat | Django test client (server kerak emas) |
| `dashboard_audit.py` | Dashboard statik audit: HTML id ↔ JS, endpointlar ↔ URLconf, methodlar, navigatsiya | Faqat faylni o'qish (server kerak emas) |
| `branding_test.py` | Dinamik brend: nom/valyuta o'zgarishi BARCHA sahifalarda darhol aks etadi | **Jonli server kerak** (`runserver 8010`) |
| `js_check.py` | Shablonlardagi `<script>` bloklarining sintaksisi (`node --check`) | node.js kerak, server kerak emas |

## Ishga tushirish

```powershell
# Windows
$env:PYTHONIOENCODING='utf-8'

# Server kerak bo'lmagan testlar
python scripts/smoke_test.py
python scripts/ws_test.py
python scripts/realtime_test.py
python scripts/geocode_test.py
python scripts/dashboard_test.py
python scripts/dashboard_audit.py

# JS sintaksisi (node.js o'rnatilgan bo'lishi kerak)
python scripts/js_check.py

# Dinamik brend — avval server ishga tushiring
python manage.py runserver 8010 --noreload
python scripts/branding_test.py
```

## Talablar

`branding_test.py` uchun `dev_customer` emas, **direktor/superuser** hisobi
ishlaydi: `admin` / `admin123` (boshqa ma'lumotlarda `TEST_ADMIN_USERNAME` /
`TEST_ADMIN_PASSWORD` bilan almashtiriladi). `smoke_test.py` uchun `setup_dev`
bajarilgan bo'lishi kerak:

```powershell
python manage.py setup_dev
```
