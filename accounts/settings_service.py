"""
Typed accessors for AppSettings.

Natija: frontend va backend bo'lib ikkala tomondan bitta manbadan o'qiydi.
Qiymatlar 30 sekundlik keshda saqlanadi va `AppSettings` saqlanganda
kesh darhol tozalanadi (dashboard orqali o'zgarish darhol ko'rinadi).
"""
from datetime import datetime, time as dtime

from django.conf import settings as dj_settings
from django.core.cache import cache

from .models import AppSettings, DEFAULT_SETTINGS

CACHE_KEY = 'bb:appsettings:v3'
CACHE_TTL = 30

# Xarita sozlamalari sozlamalar bazasida emas, settings.py da (ENV).
# Bu fallback'lar settings.py ni import qila olmagan holat uchun.
DEFAULT_TILE_URL = ('https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'
                    '?key=cb1_47sc_1_3b214a8c6cb5a56646f2cf46')
DEFAULT_ATTRIBUTION = ('&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                       ' &copy; <a href="https://carto.com/attributions">CARTO</a>')

# DEFAULT_SETTINGS dan tez lug'at: {key: value}
DEFAULTS = {row[0]: row[1] for row in DEFAULT_SETTINGS}

TRUTHY = ('1', 'true', 'yes', 'on', 'ha')


def _load_all() -> dict:
    """Barcha sozlamalarni bitta dict ko'rinishida qaytaradi."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    data = dict(DEFAULTS)
    try:
        for row in AppSettings.objects.all().only('key', 'value'):
            data[row.key] = row.value
    except Exception:
        # DB tayyor emas (migrate qilinmagan) — defaultlardan foydalanamiz
        pass

    cache.set(CACHE_KEY, data, CACHE_TTL)
    return data


def refresh() -> None:
    """Keshni tozalash — sozlamalar saqlanganda chaqiriladi."""
    cache.delete(CACHE_KEY)


def get(key: str, default=None):
    """Sozlama qiymatini qaytaradi. Bo'sh bo'lsa default ishlatiladi."""
    value = _load_all().get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        fallback = DEFAULTS.get(key, '') if default is None else default
        return fallback
    return value


def get_int(key: str, default: int = 0) -> int:
    raw = get(key)
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    raw = get(key)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def get_bool(key: str, default: bool = False) -> bool:
    raw = str(get(key)).strip().lower()
    if raw in TRUTHY:
        return True
    if raw in ('0', 'false', 'no', 'off', 'yo\'q'):
        return False
    return default


# ── Aniq o'qishlar (to'g'ri tip bilan) ──────────────────────────────────
def restaurant_name() -> str:
    """Restoran nomi. Default — 'BekBurger'."""
    name = str(get('restaurant_name')).strip()
    if not name:
        return getattr(dj_settings, 'RESTAURANT_NAME', '') or 'BekBurger'
    return name


def tagline() -> str:
    return str(get('app_tagline')).strip()


def currency() -> str:
    return str(get('currency')).strip() or "so'm"


def delivery_fee() -> int:
    return max(0, get_int('delivery_fee', 10000))


def free_delivery_from() -> int:
    """Bu summadan katta buyurtmalar yetkazib berish bepul. 0 = o'chirilgan."""
    return max(0, get_int('free_delivery_from', 0))


def min_order_amount() -> int:
    return max(0, get_int('min_order_amount', 0))


def working_hours() -> str:
    return str(get('working_hours')).strip() or '09:00 - 23:00'


def parse_working_hours(value: str):
    """
    '09:00 - 23:00' -> (time(9,0), time(23,0))
    Chiqsa (None, None) qaytaradi.
    """
    try:
        raw = (value or '').replace('–', '-').replace('—', '-')
        if '-' not in raw:
            return None, None
        left, right = raw.split('-', 1)
        def _p(part):
            part = part.strip()
            hh, _, mm = part.partition(':')
            return dtime(int(hh), int(mm or 0))
        return _p(left), _p(right)
    except (ValueError, TypeError):
        return None, None


def is_open_now() -> bool:
    """Hozir restoran ochiqmi."""
    start, end = parse_working_hours(working_hours())
    if not start or not end:
        return True  # Sozlama noto'g'ri bo'lsa ochiq deb hisoblaymiz
    now = datetime.now().time()
    if start <= end:
        return start <= now <= end
    # Tungi ish rejimi: 18:00 - 03:00
    return now >= start or now <= end


def banner_autoplay() -> bool:
    return get_bool('banner_autoplay', True)


def banner_interval() -> int:
    """Banner almashish intervali (soniya). 3 s dan kam bo'lmaydi."""
    return max(3, get_int('banner_interval', 5))


def order_cancel_allowed() -> bool:
    return get_bool('order_cancel_allowed', True)


def map_config() -> dict:
    """
    Xarita sozlamalari (frontend uchun).
    Boshqaruv `bek_burger/settings.py` da, ENV orqali almashtiriladi.
    """
    return {
        'tile_url': getattr(dj_settings, 'MAP_TILE_URL', '') or DEFAULT_TILE_URL,
        'attribution': getattr(dj_settings, 'MAP_ATTRIBUTION', '') or DEFAULT_ATTRIBUTION,
        'max_zoom': getattr(dj_settings, 'MAP_MAX_ZOOM', 19),
    }


def public_config() -> dict:
    """
    Frontend uchun yagona dinamik konfiguratsiya.
    Barcha mini app'lar shu endpoint orqali sozlamalarni oladi.
    """
    fee = delivery_fee()
    cfg = {
        'restaurant_name': restaurant_name(),
        'tagline': tagline(),
        'currency': currency(),
        'phone': str(get('phone')).strip(),
        'address': str(get('restaurant_address')).strip(),
        'working_hours': working_hours(),
        'is_open': is_open_now(),
        'delivery_fee': fee,
        'free_delivery_from': free_delivery_from(),
        'min_order_amount': min_order_amount(),
        'max_delivery_km': get_float('max_delivery_km', 15),
        'banner_autoplay': banner_autoplay(),
        'banner_interval': banner_interval(),
        'order_cancel_allowed': order_cancel_allowed(),
        'auto_assign_courier': get_bool('auto_assign_courier', False),
    }
    cfg.update(map_config())
    return cfg