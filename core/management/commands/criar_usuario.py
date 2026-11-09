from getpass import getpass

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from core.permissions import GRUPO_PRESIDENTE, GRUPO_VOLUNTARIO


class Command(BaseCommand):
    help = "Cria um usuário (presidente ou voluntário). A senha é pedida no terminal, nunca por argumento."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--perfil", choices=["presidente", "voluntario"], default="voluntario")
        parser.add_argument("--nome", default="")

    def handle(self, *args, **opcoes):
        username = opcoes["username"]
        if User.objects.filter(username=username).exists():
            raise CommandError("Este usuário já existe.")
        senha = getpass("Senha: ")
        if senha != getpass("Repita a senha: "):
            raise CommandError("As senhas não coincidem.")
        try:
            validate_password(senha)
        except ValidationError as erro:
            raise CommandError(" ".join(erro.messages))

        presidente = opcoes["perfil"] == "presidente"
        usuario = User.objects.create_user(username=username, password=senha, first_name=opcoes["nome"])
        if presidente:  # a presidente administra também o painel interno
            usuario.is_staff = usuario.is_superuser = True
            usuario.save(update_fields=["is_staff", "is_superuser"])
        grupo, _ = Group.objects.get_or_create(name=GRUPO_PRESIDENTE if presidente else GRUPO_VOLUNTARIO)
        usuario.groups.add(grupo)
        self.stdout.write(self.style.SUCCESS(f"Usuário {username} criado como {opcoes['perfil']}."))
