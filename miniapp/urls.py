from django.urls import path
from . import views

app_name = 'miniapp'

# API marshrutlari asosiy URLconf'da (/api/dashboard/, /api/staff/...).
# Bu faylda faqat mini app sahifalari bor.
urlpatterns = [
    path('', views.index, name='index'),
    path('customer/', views.customer_view, name='customer'),
    path('director/', views.director_dashboard, name='director'),
    path('chef/', views.chef_view, name='chef'),
    path('courier/', views.courier_view, name='courier'),
]