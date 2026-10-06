"""
Order models — state machine based order management.
States: yangi → qabul_qilindi → tayyorlanmoqda → tayyor → yolda → yetkazildi
        (bekor_qilindi at any stage)
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Order(models.Model):
    """Customer order with state machine."""

    STATUS_CHOICES = [
        ('yangi', 'Yangi'),
        ('qabul_qilindi', 'Qabul qilindi'),
        ('tayyorlanmoqda', 'Tayyorlanmoqda'),
        ('tayyor', 'Tayyor'),
        ('yolda', 'Yo\'lda'),
        ('yetkazildi', 'Yetkazildi'),
        ('bekor_qilindi', 'Bekor qilindi'),
    ]

    PAYMENT_CHOICES = [
        ('naqd', 'Naqd (yetkazib berishda)'),
    ]

    # State machine transitions
    VALID_TRANSITIONS = {
        'yangi': ['qabul_qilindi', 'bekor_qilindi'],
        'qabul_qilindi': ['tayyorlanmoqda', 'bekor_qilindi'],
        'tayyorlanmoqda': ['tayyor', 'bekor_qilindi'],
        'tayyor': ['yolda', 'bekor_qilindi'],
        'yolda': ['yetkazildi', 'bekor_qilindi'],
        'yetkazildi': [],
        'bekor_qilindi': [],
    }

    # Mijoz o'zi bekor qila oladigan holatlar
    CUSTOMER_CANCELLABLE = ['yangi', 'qabul_qilindi']

    # Mijoz reyting qo'yishi mumkin bo'lgan holatlar
    REVIEWABLE = ['yetkazildi']

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
        verbose_name='Mijoz',
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='yangi',
        verbose_name='Holat',
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        verbose_name='Mahsulotlar summasi (so\'m)',
    )
    delivery_fee = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=0,
        verbose_name='Yetkazib berish (so\'m)',
    )
    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        verbose_name='Jami summa (so\'m)',
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default='naqd',
        verbose_name='To\'lov turi',
    )
    is_paid = models.BooleanField(default=False, verbose_name='To\'langanmi')
    address = models.TextField(blank=True, verbose_name='Manzil')
    latitude = models.FloatField(null=True, blank=True, verbose_name='Kenglik')
    longitude = models.FloatField(null=True, blank=True, verbose_name='Uzunlik')
    note = models.TextField(blank=True, verbose_name='Izoh')
    cancel_reason = models.CharField(
        max_length=200, blank=True, default='', verbose_name='Bekor qilish sababi',
    )
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name='Bekor qilingan vaqt')

    # Reyting (faqat yetkazilgan buyurtma uchun)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Reyting (1-5)')
    review = models.TextField(blank=True, default='', verbose_name='Izoh')

    assigned_chef = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='chef_orders',
        limit_choices_to={'role': 'chef'},
        verbose_name='Biriktirilgan oshpaz',
    )
    assigned_courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='courier_orders',
        limit_choices_to={'role': 'courier'},
        verbose_name='Biriktirilgan kuryer',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Yaratilgan vaqt')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yangilangan vaqt')

    class Meta:
        verbose_name = 'Buyurtma'
        verbose_name_plural = 'Buyurtmalar'
        ordering = ['-created_at']

    def __str__(self):
        return f'Buyurtma #{self.id} — {self.customer.display_name} ({self.get_status_display()})'

    def can_transition_to(self, new_status):
        """Check if transition to new_status is valid."""
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def transition_to(self, new_status, changed_by=None, note=''):
        """
        Perform state transition if valid.
        Holat tarixi avtomatik yozib boriladi.
        """
        if not self.can_transition_to(new_status):
            raise ValueError(
                f'"{self.get_status_display()}" holatidan "{dict(self.STATUS_CHOICES).get(new_status)}" ga o\'tib bo\'lmaydi'
            )
        old_status = self.status
        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])

        if new_status == 'yetkazildi':
            self.is_paid = True
            self.save(update_fields=['is_paid'])
        elif new_status == 'bekor_qilindi':
            self.cancelled_at = timezone.now()
            self.save(update_fields=['cancelled_at'])

        # Holat tarixi
        OrderStatusHistory.objects.create(
            order=self,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            note=note,
        )

        # Send notification
        try:
            from .notifications import send_order_notification
            send_order_notification(self)
        except Exception as e:
            print(f"Error sending notification: {e}")

        try:
            from .broadcast import broadcast_order_update
            broadcast_order_update(self)
        except Exception as e:
            print(f"Error broadcasting order update: {e}")

    def calculate_total(self):
        """Recalculate total from order items."""
        subtotal = sum(item.price * item.quantity for item in self.items.all())
        self.subtotal = subtotal
        self.total_price = subtotal + self.delivery_fee
        self.save(update_fields=['subtotal', 'total_price'])
        return self.total_price

    @property
    def status_icon(self):
        icons = {
            'yangi': '🆕',
            'qabul_qilindi': '✅',
            'tayyorlanmoqda': '👨‍🍳',
            'tayyor': '📦',
            'yolda': '🛵',
            'yetkazildi': '🎉',
            'bekor_qilindi': '❌',
        }
        return icons.get(self.status, '❓')

    @property
    def eta_minutes(self):
        """Taxminiy yetkazib berish muddati (daqiqa)."""
        base = max((item.menu_item.preparation_time * item.quantity
                    for item in self.items.select_related('menu_item')), default=10)
        if self.status in ('yolda', 'yetkazildi'):
            return 0
        return base + 15

    @property
    def can_customer_cancel(self):
        from accounts import settings_service
        if not settings_service.order_cancel_allowed():
            return False
        return self.status in self.CUSTOMER_CANCELLABLE

    @property
    def can_review(self):
        return self.status in self.REVIEWABLE and self.rating is None

    def to_dict(self, with_history=False):
        data = {
            'id': self.id,
            'status': self.status,
            'status_display': self.get_status_display(),
            'status_icon': self.status_icon,
            'subtotal': int(self.subtotal),
            'delivery_fee': int(self.delivery_fee),
            'total_price': int(self.total_price),
            'payment_method': self.payment_method,
            'payment_display': self.get_payment_method_display(),
            'is_paid': self.is_paid,
            'address': self.address,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'note': self.note,
            'cancel_reason': self.cancel_reason,
            'rating': self.rating,
            'review': self.review,
            'eta_minutes': self.eta_minutes,
            'can_cancel': self.can_customer_cancel,
            'can_review': self.can_review,
            'created_at': self.created_at.isoformat(),
            'items': [item.to_dict() for item in self.items.all()],
        }
        if with_history:
            data['history'] = [h.to_dict() for h in self.history.all()]
        return data


class OrderStatusHistory(models.Model):
    """Buyurtma holati tarixi — mijoz va xodimlar uchun shaffoflik."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='history',
        verbose_name='Buyurtma',
    )
    old_status = models.CharField(max_length=30, blank=True, default='', verbose_name='Avvalgi holat')
    new_status = models.CharField(max_length=30, verbose_name='Yangi holat')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='order_status_changes',
        verbose_name='Kim o\'zgartirdi',
    )
    note = models.CharField(max_length=200, blank=True, default='', verbose_name='Izoh')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Vaqt')

    class Meta:
        verbose_name = 'Holat tarixi'
        verbose_name_plural = 'Holat tarixlari'
        ordering = ['created_at']

    def __str__(self):
        return f'#{self.order_id}: {self.old_status} → {self.new_status}'

    @property
    def new_status_display(self):
        return dict(Order.STATUS_CHOICES).get(self.new_status, self.new_status)

    def to_dict(self):
        return {
            'status': self.new_status,
            'status_display': self.new_status_display,
            'icon': dict(
                (k, v) for k, v in
                [('yangi', '🆕'), ('qabul_qilindi', '✅'), ('tayyorlanmoqda', '👨‍🍳'),
                 ('tayyor', '📦'), ('yolda', '🛵'), ('yetkazildi', '🎉'),
                 ('bekor_qilindi', '❌')]
            ).get(self.new_status, '•'),
            'note': self.note,
            'changed_by': self.changed_by.display_name if self.changed_by else 'Tizim',
            'created_at': self.created_at.isoformat(),
            'time': self.created_at.strftime('%H:%M'),
        }


