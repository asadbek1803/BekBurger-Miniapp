"""
Telegram initData authentication middleware.

Xavfsizlik qoidalari:
1. Telegram initData HMAC-SHA256 orqali tekshiriladi (faqat production).
2. DEV_MODE o'zi rol tekshiruvini OCHMAYDI — faqat initData tekshiruvini
   o'chiradi. Aks holda production'da kimgadir oshpaz paneli ochilib qoladi.
3. Rol tekshiruvi har bir so'rovda `RoleAccessMiddleware` orqali bajariladi.
"""
import hashlib
import hmac
import json
import time
import urllib.parse

from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

# Auth talab qilinmaydigan yo'llar
PUBLIC_PATHS = [
    '/admin/',
    '/static/',
    '/media/',
    '/api/auth/telegram/',
]

# Telegram bot orqali kirishda tekshiriladigan vaqt chegarasi
MAX_AUTH_AGE = 86400  # 24 soat


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Telegram WebApp initData HMAC-SHA256 orqali tekshiradi.
    Muvaffaqiyatli bo'lsa user dict, aks holda None qaytaradi.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop('hash', None)
        if not received_hash:
            return None

        # Vaqt chegarasi: eskirgan initData'ni rad etamiz
        auth_date = parsed.get('auth_date')
        if auth_date and time.time() - int(auth_date) > MAX_AUTH_AGE:
            return None

        # data-check-string (kalitlar tartiblangan, \n bilan birlashtirilgan)
        data_check_string = '\n'.join(f'{k}={v}' for k, v in sorted(parsed.items()))

        # Secret key = HMAC-SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            key=b'WebAppData',
            msg=bot_token.encode(),
            digestmod=hashlib.sha256,
        ).digest()

        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            return None

        return json.loads(parsed.get('user', '{}'))

    except Exception:
        return None


def get_or_create_telegram_user(user_data: dict):
    """Telegram ma'lumotlaridan foydalanuvchini oladi yoki yaratadi."""
    telegram_id = user_data.get('id')
    if not telegram_id:
        return None

    username = user_data.get('username') or f'tg_{telegram_id}'

    user, created = User.objects.get_or_create(
        telegram_id=telegram_id,
        defaults={
            'username': username[:150],
            'first_name': (user_data.get('first_name') or '')[:150],
            'last_name': (user_data.get('last_name') or '')[:150],
            'telegram_username': (user_data.get('username') or '')[:100],
            'role': 'customer',
        },
    )

    if not created:
        changed = []
        updates = {
            'first_name': (user_data.get('first_name') or '')[:150],
            'last_name': (user_data.get('last_name') or '')[:150],
            'telegram_username': (user_data.get('username') or '')[:100],
            'avatar_url': (user_data.get('photo_url') or '')[:200] or None,
        }
        for field, value in updates.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed.append(field)
        if changed:
            user.save(update_fields=changed)

    # Bloklangan foydalanuvchilar kirish olmaydi
    if not user.is_active:
        return None

    return user


def dev_mode_enabled() -> bool:
    """DEV_MODE faqat .env orqali yoqiladi — hech qachon DB dan emas."""
    return bool(getattr(settings, 'DEV_MODE', False))


