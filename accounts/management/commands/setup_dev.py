"""
Management command: setup_dev

Development uchun dastlabki ma'lumotlarni sozlaydi.
Takroriy ishga tushirsa xavfsiz (hech narsa o'chmaydi, o'zgartirilmaydi).

Ishlatish:
    python manage.py setup_dev
"""
import sys

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

# Windows'da UTF-8 chiqishni majburlash
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

User = get_user_model()

STAFF = [
    ('admin', 'admin123', 'Admin', 'BekBurger', 'director', 100000001),
    ('dev_customer', 'customer123', 'Test', 'Mijoz', 'customer', 999999999),
    ('dev_chef', 'chef123', 'Test', 'Oshpaz', 'chef', 100000002),
    ('dev_courier', 'courier123', 'Test', 'Kuryer', 'courier', 100000003),
]

DEFAULT_BANNERS = [
    {
        'title': 'BekBurger Classic',
        'subtitle': 'Molpani go\'sht, cheddar pishig\'i va maxsus sous',
        'label': '🔥 ENG KO\'P BUYURTMA',
        'color_start': '#E63946', 'color_end': '#F4A261',
        'button_text': 'Menyuni ko\'rish', 'button_action': 'scroll_menu',
        'order': 0, 'autoplay_delay': 5,
    },
    {
        'title': 'Yetkazib berish 30 daqiqada',
        'subtitle': 'Toshkent bo\'ylab issiq va mazali',
        'label': '🛵 TEZ YETKAZIB BERISH',
        'color_start': '#2A9D8F', 'color_end': '#E9C46A',
        'button_text': 'Manzil kiritish', 'button_action': 'none',
        'order': 1, 'autoplay_delay': 6,
    },
    {
        'title': 'Birinchi buyurtma uchun -10%',
        'subtitle': 'Promo kod: BIRINCHI',
        'label': '🎁 CHEGIRMA',
        'color_start': '#6A4C93', 'color_end': '#C05D7E',
        'button_text': 'Qabul qilish', 'button_action': 'none',
        'order': 2, 'autoplay_delay': 6,
    },
]


class Command(BaseCommand):
    help = "Development uchun dastlabki ma'lumotlarni sozlash"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('BekBurger dev sozlamalarini yuklamoqda...')

        # ── Foydalanuvchilar ──
        for username, password, first, last, role, tg_id in STAFF:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'telegram_id': tg_id,
                    'first_name': first,
                    'last_name': last,
                    'role': role,
                },
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f'[OK] {role}: {username} / {password}'))

        # Admin'ga superuser huquqi
        admin_user = User.objects.filter(username='admin').first()
        if admin_user and not admin_user.is_superuser:
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.role = 'director'
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('[OK] admin — superuser huquqi berildi'))

        # ── Sozlamalar (restaurant_name = BekBurger) ──
        from accounts.models import AppSettings
        created_keys = AppSettings.seed_defaults()
        if created_keys:
            self.stdout.write(self.style.SUCCESS(f'[OK] {len(created_keys)} ta sozlama yaratildi'))

        # ── Menyu ──
        from menu.models import Category, MenuItem, Banner
        if not Category.objects.exists():
            try:
                call_command('loaddata', 'initial_menu', verbosity=0)
                self.stdout.write(self.style.SUCCESS('[OK] Menyu yuklandi'))
            except Exception as e:
                self.stdout.WARNING(f'[WARN] Menyu yuklanmadi: {e}')
        else:
            self.stdout.write('Menyu allaqachon mavjud — o\'tkazib yuborildi')

        # ── Bannerlar ──
        if not Banner.objects.exists():
            for data in DEFAULT_BANNERS:
                Banner.objects.create(**data)
            self.stdout.write(
                self.style.SUCCESS(f'[OK] {len(DEFAULT_BANNERS)} ta banner yaratildi')
            )
        else:
            self.stdout.write('Bannerlar allaqachon mavjud — o\'tkazib yuborildi')

        # ── Natija ──
        base = 'http://127.0.0.1:8000'
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 52))
        self.stdout.write(self.style.SUCCESS('Dev muhiti tayyor!'))
        self.stdout.write(self.style.SUCCESS('=' * 52))
        self.stdout.write('')
        self.stdout.write(f'  Mijoz ilovasi : {base}/miniapp/customer/')
        self.stdout.write(f'  Dashboard     : {base}/dashboard/  (admin / admin123)')
        self.stdout.write(f'  Oshpaz paneli : {base}/miniapp/chef/   (dev_chef / chef123)')
        self.stdout.write(f'  Kuryer paneli : {base}/miniapp/courier/ (dev_courier / courier123)')
        self.stdout.write(f'  Django admin  : {base}/admin/')
        self.stdout.write('')