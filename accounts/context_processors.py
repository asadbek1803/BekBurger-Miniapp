"""Template context processor — dinamik sozlamalarni har sahifaga beradi."""
from . import settings_service


def app_config(request):
    """
    Barcha template'larga `app` konteksti qo'shiladi.
    Misol: {{ app.restaurant_name }}, {{ app.delivery_fee }}, {{ app.is_open }}
    """
    try:
        cfg = settings_service.public_config()
    except Exception:
        cfg = {'restaurant_name': 'BekBurger', 'currency': "so'm"}
        cfg.update(settings_service.map_config())

    class _App(dict):
        """Dict bilan atribut murojaati."""
        __getattr__ = dict.get

    return {'app': _App(cfg)}