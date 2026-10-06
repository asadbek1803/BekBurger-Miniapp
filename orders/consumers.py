"""
WebSocket consumers.

1. `StaffOrderConsumer` — oshpaz va kuryer panellari uchun jonli buyurtma oqimi.
   Yangi buyurtma yoki holat o'zgarganda panel darhol yangilanadi.

2. `CourierTrackingConsumer` — mijoz kuryerni jonli kuzatadi.
"""
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .broadcast import STAFF_GROUP, broadcast_order_update


def _user_allowed_staff_panel(user, allowed_roles):
    """Superuser yoki ruxsat etilgan rol."""
    return bool(user and user.is_authenticated
                and (user.is_superuser or user.role in allowed_roles))


class StaffOrderConsumer(AsyncWebsocketConsumer):
    """Oshpaz/kuryer paneli uchun real-time buyurtma oqimi."""

    async def connect(self):
        user = self.scope.get('user')

        # Faqat autentifikatsiyalangan xodimlar (oshpaz/kuryer/direktor)
        if not _user_allowed_staff_panel(user, ('chef', 'courier', 'director')):
            await self.close(code=4001)
            return

        self.group_name = STAFF_GROUP
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Mijoz tomondan kelgan 'ping' ga javob beramiz."""
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get('action') == 'ping':
            await self.send(text_data=json.dumps({'action': 'pong'}))

    async def staff_order_update(self, event):
        """Buyurtma yangilandi — panellarga yuboramiz."""
        await self.send(text_data=json.dumps(event['data']))


class ConfigConsumer(AsyncWebsocketConsumer):
    """
    Mijoz ilovasi uchun sozlamalar kanali.

    Direktor dashboard'dan nom/narx/banner o'zgartirilganda ochiq ilovalar
    darhol yangilanadi — sahifani qayta yuklash shart emas.
    """

    async def connect(self):
        self.group_name = 'bb_customers'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Hozirgi sozlamalarni yuborib boshlaymiz
        cfg = await self._config()
        await self.send(text_data=json.dumps({'action': 'config_update', 'config': cfg}))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if data.get('action') == 'ping':
            await self.send(text_data=json.dumps({'action': 'pong'}))

    @database_sync_to_async
    def _config(self):
        try:
            from accounts.settings_service import public_config
            return public_config()
        except Exception:
            return {'restaurant_name': 'BekBurger'}

    async def customer_config_update(self, event):
        await self.send(text_data=json.dumps({
            'action': 'config_update',
            'config': event['data'],
        }))

    async def customer_menu_update(self, event):
        await self.send(text_data=json.dumps({'action': 'menu_update'}))


class CourierTrackingConsumer(AsyncWebsocketConsumer):
    """Mijoz kuryer joylashuvini real-time kuzatadi."""

    async def connect(self):
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.group_name = f'order_track_{self.order_id}'

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Yangi ulanishda oxirgi joylashuvni yuborish
        last = await self._last_known()
        if last:
            await self.send(text_data=json.dumps({
                'action': 'location_update',
                'lat': last['lat'],
                'lng': last['lng'],
            }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Kuryer joylashuvini qabul qiladi va guruhga yuboradi."""
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if data.get('action') != 'update_location':
            return

        lat = data.get('lat')
        lng = data.get('lng')
        if lat is None or lng is None:
            return

        # O'zbekiston chegaralarida bo'lishi kerak
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            return

        await self.channel_layer.group_send(self.group_name, {
            'type': 'location_message',
            'lat': lat,
            'lng': lng,
        })

    @database_sync_to_async
    def _last_known(self):
        try:
            from .models import CourierLocation
            loc = CourierLocation.objects.filter(
                order_id=self.order_id
            ).order_by('-updated_at').first()
            if loc:
                return {'lat': loc.latitude, 'lng': loc.longitude}
        except Exception:
            return None
        return None

    async def location_message(self, event):
        await self.send(text_data=json.dumps({
            'action': 'location_update',
            'lat': event['lat'],
            'lng': event['lng'],
        }))