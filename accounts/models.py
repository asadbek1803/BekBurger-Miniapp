"""
Custom User model for BekBurger.
Roles: director, chef, courier, customer
Authentication via Telegram initData.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """Extended user model with Telegram integration and role system."""

    ROLE_CHOICES = [
        ('director', 'Direktor'),
        ('chef', 'Oshpaz'),
        ('courier', 'Kuryer'),
        ('customer', 'Mijoz'),
    ]

    telegram_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        verbose_name='Telegram ID',
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer',
        verbose_name='Rol',
    )
    phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        verbose_name='Telefon raqami',
    )
    telegram_username = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='Telegram username',
    )
    avatar_url = models.URLField(
        null=True,
        blank=True,
        verbose_name='Avatar URL',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Ro\'yxatdan o\'tgan vaqt')

    class Meta:
        verbose_name = 'Foydalanuvchi'
        verbose_name_plural = 'Foydalanuvchilar'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    @property
    def display_name(self):
        """Return best available display name."""
        if self.first_name:
            name = self.first_name
            if self.last_name:
                name += f' {self.last_name}'
            return name
        if self.telegram_username:
            return f'@{self.telegram_username}'
        return f'User #{self.telegram_id}'

    def is_director(self):
        return self.role == 'director'

    def is_chef(self):
        return self.role == 'chef'

    def is_courier(self):
        return self.role == 'courier'

    def is_customer(self):
        return self.role == 'customer'


def _broadcast_config():
    """Sozlama o'zgarganini ochiq ilovalarga yuborish (xato bo'lsa jim qoladi)."""
    try:
        from orders.broadcast import broadcast_settings_update
        broadcast_settings_update()
    except Exception:
        pass


class AppSettings(models.Model):
    """Key-value store for application settings (bot token, etc.)"""

    SETTING_TYPES = [
        ('text', 'Matn'),
        ('password', 'Parol/Token'),
        ('number', 'Raqam'),
        ('boolean', 'Ha/Yo\'q'),
    ]

    key = models.CharField(max_length=100, unique=True, verbose_name='Kalit')
    value = models.TextField(blank=True, default='', verbose_name='Qiymat')
    label = models.CharField(max_length=200, verbose_name='Nom')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    setting_type = models.CharField(
        max_length=20,
        choices=SETTING_TYPES,
        default='text',
        verbose_name='Tur',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sozlama'
        verbose_name_plural = 'Sozlamalar'
        ordering = ['key']

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keshni darhol tozalash — frontend o'zgarishni darhol ko'radi
        try:
            from .settings_service import refresh
            refresh()
        except Exception:
            pass
        # Ochiq ilovalarni jonli xabardor qilish (nomi, narx, banner va h.k.)
        _broadcast_config()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        try:
            from .settings_service import refresh
            refresh()
        except Exception:
            pass
        _broadcast_config()

    @classmethod
    def get(cls, key, default=''):
        """Get setting value by key."""
        from .settings_service import get as _get
        return _get(key, default)

    @classmethod
    def set(cls, key, value):
        """Set setting value by key (yaratadi yoki yangilaydi)."""
        obj, _ = cls.objects.get_or_create(key=key)
        obj.value = str(value)
        obj.save()
        return obj

    @classmethod
    def seed_defaults(cls):
        """DEFAULT_SETTINGS dagi yo'q sozlamalarni yaratadi. Mavjudlarni tegmaydi."""
        created = []
        for key, value, label, desc, stype in DEFAULT_SETTINGS:
            obj, was_created = cls.objects.get_or_create(
                key=key,
                defaults={
                    'value': value,
                    'label': label,
                    'description': desc,
                    'setting_type': stype,
                },
            )
            if not was_created:
                # Yangi default qo'shilgan bo'lsa, izoh/mavzu yangilanadi,
                # lekin qiymat (mijozning o'zgartirgani) saqlanadi.
                changed = False
                if not obj.label:
                    obj.label = label
                    changed = True
                if not obj.description:
                    obj.description = desc
                    changed = True
                if changed:
                    obj.save()
            else:
                created.append(key)
        if created:
            from .settings_service import refresh
            refresh()
        return created


DEFAULT_SETTINGS = [
    # ── Telegram ──
    ('telegram_bot_token', '', 'Telegram Bot Token', 'BotFather dan olingan token', 'password'),
    ('telegram_miniapp_url', '', 'Mini App URL', 'ngrok yoki production URL', 'text'),

    # ── Restoran ──
    ('restaurant_name', 'BekBurger', 'Restoran nomi',
     'Ilova bo\'limlarida ko\'rsatiladigan nom. Bo\'sh qoldirilsa "BekBurger" qoladi.', 'text'),
    ('app_tagline', 'Tez va mazali yetkazib beramiz', 'Slogan',
     'Ilova ostidagi qisqa izoh', 'text'),
    ('restaurant_address', '', 'Restoran manzili', 'Xaritada boshlang\'ich nuqta sifatida ishlatiladi', 'text'),
    ('phone', '', 'Telefon raqami', 'Mijozlar bilan bog\'lanish uchun', 'text'),
    ('working_hours', '09:00 - 23:00', 'Ish vaqti',
     'Masalan: 09:00 - 23:00. Yopiq paytda buyurtma berilmaydi.', 'text'),
    ('currency', "so'm", 'Valyuta', 'Narxlardan keyingi belgi', 'text'),

    # ── Yetkazib berish ──
    ('delivery_fee', '10000', 'Yetkazib berish narxi',
     'Har bir buyurtma uchun qo\'shimcha haq (valyuta: yuqoridagi "Valyuta")', 'number'),
    ('free_delivery_from', '0', 'Bu summadan katta — bepul',
     '0 bo\'lsa o\'chirilgan. Masalan: 100000', 'number'),
    ('min_order_amount', '20000', 'Minimal buyurtma summasi',
     'Bu summadan kam bo\'lsa buyurtma qabul qilinmaydi. 0 = o\'chirilgan', 'number'),
    ('max_delivery_km', '15', 'Maks. yetkazib berish masofasi (km)', '', 'number'),
    ('auto_assign_courier', 'False', 'Kuryerni avtomatik belgilash',
     'Tayyor bo\'lgan buyurtmani birinchi bo\'sh kuryerga avtomatik berish', 'boolean'),

    # ── Bannerlar ──
    ('banner_autoplay', 'True', 'Bannerlarni avtomatik almashtirish', '', 'boolean'),
    ('banner_interval', '5', 'Banner almashish vaqti (soniya)', 'Kamida 3 sekund', 'number'),

    # ── Tizim ──
    ('dev_mode', 'True', 'DEV rejimi',
     'True bo\'lsa Telegram auth tekshirilmaydi. Production uchun False qiling.', 'boolean'),
    ('order_cancel_allowed', 'True', 'Mijoz buyurtmani bekor qila oladi',
     'Faqat "yangi" holatdagina', 'boolean'),
]
