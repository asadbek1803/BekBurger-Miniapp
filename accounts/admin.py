"""Accounts admin configuration."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, AppSettings


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    list_display = ('label', 'key', 'setting_type', 'updated_at')
    list_filter = ('setting_type',)
    search_fields = ('key', 'label')


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'telegram_id', 'display_name', 'role', 'phone', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'telegram_id', 'telegram_username')
    ordering = ('-created_at',)

    fieldsets = UserAdmin.fieldsets + (
        ('Telegram ma\'lumotlari', {
            'fields': ('telegram_id', 'telegram_username', 'avatar_url', 'role', 'phone'),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Telegram ma\'lumotlari', {
            'fields': ('telegram_id', 'role', 'phone'),
        }),
    )
