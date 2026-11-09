"""Testes de segurança (RNF01/RNF02) e do fluxo pelas telas."""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from core import services
from core.models import Entrega, Familia
from core.tests.conftest import SENHA_TESTE


def test_visitante_sem_login_e_redirecionado_ao_login(client):
    for nome in ("home", "familia_lista", "estoque", "entrega_nova", "relatorio"):
        resposta = client.get(reverse(nome))
        assert resposta.status_code == 302
        assert resposta["Location"].startswith(reverse("login"))


def test_voluntario_recebe_403_nas_funcoes_da_presidente(cliente_voluntario, familia, estoque_arroz, voluntario):
    entrega = services.registrar_entrega(familia, voluntario, [(estoque_arroz, Decimal("1"))])
    assert cliente_voluntario.get(reverse("relatorio")).status_code == 403
    assert cliente_voluntario.post(reverse("entrega_cancelar", args=[entrega.pk])).status_code == 403
    assert cliente_voluntario.post(reverse("familia_alternar", args=[familia.pk])).status_code == 403
    assert cliente_voluntario.get(reverse("item_novo")).status_code == 403
    entrega.refresh_from_db()
    assert entrega.cancelada is False


def test_presidente_acessa_relatorio_e_csv(cliente_presidente):
    assert cliente_presidente.get(reverse("relatorio")).status_code == 200
    csv = cliente_presidente.get(reverse("relatorio") + "?formato=csv")
    assert csv.status_code == 200 and csv["Content-Type"].startswith("text/csv")


def test_senha_guardada_como_hash_pbkdf2(voluntario):
    senha = User.objects.get(username="voluntaria").password
    assert senha.startswith("pbkdf2_sha256$")
    assert SENHA_TESTE not in senha


def test_login_valido_e_invalido_com_mensagem_generica(client, voluntario):
    ruim = client.post(reverse("login"), {"username": "voluntaria", "password": "errada"})
    assert ruim.status_code == 200
    assert "_auth_user_id" not in client.session
    inexistente = client.post(reverse("login"), {"username": "ninguem", "password": "errada"})
    assert ruim.context["form"].non_field_errors() == inexistente.context["form"].non_field_errors()
    ok = client.post(reverse("login"), {"username": "voluntaria", "password": SENHA_TESTE})
    assert ok.status_code == 302 and "_auth_user_id" in client.session


def test_bloqueio_apos_5_tentativas_invalidas(client, voluntario):
    for _ in range(5):
        client.post(reverse("login"), {"username": "voluntaria", "password": "errada"})
    resposta = client.post(reverse("login"), {"username": "voluntaria", "password": SENHA_TESTE})
    assert resposta.status_code == 200
    assert "_auth_user_id" not in client.session


def test_sair_encerra_a_sessao(cliente_voluntario):
    assert cliente_voluntario.get(reverse("home")).status_code == 200
    cliente_voluntario.post(reverse("logout"))
    assert cliente_voluntario.get(reverse("home")).status_code == 302


def test_paginas_nao_sao_guardadas_em_cache_e_tem_csp(cliente_voluntario):
    resposta = cliente_voluntario.get(reverse("home"))
    assert resposta["Cache-Control"] == "no-store"
    assert "script-src 'self'" in resposta["Content-Security-Policy"]


def test_xss_na_saida_e_escapado(cliente_voluntario):
    Familia.objects.create(nome_responsavel="<script>alert(1)</script>", bairro="B", num_pessoas=1)
    html = cliente_voluntario.get(reverse("familia_lista")).content.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_formulario_rejeita_marcacao_html(cliente_voluntario):
    resposta = cliente_voluntario.post(reverse("familia_nova"), {
        "nome_responsavel": "<img src=x onerror=alert(1)>", "bairro": "Centro", "num_pessoas": 3,
    })
    assert resposta.status_code == 200
    assert Familia.objects.count() == 0


@pytest.mark.parametrize("q", ["' OR '1'='1", "'; DROP TABLE core_familia;--"])
def test_busca_trata_injecao_de_sql_como_texto(cliente_voluntario, familia, q):
    resposta = cliente_voluntario.get(reverse("familia_lista"), {"q": q})
    assert resposta.status_code == 200
    assert Familia.objects.count() == 1  # tabela intacta
    assert "Família Teste" not in resposta.content.decode()


def test_cadastro_valida_campos_obrigatorios_e_numero_de_pessoas(cliente_voluntario):
    r = cliente_voluntario.post(reverse("familia_nova"), {"nome_responsavel": "", "bairro": "", "num_pessoas": 0})
    assert r.status_code == 200 and Familia.objects.count() == 0
    ok = cliente_voluntario.post(reverse("familia_nova"), {
        "nome_responsavel": "Ana", "contato": "(75) 99999-0000", "bairro": "Centro", "num_pessoas": 3,
    })
    assert ok.status_code == 302 and Familia.objects.count() == 1


def test_duplicidade_de_familia_pede_confirmacao(cliente_voluntario):
    dados = {"nome_responsavel": "Ana", "contato": "(75) 99999-0000", "bairro": "Centro", "num_pessoas": 3}
    cliente_voluntario.post(reverse("familia_nova"), dados)
    de_novo = cliente_voluntario.post(reverse("familia_nova"), dados)
    assert de_novo.status_code == 200 and Familia.objects.count() == 1
    confirmado = cliente_voluntario.post(reverse("familia_nova"), {**dados, "confirmar_duplicado": "1"})
    assert confirmado.status_code == 302 and Familia.objects.count() == 2


def test_fluxo_de_entrega_pela_tela_e_bloqueio_da_segunda(cliente_voluntario, familia, estoque_arroz):
    url = reverse("entrega_nova")
    dados = {"familia": familia.pk, "data_entrega": services.hoje().isoformat(), f"qtd_{estoque_arroz.pk}": "5"}
    primeira = cliente_voluntario.post(url, dados)
    assert primeira.status_code == 302
    segunda = cliente_voluntario.post(url, dados)
    assert segunda.status_code == 200
    texto = segunda.content.decode()
    assert "já recebeu a cesta em" in texto and "Nenhuma alteração foi feita no estoque" in texto
    assert services.saldo_utilizavel(estoque_arroz) == Decimal("15")
    assert Entrega.objects.count() == 1


def test_entrega_com_quantidade_invalida_mostra_erro_em_texto(cliente_voluntario, familia, estoque_arroz):
    dados = {"familia": familia.pk, "data_entrega": services.hoje().isoformat(), f"qtd_{estoque_arroz.pk}": "0"}
    r = cliente_voluntario.post(reverse("entrega_nova"), dados)
    assert r.status_code == 200 and "maior que zero" in r.content.decode()
    assert Entrega.objects.count() == 0


def test_pagina_inexistente_nao_mostra_detalhes_tecnicos(cliente_voluntario):
    html = cliente_voluntario.get("/rota-que-nao-existe/").content.decode()
    assert "Traceback" not in html and "Django" not in html
