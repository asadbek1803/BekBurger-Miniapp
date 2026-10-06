"""WSGI config for bek_burger project."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')
application = get_wsgi_application()
