from django.contrib import admin
from django.utils.html import format_html

from .models import Category, MenuItem, Banner


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'icon', 'name', 'order', 'is_active', 'items_count')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

    def items_count(self, obj):
        return f'{obj.items.filter(is_available=True).count()} ta'
    items_count.short_description = 'Mahsulotlar'

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:40px;height:40px;object-fit:contain;border-radius:8px;" />',
                obj.image.url
            )
        return '📷'
    image_preview.short_description = 'Rasm'


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'name', 'category', 'price_display', 'is_available',
                    'is_popular', 'preparation_time', 'order')
    list_editable = ('is_available', 'is_popular', 'order')
    list_filter = ('category', 'is_available', 'is_popular')
    search_fields = ('name', 'description')
    ordering = ('category', 'order', 'name')

    def price_display(self, obj):
        return f'{obj.price:,} so\'m'
    price_display.short_description = 'Narxi'
    price_display.admin_order_field = 'price'

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:50px;height:50px;object-fit:cover;border-radius:8px;" />',
                obj.image.url
            )
        return '📷'
    image_preview.short_description = 'Rasm'


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('thumb', 'title', 'label', 'colors', 'layout', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active', 'layout')
    search_fields = ('title', 'subtitle')

    fieldsets = (
        (None, {
            'fields': ('title', 'subtitle', 'label', 'image', 'is_active', 'order')
        }),
        ('Ko\'rinish', {
            'fields': ('color_start', 'color_end', 'text_color', 'layout'),
            'description': 'Har bir banner o\'z gradient rangiga ega.',
        }),
        ('Tugma', {
            'fields': ('button_text', 'button_action', 'button_value', 'autoplay_delay'),
        }),
    )

    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:90px;height:45px;object-fit:cover;border-radius:6px;" />',
                obj.image.url
            )
        # Rasmsiz banner — gradient ko'rinishi
        return format_html(
            '<div style="width:90px;height:45px;border-radius:6px;background:{};'
            'color:{};display:flex;align-items:center;justify-content:center;'
            'font-size:10px;padding:4px;text-align:center;">{}</div>',
            obj.gradient, obj.text_color, obj.title[:22]
        )
    thumb.short_description = 'Ko\'rinishi'

    def colors(self, obj):
        return format_html(
            '<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
            'background:{};border:1px solid #ddd;"></span> → '
            '<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
            'background:{};border:1px solid #ddd;"></span>',
            obj.color_start, obj.color_end
        )
    colors.short_description = 'Ranglar'