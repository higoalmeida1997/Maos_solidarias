from django.apps import AppConfig
from django.db.models.signals import post_migrate


def criar_grupos(sender, **kwargs):
    from django.contrib.auth.models import Group

    from .permissions import GRUPO_PRESIDENTE, GRUPO_VOLUNTARIO

    for nome in (GRUPO_PRESIDENTE, GRUPO_VOLUNTARIO):
        Group.objects.get_or_create(name=nome)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Mãos Solidárias"

    def ready(self):
        post_migrate.connect(criar_grupos, sender=self)