class CourierLocation(models.Model):
    """
    Kuryerning oxirgi joylashuvi.

    Mijoz sahifani yangilasa ham kuryer joylashuvi ko'rinib turadi —
    shuning uchun joylashuv bazada saqlanadi (faqat oxirgisi).
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='courier_locations',
        verbose_name='Buyurtma',
    )
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='courier_locations',
        limit_choices_to={'role': 'courier'},
        verbose_name='Kuryer',
    )
    latitude = models.FloatField(verbose_name='Kenglik')
    longitude = models.FloatField(verbose_name='Uzunlik')
    heading = models.FloatField(null=True, blank=True, verbose_name='Yo\'nalish')
    accuracy = models.FloatField(null=True, blank=True, verbose_name='Aniqlik (m)')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Yangilangan vaqt')

    class Meta:
        verbose_name = 'Kuryer joylashuvi'
        verbose_name_plural = 'Kuryer joylashuvlari'
        ordering = ['-updated_at']

    def __str__(self):
        return f'#{self.order_id} — {self.latitude:.4f}, {self.longitude:.4f}'

    def to_dict(self):
        return {'lat': self.latitude, 'lng': self.longitude, 'updated_at': self.updated_at.isoformat()}


class OrderItem(models.Model):
    """Individual item within an order."""
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Buyurtma',
    )
    menu_item = models.ForeignKey(
        'menu.MenuItem',
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name='Mahsulot',
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name='Miqdor')
    price = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        verbose_name='Narxi (o\'sha paytdagi)',
    )

    class Meta:
        verbose_name = 'Buyurtma mahsuloti'
        verbose_name_plural = 'Buyurtma mahsulotlari'

    def __str__(self):
        return f'{self.menu_item.name} x{self.quantity}'

    @property
    def subtotal(self):
        return self.price * self.quantity

    def to_dict(self):
        return {
            'id': self.id,
            'menu_item_id': self.menu_item_id,
            'name': self.menu_item.name,
            'price': int(self.price),
            'quantity': self.quantity,
            'subtotal': int(self.subtotal),
            'image_url': self.menu_item.image_url,
        }
