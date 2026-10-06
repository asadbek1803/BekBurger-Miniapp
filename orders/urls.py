from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # Savat
    path('', views.cart_view, name='cart'),
    path('add/', views.cart_add, name='cart_add'),
    path('update/', views.cart_update, name='cart_update'),
    path('remove/', views.cart_remove, name='cart_remove'),
    path('clear/', views.cart_clear, name='cart_clear'),

    # Buyurtmalar
    path('create/', views.create_order, name='create_order'),
    path('my/', views.my_orders, name='my_orders'),
    path('<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('<int:order_id>/review/', views.review_order, name='review_order'),
]