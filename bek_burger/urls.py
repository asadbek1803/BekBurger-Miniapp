"""BekBurger URL Configuration"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from accounts import geocode as geocode_views
from accounts import views as accounts_views
from menu import views as menu_views
from miniapp import dashboard_api, staff_api
from miniapp import views as miniapp_views
from orders import views as order_views

urlpatterns = [
    # ── Admin ──
    path('admin/', admin.site.urls),

    # ── Ommaviy API ──
    path('api/config/', menu_views.config, name='config'),
    path('api/geocode/reverse/', geocode_views.reverse, name='geocode_reverse'),
    path('api/auth/', include('accounts.urls')),
    path('api/menu/', include('menu.urls')),
    path('api/cart/', include('orders.urls')),
    path('api/orders/create/', order_views.create_order, name='create_order'),
    path('api/orders/my/', order_views.my_orders, name='my_orders'),
    path('api/orders/<int:order_id>/cancel/', order_views.cancel_order, name='order_cancel'),
    path('api/orders/<int:order_id>/review/', order_views.review_order, name='order_review'),

    # ── Mini App sahifalari ──
    path('miniapp/', include('miniapp.urls')),
    path('dashboard/', miniapp_views.director_dashboard, name='dashboard'),

    # ── Dashboard API (direktor) ──
    path('api/dashboard/stats/', dashboard_api.dashboard_stats, name='dash_stats'),
    path('api/dashboard/orders/', dashboard_api.dashboard_orders, name='dash_orders'),
    path('api/dashboard/orders/<int:order_id>/status/', dashboard_api.dashboard_order_status,
         name='dash_order_status'),
    path('api/dashboard/menu/items/', dashboard_api.dashboard_menu_items, name='dash_menu_items'),
    path('api/dashboard/menu/items/<int:item_id>/', dashboard_api.dashboard_menu_item_detail,
         name='dash_menu_item'),
    path('api/dashboard/menu/categories/', dashboard_api.dashboard_categories, name='dash_categories'),
    path('api/dashboard/menu/categories/<int:cat_id>/', dashboard_api.dashboard_category_detail,
         name='dash_category'),
    path('api/dashboard/users/', dashboard_api.dashboard_users, name='dash_users'),
    path('api/dashboard/users/<int:user_id>/', dashboard_api.dashboard_user_detail, name='dash_user'),
    path('api/dashboard/settings/', dashboard_api.dashboard_settings, name='dash_settings'),
    path('api/dashboard/banners/', dashboard_api.dashboard_banners, name='dash_banners'),
    path('api/dashboard/banners/<int:banner_id>/', dashboard_api.dashboard_banner_detail,
         name='dash_banner'),
    path('api/dashboard/reviews/', dashboard_api.dashboard_reviews, name='dash_reviews'),

    # ── Xodim API ──
    path('api/staff/chef/orders/', staff_api.chef_orders, name='chef_orders'),
    path('api/staff/chef/orders/<int:order_id>/status/', staff_api.chef_update_status,
         name='chef_update_status'),
    path('api/staff/courier/orders/', staff_api.courier_orders, name='courier_orders'),
    path('api/staff/courier/orders/<int:order_id>/status/', staff_api.courier_update_status,
         name='courier_update_status'),
    path('api/staff/courier/orders/<int:order_id>/location/', staff_api.courier_location,
         name='courier_location'),

    # ── Bosh sahifa ──
    path('', RedirectView.as_view(url='/miniapp/customer/', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)