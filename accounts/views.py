"""
Accounts views — Telegram authentication API.
"""
import json
from django.conf import settings
from django.contrib.auth import login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .middleware import verify_telegram_init_data, get_or_create_telegram_user


@csrf_exempt
@require_POST
def telegram_auth(request):
    """
    POST /api/auth/telegram/
    Body: { "initData": "..." }
    Validates Telegram initData, creates/gets user, logs in via session.
    """
    try:
        body = json.loads(request.body)
        init_data = body.get('initData', '')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON noto\'g\'ri'}, status=400)

    # DEV_MODE: skip validation
    if settings.DEV_MODE:
        # Try to parse user data anyway (if provided)
        if init_data:
            import urllib.parse
            parsed = dict(urllib.parse.parse_qsl(init_data))
            try:
                import json as _json
                user_data = _json.loads(parsed.get('user', '{}'))
            except Exception:
                user_data = {}
        else:
            user_data = {
                'id': 999999999,
                'first_name': 'Test',
                'last_name': 'Mijoz',
                'username': 'test_customer',
            }

        user = get_or_create_telegram_user(user_data) if user_data.get('id') else None
        if not user:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user, _ = User.objects.get_or_create(
                username='dev_customer',
                defaults={
                    'telegram_id': 999999999,
                    'first_name': 'Test',
                    'last_name': 'Mijoz',
                    'role': 'customer',
                }
            )
    else:
        # Production: verify initData
        bot_token = settings.TELEGRAM_BOT_TOKEN
        user_data = verify_telegram_init_data(init_data, bot_token)
        if not user_data:
            return JsonResponse({'error': 'Telegram autentifikatsiya xatosi'}, status=401)
        user = get_or_create_telegram_user(user_data)
        if not user:
            return JsonResponse({'error': 'Foydalanuvchi topilmadi'}, status=400)

    # Log in user via Django session
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    return JsonResponse({
        'success': True,
        'user': {
            'id': user.id,
            'telegram_id': user.telegram_id,
            'name': user.display_name,
            'role': user.role,
            'role_display': user.get_role_display(),
        }
    })


def profile(request):
    """GET /api/auth/profile/ — current user info."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Kirish talab qilinadi'}, status=401)

    user = request.user
    return JsonResponse({
        'id': user.id,
        'telegram_id': user.telegram_id,
        'name': user.display_name,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.telegram_username,
        'role': user.role,
        'role_display': user.get_role_display(),
        'phone': user.phone,
    })
