import requests
import threading

def _send_message_task(bot_token, chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram notification error: {e}")

def send_order_notification(order):
    """Send a Telegram notification to the customer about their order status."""
    if not order.customer or not order.customer.telegram_id:
        return

    try:
        from accounts.models import AppSettings
        bot_token = AppSettings.objects.filter(key='telegram_bot_token').values_list('value', flat=True).first()
        if not bot_token:
            return
    except Exception:
        return

    status_messages = {
        'qabul_qilindi': "✅ <b>Buyurtma qabul qilindi!</b>\nTez orada tayyorlashni boshlaymiz.",
        'tayyorlanmoqda': "👨‍🍳 <b>Buyurtmangiz tayyorlanmoqda!</b>\nOshpazimiz ishga kirishdi.",
        'tayyor': "📦 <b>Buyurtma tayyor!</b>\nKuryerga topshirilmoqda.",
        'yolda': "🛵 <b>Buyurtmangiz yo'lga chiqdi!</b>\nIlova orqali kuryerni jonli kuzatishingiz mumkin.",
        'yetkazildi': "🎉 <b>Buyurtma yetkazib berildi!</b>\nYoqimli ishtaha! BekBurger ni tanlaganingiz uchun rahmat.",
        'bekor_qilindi': "❌ <b>Buyurtma bekor qilindi.</b>\nBatafsil ma'lumot uchun biz bilan bog'laning."
    }

    message = status_messages.get(order.status)
    if message:
        text = f"Buyurtma <b>#{order.id}</b>\n\n{message}"
        threading.Thread(target=_send_message_task, args=(bot_token, order.customer.telegram_id, text), daemon=True).start()
