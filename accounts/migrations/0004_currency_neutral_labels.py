"""Sozlama yorliqlarini valyutaga bog'liq emas qilish (so'm -> umumiy)."""
from django.db import migrations

RENAMES = {
    'delivery_fee': (
        'Yetkazib berish narxi',
        'Har bir buyurtma uchun qo\'shimcha haq (valyuta: yuqoridagi "Valyuta")',
    ),
    'min_order_amount': (
        'Minimal buyurtma summasi',
        'Bu summadan kam bo\'lsa buyurtma qabul qilinmaydi. 0 = o\'chirilgan',
    ),
}


def apply_labels(apps, schema_editor):
    AppSettings = apps.get_model('accounts', 'AppSettings')
    for key, (label, description) in RENAMES.items():
        AppSettings.objects.filter(key=key).update(label=label, description=description)


def revert_labels(apps, schema_editor):
    # Matnni qaytarish kerak emas — qiymatlar o'zgarmagan.
    pass


class Migration(migrations.Migration):

    dependencies = [('accounts', '0003_seed_new_settings')]

    operations = [
        migrations.RunPython(apply_labels, revert_labels),
    ]
