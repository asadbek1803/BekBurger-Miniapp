"""Miniapp views — Telegram Mini App sahifalari va direktor dashboard."""
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect, render

from accounts import settings_service


def _page_context(request, page):
    """Barcha mini app sahifalari uchun umumiy kontekst (dinamik sozlamalar bilan)."""
    user = request.user
    return {
        'dev_mode': settings.DEV_MODE,
        'user': user if user.is_authenticated else None,
        'page': page,
        'config': settings_service.public_config(),
        'restaurant_name': settings_service.restaurant_name(),
        'delivery_fee': settings_service.delivery_fee(),
        'currency': settings_service.get('currency', "so'm"),
    }


def index(request):
    """Bosh sahifa — mijoz mini app'iga yo'naltiradi."""
    return redirect('miniapp:customer')


def customer_view(request):
    """Mijoz Mini App."""
    if not settings.DEV_MODE:
        user = request.user
        if not user.is_authenticated:
            return render(request, 'miniapp/error.html', {
                'message': 'Ishga tushish uchun Telegram orqali kiring',
            }, status=401)
        # Xodimlar mijoz ilovasidan foydalanishi mumkin (sinov uchun),
        # lekin production'da 403 beriladi.
        if user.role not in ('customer', 'director') and not user.is_superuser:
            return render(request, 'miniapp/error.html', {
                'message': 'Bu sahifa faqat mijozlar uchun',
            }, status=403)

    return render(request, 'miniapp/customer/index.html', _page_context(request, 'customer'))


def director_dashboard(request):
    """Direktor dashboardi."""
    user = request.user

    if not user.is_authenticated:
        # DEV_MODE: avtomatik admin sifatida kirish
        if settings.DEV_MODE and settings.DEBUG:
            User = get_user_model()
            admin_user = User.objects.filter(
                is_superuser=True
            ).first() or User.objects.filter(username='admin').first()
            if admin_user:
                login(request, admin_user, backend='django.contrib.auth.backends.ModelBackend')
                user = admin_user
            else:
                return render(request, 'miniapp/error.html', {
                    'message': "Avval `python manage.py setup_dev` buyrug'ini ishga tushiring",
                }, status=403)
        else:
            return redirect('/admin/login/?next=/dashboard/')

    if not (user.is_superuser or user.role == 'director'):
        return render(request, 'miniapp/error.html', {
            'message': 'Bu sahifa faqat direktorlar uchun',
        }, status=403)

    context = _page_context(request, 'director')
    return render(request, 'miniapp/director/dashboard.html', context)


def chef_view(request):
    """Oshpaz paneli."""
    return _staff_page(request, 'chef', ('chef', 'director'), 'miniapp/chef/index.html', 'chef_name')


def courier_view(request):
    """Kuryer paneli."""
    return _staff_page(request, 'courier', ('courier', 'director'), 'miniapp/courier/index.html', 'courier_name')


def _staff_page(request, page, roles, template, name_key):
    """Oshpaz va kuryer sahifalari uchun umumiy qism."""
    user = request.user

    if not settings.DEV_MODE and not (
        user.is_authenticated and (user.is_superuser or user.role in roles)
    ):
        return render(request, 'miniapp/error.html', {
            'message': f'Bu sahifa faqat {", ".join(roles)} uchun',
        }, status=403)

    restaurant = settings_service.restaurant_name()
    context = _page_context(request, page)
    context[name_key] = user.display_name if user.is_authenticated else restaurant
    return render(request, template, context)