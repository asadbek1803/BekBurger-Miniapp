from django.urls import path
from . import views

app_name = 'menu'

urlpatterns = [
    path('categories/', views.categories_list, name='categories'),
    path('items/', views.items_list, name='items'),
    path('items/<int:item_id>/', views.item_detail, name='item_detail'),
]