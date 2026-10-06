from django.db import migrations

# accounts/models.py dagi DEFAULT_SETTINGS bilan bir xil
NEW_SETTINGS = [
    ('telegram_miniapp_url', '', 'Mini App URL', 'ngrok yoki production URL', 'text'),
    ('app_tagline', 'Tez va mazali yetkazib beramiz', 'Slogan',
     'Ilova ostidagi qisqa izoh', 'text'),
    ('restaurant_address', '', 'Restoran manzili',
     'Xaritada boshlang\'ich nuqta sifatida ishlatiladi', 'text'),
    ('currency', "so'm", 'Valyuta', 'Narxlardan keyingi belgi', 'text'),
    ('free_delivery_from', '0', 'Bu summadan katta — bepul',
     '0 bo\'lsa o\'chirilgan. Masalan: 100000', 'number'),
    ('banner_autoplay', 'True', 'Bannerlarni avtomatik almashtirish', '', 'boolean'),
    ('banner_interval', '5', 'Banner almashish vaqti (soniya)', 'Kamida 3 sekund', 'number'),
    ('order_cancel_allowed', 'True', 'Mijoz buyurtmani bekor qila oladi',
     'Faqat "yangi" holatdagina', 'boolean'),
]


def seed_settings(apps, schema_editor):
    """
    Yangi dinamik sozlamalarni qo'shadi.
    Mavjud qiymatlar (mijozning o'zgartirganlari) tegilmaydi.
    """
    AppSettings = apps.get_model('accounts', 'AppSettings')
    for key, value, label, description, setting_type in NEW_SETTINGS:
        AppSettings.objects.get_or_create(
            key=key,
            defaults={
                'value': value,
                'label': label,
                'description': description,
                'setting_type': setting_type,
            },
        )

    # restaurant_name sozlamasi bo'lmasa — 'BekBurger' bilan yaratamiz
    AppSettings.objects.get_or_create(
        key='restaurant_name',
        defaults={
            'value': 'BekBurger',
            'label': 'Restoran nomi',
            'description': 'Ilova bo\'limlarida ko\'rsatiladigan nom.',
            'setting_type': 'text',
        },
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_appsettings'),
    ]

    operations = [
        migrations.RunPython(seed_settings, noop),
    ]