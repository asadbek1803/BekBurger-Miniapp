"""
Menu models — Category and MenuItem.
"""
from django.db import models


def _notify_menu_change():
    """Ochiq ilovalarni menyu/banner o'zgarganini bilishga undaydi (xatosiz)."""
    try:
        from orders.broadcast import broadcast_menu_update
        broadcast_menu_update()
    except Exception:
        pass


class Category(models.Model):
    """Food category (Burgerlar, Ichimliklar, etc.)"""
    name = models.CharField(max_length=100, verbose_name='Nomi')
    icon = models.CharField(
        max_length=10,
        default='🍔',
        verbose_name='Emoji/Icon',
        help_text='Kategoriya uchun emoji (masalan: 🍔, 🥤, 🍟) (Agar rasm yo\'q bo\'lsa ishlatiladi)',
    )
    image = models.ImageField(
        upload_to='categories/',
        null=True,
        blank=True,
        verbose_name='Rasmi (Ixtiyoriy)'
    )
    order = models.PositiveIntegerField(default=0, verbose_name='Tartib')
    is_active = models.BooleanField(default=True, verbose_name='Faolmi')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kategoriya'
        verbose_name_plural = 'Kategoriyalar'
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.icon} {self.name}'


class MenuItem(models.Model):
    """Menu item — food or drink."""
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Kategoriya',
    )
    name = models.CharField(max_length=200, verbose_name='Nomi')
    description = models.TextField(blank=True, verbose_name='Tavsif')
    price = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        verbose_name='Narxi (so\'m)',
    )
    image = models.ImageField(
        upload_to='menu/',
        null=True,
        blank=True,
        verbose_name='Rasmi',
    )
    is_available = models.BooleanField(default=True, verbose_name='Mavjudmi')
    is_popular = models.BooleanField(default=False, verbose_name='Mashhurmi')
    weight = models.CharField(
        max_length=30, blank=True, default='', verbose_name='Og\'irligi',
        help_text='Masalan: 180g yoki 250 ml',
    )
    calories = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='Kaloriya (kcal)',
    )
    preparation_time = models.PositiveIntegerField(
        default=10,
        verbose_name='Tayyorlash vaqti (daqiqa)',
    )
    order = models.PositiveIntegerField(default=0, verbose_name='Tartib')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Menyu mahsuloti'
        verbose_name_plural = 'Menyu mahsulotlari'
        ordering = ['order', 'name']

    def __str__(self):
        return f'{self.name} — {self.price:,} so\'m'

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return None

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _notify_menu_change()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        _notify_menu_change()

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': int(self.price),
            'image_url': self.image_url,
            'is_available': self.is_available,
            'is_popular': self.is_popular,
            'weight': self.weight,
            'calories': self.calories,
            'preparation_time': self.preparation_time,
            'category_id': self.category_id,
            'category_name': self.category.name,
        }

class Banner(models.Model):
    """
    Bannerlar — menyu sahifasining tepasidagi avtomatik aylanuvchi slaydlar.

    Har bir banner mustaqil ravishda boshqariladi: gradient ranglari,
    rasm joylashuvi, tugma va avtomatik almashish tezligi.
    """
    LAYOUT_CHOICES = [
        ('image_right', 'Rasm o\'ngda'),
        ('background', 'Rasm fon sifatida'),
    ]

    ACTION_CHOICES = [
        ('none', 'Amal yo\'q'),
        ('call', 'Telefon qilish'),
        ('scroll_menu', 'Menyuni ochish'),
        ('open_url', 'Havolaga o\'tish'),
    ]

    title = models.CharField(max_length=100, verbose_name='Sarlavha', help_text='Masalan: BekBurger Classic')
    subtitle = models.CharField(max_length=200, verbose_name='Qo\'shimcha matn', help_text='Masalan: Tez va mazali yetkazib beramiz!')
    label = models.CharField(max_length=50, verbose_name='Yorliq (Label)', default='🔥 BUGUNGI TAVSIYA')

    image = models.ImageField(upload_to='banners/', null=True, blank=True, verbose_name='Banner rasmi')

    # ── Ko\'rinish ──
    color_start = models.CharField(max_length=9, default='#E63946', verbose_name='Gradient 1-rang')
    color_end = models.CharField(max_length=9, default='#F4A261', verbose_name='Gradient 2-rang')
    text_color = models.CharField(max_length=9, default='#FFFFFF', verbose_name='Matn rangi')
    layout = models.CharField(max_length=20, choices=LAYOUT_CHOICES, default='image_right', verbose_name='Rasm joylashuvi')

    # ── Tugma ──
    button_text = models.CharField(max_length=50, blank=True, default='', verbose_name='Tugma matni')
    button_action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='none', verbose_name='Tugma amalga')
    button_value = models.CharField(max_length=300, blank=True, default='', verbose_name='Tugma qiymati',
                                    help_text='Telefon yoki havola (open_url uchun)')

    order = models.PositiveIntegerField(default=0, verbose_name='Tartib')
    is_active = models.BooleanField(default=True, verbose_name='Faolmi')
    autoplay_delay = models.PositiveIntegerField(
        default=0, verbose_name='Avtomatik almashish (soniya)',
        help_text='0 = umumiy sozlamani ishlatish',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Banner'
        verbose_name_plural = 'Bannerlar'
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return None

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        _notify_menu_change()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        _notify_menu_change()

    @property
    def gradient(self):
        """CSS gradient qatori."""
        return f'linear-gradient(135deg, {self.color_start} 0%, {self.color_end} 100%)'

    def to_dict(self, default_interval=5):
        return {
            'id': self.id,
            'title': self.title,
            'subtitle': self.subtitle,
            'label': self.label,
            'image_url': self.image_url,
            'gradient': self.gradient,
            'text_color': self.text_color,
            'layout': self.layout,
            'button_text': self.button_text,
            'button_action': self.button_action,
            'button_value': self.button_value,
            'delay': self.autoplay_delay or default_interval,
        }
