from django.contrib import admin
from django.utils.html import format_html

from .models import Order, OrderItem, OrderStatusHistory, CourierLocation


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('menu_item', 'quantity', 'price', 'line_total')
    fields = ('menu_item', 'quantity', 'price', 'line_total')

    def line_total(self, obj):
        return f'{(obj.price or 0) * (obj.quantity or 0):,}'
    line_total.short_description = 'Summa'


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('old_status', 'new_status', 'changed_by', 'note', 'created_at')
    ordering = ('created_at',)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'items_summary', 'total_display', 'status',
                    'payment_method', 'is_paid', 'created_at')
    list_filter = ('status', 'payment_method', 'is_paid', 'created_at')
    search_fields = ('id', 'customer__first_name', 'customer__last_name', 'customer__telegram_id')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    inlines = [OrderItemInline, OrderStatusHistoryInline]

    fieldsets = (
        ('Buyurtma', {
            'fields': ('customer', 'status', 'subtotal', 'delivery_fee', 'total_price')
        }),
        ('To\'lov', {
            'fields': ('payment_method', 'is_paid')
        }),
        ('Yetkazib berish', {
            'fields': ('address', 'latitude', 'longitude', 'note')
        }),
        ('Biriktirish', {
            'fields': ('assigned_chef', 'assigned_courier')
        }),
        ('Reyting', {
            'fields': ('rating', 'review')
        }),
        ('Bekor qilish', {
            'classes': ('collapse',),
            'fields': ('cancel_reason', 'cancelled_at')
        }),
    )

    def items_summary(self, obj):
        items = list(obj.items.select_related('menu_item')[:3])
        text = ', '.join(f'{i.menu_item.name} x{i.quantity}' for i in items)
        extra = obj.items.count() - len(items)
        if extra > 0:
            text += f' +{extra}'
        return text or '—'
    items_summary.short_description = 'Mahsulotlar'

    def total_display(self, obj):
        return f'{obj.total_price:,} so\'m'
    total_display.short_description = 'Jami'
    total_display.admin_order_field = 'total_price'

    def has_add_permission(self, request):
        # Buyurtmalar faqat mijoz ilovasi orqali yaratiladi
        return False


@admin.register(CourierLocation)
class CourierLocationAdmin(admin.ModelAdmin):
    list_display = ('order', 'courier', 'coords', 'updated_at')
    list_filter = ('updated_at',)
    ordering = ('-updated_at',)

    def coords(self, obj):
        return f'{obj.latitude:.5f}, {obj.longitude:.5f}'
    coords.short_description = 'Koordinatalar'