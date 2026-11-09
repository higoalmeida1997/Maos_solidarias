from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache

from core import services
from core.models import Familia, Item
from core.permissions import GRUPO_PRESIDENTE, GRUPO_VOLUNTARIO

SENHA_TESTE = "Senha-Teste-12345"  # credencial fictícia, só para testes


@pytest.fixture(autouse=True)
def limpar_cache():
    cache.clear()
    yield
    cache.clear()


def _usuario(nome, grupo):
    u = User.objects.create_user(nome, password=SENHA_TESTE)
    u.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return u


@pytest.fixture
def voluntario(db):
    return _usuario("voluntaria", GRUPO_VOLUNTARIO)


@pytest.fixture
def presidente(db):
    return _usuario("presidente", GRUPO_PRESIDENTE)


@pytest.fixture
def familia(db):
    return Familia.objects.create(nome_responsavel="Família Teste", bairro="Bairro Teste", num_pessoas=4)


@pytest.fixture
def arroz(db):
    return Item.objects.create(nome="Arroz", unidade="kg", estoque_minimo=Decimal("5"))


@pytest.fixture
def estoque_arroz(arroz):
    """20 kg de arroz com validade longe."""
    services.registrar_entrada(arroz, Decimal("20"), services.hoje() + timedelta(days=365), "Doação")
    return arroz


@pytest.fixture
def cliente_voluntario(client, voluntario):
    client.login(username="voluntaria", password=SENHA_TESTE)
    return client


@pytest.fixture
def cliente_presidente(client, presidente):
    client.login(username="presidente", password=SENHA_TESTE)
    return client
