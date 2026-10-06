from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('telegram/', views.telegram_auth, name='telegram_auth'),
    path('profile/', views.profile, name='profile'),
]
