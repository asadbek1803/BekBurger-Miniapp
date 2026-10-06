"""
BekBurger Django project settings.

Barcha muhim qiymatlar .env orqali keladi (qarang: .env.example).
Production uchun qulay: Postgres va Redis faqat ENV orqali yoqiladi,
hozirgi SQLite ma'lumotlari saqlanib qoladi.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(key, default=False):
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(key, default=None):
    raw = os.getenv(key)
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(',') if item.strip()]


# ── Core ─────────────────────────────────────────────────────────────────
INSECURE_DEFAULT_SECRET = 'django-insecure-bekburger-secret-key-change-in-production-2024'

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY') or os.getenv('SECRET_KEY') or INSECURE_DEFAULT_SECRET

DEBUG = os.getenv('DEBUG', 'True').strip().lower() in ('1', 'true', 'yes', 'on')

# DEV_MODE — Telegram initData tekshiruvini o'chiradi va dev loginlarni yoqadi.
# Production'da MUTLAQA False bo'lishi kerak.
DEV_MODE = os.getenv('DEV_MODE', 'True').strip().lower() in ('1', 'true', 'yes', 'on')

# Default restoran nomi. Bo'sh bo'lsa 'BekBurger' qoladi.
RESTAURANT_NAME = os.getenv('RESTAURANT_NAME', 'BekBurger')

ALLOWED_HOSTS = _env_list(
    'ALLOWED_HOSTS',
    ['*'] if DEBUG else ['localhost', '127.0.0.1'],
)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Bot orqali xabar yuborish uchun (buyurtma holati xabarlari)
TELEGRAM_BOT_CHAT_ID = os.getenv('TELEGRAM_BOT_CHAT_ID', '')

# ── Production bootstrap tekshiruvi ──────────────────────────────────────
# Noto'g'ri sozlamada ilova ISHLAMASLIGI kerak — jimgina ishlamay qolmasin.
if not DEBUG:
    problems = []

    if SECRET_KEY == INSECURE_DEFAULT_SECRET:
        problems.append('DJANGO_SECRET_KEY o\'rnatilmagan (hozir standart qiymat ishlatilmoqda)')
    elif len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 8:
        problems.append('DJANGO_SECRET_KEY kamida 50 belgi va 8 ta unikal belgidan iborat bo\'lishi kerak')

    if DEV_MODE:
        problems.append('DEV_MODE=False bo\'lishi kerak (hozir Telegram auth tekshiruvi o\'chirilgan)')

    if '*' in ALLOWED_HOSTS:
        problems.append('ALLOWED_HOSTS da "*" bo\'lmasligi kerak')

    if problems:
        raise ImproperlyConfigured(
            'Production sozlamalari xato:\n  - ' + '\n  - '.join(problems)
            + '\n\n .env.example faylini ko\'rib, quyidagilarni to\'ldiring.'
        )

# ── Applications ─────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'channels',
    # Local apps
    'accounts',
    'menu',
    'orders',
    'miniapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.FrameAncestorsMiddleware',
    'accounts.middleware.AdminBrandingMiddleware',
    'accounts.middleware.TelegramAuthMiddleware',
    'accounts.middleware.RoleAccessMiddleware',
]

ROOT_URLCONF = 'bek_burger.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.app_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'bek_burger.wsgi.application'
ASGI_APPLICATION = 'bek_burger.asgi.application'

# ── Channels ─────────────────────────────────────────────────────────────
# Redis yo'q bo'lsa InMemory (faqat bitta process ishlaydi).
REDIS_URL = os.getenv('REDIS_URL', '')
if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# ── Xarita: plitkalar (tiles) va geokodlash ───────────────────────────────
# ESDA DIQQAT: `tile.openstreetmap.org` ishlatilmaydi. OSM serverlari
# bepul va ko'ngillilar hisobiga ishlaydi; Tile Usage Policy buzilsa butun
# IP bloklanadi ("osm.wiki/Blocked"). Standart tile serveri — CARTO.
MAP_TILE_URL = os.getenv(
    'MAP_TILE_URL',
    'https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'
    '?key=cb1_47sc_1_3b214a8c6cb5a56646f2cf46',
)
MAP_ATTRIBUTION = os.getenv(
    'MAP_ATTRIBUTION',
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    ' &copy; <a href="https://carto.com/attributions">CARTO</a>',
)
MAP_MAX_ZOOM = int(os.getenv('MAP_MAX_ZOOM', '19'))

# Reverse geocoding. Default — o'z serverimizdagi Nominatim
# (`/api/geocode/reverse` orqali proksi qilinadi). Public Nominatim
# production uchun mo'ljallanmagan va tez bloklaydi.
GEOCODER_URL = os.getenv('GEOCODER_URL', '').strip()
GEOCODER_MAX_ZOOM = int(os.getenv('GEOCODER_MAX_ZOOM', '18'))

# ── Database ─────────────────────────────────────────────────────────────
DB_ENGINE = os.getenv('DB_ENGINE', 'sqlite').strip().lower()

if DB_ENGINE in ('postgres', 'postgresql'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB', 'bekburger'),
            'USER': os.getenv('POSTGRES_USER', 'bekburger'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': int(os.getenv('POSTGRES_CONN_MAX_AGE', '60')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CACHES = {
    'default': {
        'BACKEND': os.getenv('CACHE_BACKEND', 'django.core.cache.backends.locmem.LocMemCache'),
        'LOCATION': 'bekburger',
        'TIMEOUT': 300,
    }
}

# ── Auth ─────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# ── I18N / TZ ────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'uz'
TIME_ZONE = os.getenv('TIME_ZONE', 'Asia/Tashkent')
USE_I18N = True
USE_TZ = True

# ── Static & Media ───────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Rasmlarni optimallashirish
IMAGE_MAX_SIZE_MB = int(os.getenv('IMAGE_MAX_SIZE_MB', '5'))

# ── Sessions ─────────────────────────────────────────────────────────────
SESSION_COOKIE_AGE = 86400 * 30  # 30 kun
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ── CSRF — Telegram Mini App iframe uchun ────────────────────────────────
CSRF_TRUSTED_ORIGINS = _env_list(
    'CSRF_TRUSTED_ORIGINS',
    [
        'https://*.ngrok.io',
        'https://*.ngrok-free.app',
        'https://*.trycloudflare.com',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    ],
)

# Telegram Mini App boshqa origin ichida ochilishi SHART, shuning uchun
# X_FRAME_OPTIONS o'rniga CSP `frame-ancestors` ishlatiladi (ancha aniq
# himoya: faqat Telegram origin'lari embed qila oladi).
X_FRAME_OPTIONS = 'ALLOWALL'

# security.W019 ni o'chiramiz — yuqoridagi CSP frame-ancestors uni almashtiradi.
SILENCED_SYSTEM_CHECKS = ['security.W019']

# Mini App'ni iframe'ga olishga ruxsat etiladigan origin'lar
CSP_FRAME_ANCESTORS = _env_list('CSP_FRAME_ANCESTORS', [
    'https://web.telegram.org',
    'https://*.telegram.org',
    'https://telegram.org',
])
if DEBUG:
    # Mahalliy ishlab chiqarishda Telegram orqali emas, to'g'ridan-to'gri ochish
    CSP_FRAME_ANCESTORS += ["'self'", 'http://localhost:8000', 'http://127.0.0.1:8000',
                            'http://localhost:8010', 'http://127.0.0.1:8010']

# ── Production xavfsizlik ────────────────────────────────────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
    X_CONTENT_TYPE_OPTIONS = 'nosniff'

# ── Logging ──────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[{asctime}] {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}