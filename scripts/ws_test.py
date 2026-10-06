import os
import sys

# Loyiha ildizi sys.path ga (skript scripts/ ichidan ishga tushirilganda)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')
import os

import django


django.setup()

import asyncio

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model

from orders.routing import websocket_urlpatterns

U = get_user_model()
app = URLRouter(websocket_urlpatterns)


async def main():
    users = {n: await sync_to_async(U.objects.get)(username=n)
             for n in ('dev_chef', 'dev_courier', 'dev_customer', 'admin')}

    async def t(name, path, user=None, expect=True):
        c = WebsocketCommunicator(app, path)
        if user is not None:
            c.scope['user'] = user
        ok, code = await c.connect()
        verdict = 'RUXSAT' if ok else 'RAD(code={})'.format(code)
        flag = '  OK  ' if ok == expect else '  FAIL'
        print('{} {:40s} -> {}'.format(flag, name, verdict))
        await c.disconnect()
        return ok == expect

    results = []
    print('--- /ws/staff/orders/ (xodimlar uchun) ---')
    results.append(await t('anonim', '/ws/staff/orders/', None, False))
    results.append(await t('oshpaz (chef)', '/ws/staff/orders/', users['dev_chef'], True))
    results.append(await t('kuryer (courier)', '/ws/staff/orders/', users['dev_courier'], True))
    results.append(await t('direktor (superuser)', '/ws/staff/orders/', users['admin'], True))
    results.append(await t('MIJOZ -> rad bo\'lishi kerak', '/ws/staff/orders/', users['dev_customer'], False))

    print('--- /ws/config/ (ochiq) ---')
    results.append(await t('anonim', '/ws/config/', None, True))

    print('--- ping/pong ---')
    c = WebsocketCommunicator(app, '/ws/staff/orders/')
    c.scope['user'] = users['dev_chef']
    await c.connect()
    await c.send_json_to({'action': 'ping'})
    msg = await c.receive_json_from()
    ok = msg.get('action') == 'pong'
    results.append(ok)
    print('  {} ping -> pong'.format('  OK  ' if ok else '  FAIL'))
    await c.disconnect()

    c = WebsocketCommunicator(app, '/ws/config/')
    await c.connect()
    msg = await c.receive_json_from()
    ok = msg.get('action') == 'config_update' and msg['config']['restaurant_name'] == 'BekBurger'
    results.append(ok)
    print('  {} config boshlang\'ich xabar: {} / {}'.format(
        '  OK  ' if ok else '  FAIL', msg.get('action'), msg.get('config', {}).get('restaurant_name')))
    await c.disconnect()

    print()
    print('WebSocket: {} / {} passed'.format(sum(results), len(results)))


asyncio.run(main())