class TelegramAuthMiddleware:
    """
    Session orqali Telegram foydalanuvchisini autentifikatsiya qiladi.
    DEV_MODE da `request.tg_user` ga sinov mijozini qo'yadi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(p) for p in PUBLIC_PATHS):
            return self.get_response(request)

        # DEV_MODE: sinov mijozini tayyorlab qo'yamiz.
        # DIQQAT: bu request.user ni almashtirmaydi — rol tekshiruvi
        # RoleAccessMiddleware da bajariladi.
        if dev_mode_enabled() and not request.user.is_authenticated:
            request.tg_user = get_or_create_telegram_user({
                'id': 999999999,
                'first_name': 'Test',
                'last_name': 'Mijoz',
                'username': 'dev_customer',
            })
        else:
            request.tg_user = None

        return self.get_response(request)


# ── Rol bilan kirish ─────────────────────────────────────────────────────
# Yo'l boshlanishi → ruxsat etilgan rollar
ROLE_PROTECTED_PREFIXES = [
    ('/dashboard/', {'director'}),
    ('/miniapp/director/', {'director'}),
    ('/miniapp/chef/', {'chef', 'director'}),
    ('/miniapp/courier/', {'courier', 'director'}),
]

# API yo'llari → ruxsat etilgan rollar
ROLE_PROTECTED_APIS = [
    ('/api/dashboard/', {'director'}),
    ('/api/staff/chef/', {'chef', 'director'}),
    ('/api/staff/courier/', {'courier', 'director'}),
]


def allowed_roles_for(path: str):
    for prefix, roles in ROLE_PROTECTED_PREFIXES + ROLE_PROTECTED_APIS:
        if path.startswith(prefix):
            return roles
    return None


class RoleAccessMiddleware:
    """
    Rolga qarab kirishni tekshiradi.

    Muhim: DEV_MODE rol tekshiruvini OCHMAYDI. Faqat `DEBUG` ham True bo'lsa
    dev-mode'da anonim foydalanuvchiga ruxsat beriladi (mahalliy ishlab
    chiqarish uchun qulay).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        roles = allowed_roles_for(request.path)
        if not roles:
            return self.get_response(request)

        user = request.user

        if user.is_authenticated:
            if user.is_superuser or user.role in roles:
                request.is_staff_panel = True
                return self.get_response(request)
            return self._deny(request, 403, 'Bu sahifa sizga ruxsat etilmagan')

        # DEV_MODE + DEBUG: lokal ishlab chiqarishda autentifikatsiyani
        # o'tkazib yuboramiz (view ichidagi dev-login logikasi ishlaydi).
        # Production'da bu yo'l FAQAT ishlaydi — xavfsizlik buzilmaydi.
        if dev_mode_enabled() and settings.DEBUG:
            return self.get_response(request)

        return self._deny(request, 401, 'Kirish talab qilinadi')

    @staticmethod
    def _deny(request, status, message):
        from django.http import JsonResponse

        wants_json = (
            request.path.startswith('/api/')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in (request.headers.get('Accept') or '')
        )
        if wants_json:
            return JsonResponse({'error': message}, status=status)

        from django.shortcuts import render
        return render(request, 'miniapp/error.html', {'message': message}, status=status)


class FrameAncestorsMiddleware:
    """
    `Content-Security-Policy: frame-ancestors ...` headerini qo'shadi.

    Telegram Mini App boshqa origin ichida ochilishi SHART, shuning uchun
    `X-Frame-Options` ishlatib bo'lmaydi (u faqat SAMEORIGIN/DENY qo'llaydi).
    CSP `frame-ancestors` esa aniqroq: faqat Telegram origin'lari (va dev uchun
    localhost) sahifani iframe'ga olishi mumkin bo'ladi.

    Ro'yxat ENV orqali o'zgartiriladi: CSP_FRAME_ANCESTORS=... (vergul bilan).
    """

    def __init__(self, get_response):
        self.get_response = get_response
        raw = getattr(settings, 'CSP_FRAME_ANCESTORS', None) or [
            'https://web.telegram.org',
            'https://*.telegram.org',
            'https://telegram.org',
        ]
        self.value = 'frame-ancestors ' + ' '.join(raw)

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault('Content-Security-Policy', self.value)
        return response


class AdminBrandingMiddleware:
    """
    Django admin sarlavhasini restoran nomidan dinamik qiladi.

    `admin.site.site_header` URLconf import qilganda bir marta o'qiladi, ya'ni
    nom o'zgartirilgandan keyin server qayta ishga tushmaguncha eskirgan bo'lardi.
    Shu sababli har admin so'rovida yangilanadi (`each_context` shu zahotiyoq
    qiymatni oladi).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/admin/'):
            try:
                from django.contrib import admin
                from . import settings_service
                name = settings_service.restaurant_name()
                admin.site.site_header = f'{name} — Boshqaruv'
                admin.site.site_title = name
                admin.site.index_title = 'Boshqaruv paneli'
            except Exception:
                pass
        return self.get_response(request)
