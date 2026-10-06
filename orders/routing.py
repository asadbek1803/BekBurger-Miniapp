from django.urls import re_path

from . import consumers

# Buyurtma id — faqat harf va raqam
ID = r'(?P<order_id>\d+)'

websocket_urlpatterns = [
    # Oshpaz/kuryer paneli — real-time buyurtma oqimi
    re_path(r'ws/staff/orders/$', consumers.StaffOrderConsumer.as_asgi()),

    # Mijoz ilovasi — dinamik sozlamalar kanali
    re_path(r'ws/config/$', consumers.ConfigConsumer.as_asgi()),

    # Mijoz kuryerni jonli kuzatadi
    re_path(rf'ws/orders/{ID}/track/$', consumers.CourierTrackingConsumer.as_asgi()),
]