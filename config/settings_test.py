"""Configuração usada apenas pelos testes automatizados."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "chave-somente-para-testes-automatizados")
os.environ.setdefault("DJANGO_DEBUG", "0")

from .settings import *  # noqa: E402,F401,F403

SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["testserver", "localhost"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
