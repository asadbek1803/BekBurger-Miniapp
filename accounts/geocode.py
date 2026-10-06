"""
Reverse geocoding proksi.

Nomija: frontend `nominatim.openstreetmap.org` ga to'g'ridan-to'g'ri
so'rov yubormasin. Public Nominatim production uchun mo'ljallanmagan
(1 so'rov/soniya, tez bloklash). Bu view o'z serverimizdagi Nominatim'ga
proksi qiladi va javobni keshlaydi.

GET /api/geocode/reverse/?lat=41.2995&lon=69.2401
→ {"address": "...", "source": "cache"}

Sozlamalar (ENV):
  GEOCODER_URL — o'z Nominatim manzili, masalan
                http://127.0.0.1:8080/search  (ichki tarmoqda)
  Bo'sh bo'lsa endpoint `503` qaytaradi va frontend koordinatani
  ko'rsatishga qaytadi (biror narsa ishlashdan to'xtamaydi).
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24 * 7  # bir hafta — manzil o'zgarmaydi
CACHE_PREFIX = 'bb:geocode:v1'
TIMEOUT = 5


def _cache_key(lat: float, lng: float) -> str:
    # 4 ta kasr (~11 m) — GPS drift'ini hisobga oladi
    return f'{CACHE_PREFIX}:{lat:.4f}:{lng:.4f}'


@require_GET
def reverse(request):
    """Kordinatani manzilga o'giradi (Nominatim reverse)."""
    try:
        lat = float(request.GET.get('lat'))
        lng = float(request.GET.get('lon'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'lat va lon raqam bo\'lishi kerak'}, status=400)

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JsonResponse({'error': 'koordinata diapazondan tashqarida'}, status=400)

    base = (getattr(settings, 'GEOCODER_URL', '') or '').strip()
    if not base:
        return JsonResponse({
            'error': 'geokodlash sozlanmagan',
            'detail': 'GEOCODER_URL ENV o\'zgaruvchisini to\'ldiring',
        }, status=503)

    key = _cache_key(lat, lng)
    cached = cache.get(key)
    if cached is not None:
        return JsonResponse({'address': cached, 'source': 'cache'})

    params = urllib.parse.urlencode({
        'format': 'json',
        'lat': f'{lat:.6f}',
        'lon': f'{lng:.6f}',
        'zoom': getattr(settings, 'GEOCODER_MAX_ZOOM', 18),
        'addressdetails': 1,
        'accept-language': 'uz',
    })
    url = f'{base}?{params}'
    # Nominatim User-Agent talab qiladi — so'rov sarlavhasini aniq belgilaymiz.
    req = urllib.request.Request(url, headers={
        'User-Agent': getattr(settings, 'GEOCODER_USER_AGENT',
                              'BekBurger/1.0 (+https://t.me/your_bot)'),
        'Accept': 'application/json',
    })

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        address = (data.get('display_name') or '').strip()
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        logger.warning('Geokodlash muvaffaqiyatsiz: %s', exc)
        return JsonResponse({'error': 'geokodlash vaqtincha ishlamaydi'}, status=502)

    if address:
        cache.set(key, address, CACHE_TTL)
    return JsonResponse({'address': address, 'source': 'live'})
