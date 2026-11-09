"""Testes das regras de negócio (RF02, RF03, RF04, RF05)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from core import services
from core.models import Entrega, Item, MovimentacaoEstoque

D = Decimal
Tipo = MovimentacaoEstoque.Tipo


def test_primeira_entrega_grava_e_baixa_estoque(familia, estoque_arroz, voluntario):
    entrega = services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5"))])
    assert services.saldo_utilizavel(estoque_arroz) == D("15")
    assert entrega.mes_referencia == services.hoje().strftime("%Y-%m")
    assert entrega.itens.count() == 1


def test_segunda_entrega_no_mes_e_recusada_sem_mexer_no_estoque(familia, estoque_arroz, voluntario):
    primeira = services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5"))])
    with pytest.raises(services.EntregaDuplicada) as erro:
        services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5"))])
    assert erro.value.data_anterior == primeira.data_entrega
    assert primeira.data_entrega.strftime("%d/%m/%Y") in str(erro.value)
    assert services.saldo_utilizavel(estoque_arroz) == D("15")
    assert Entrega.objects.count() == 1


def test_mesma_familia_pode_receber_no_mes_seguinte(familia, estoque_arroz, voluntario):
    services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("2"))], date(2026, 3, 10))
    services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("2"))], date(2026, 4, 5))
    assert Entrega.objects.count() == 2


def test_saldo_insuficiente_recusa_e_nada_e_gravado(familia, estoque_arroz, voluntario):
    with pytest.raises(services.SaldoInsuficiente):
        services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("21"))])
    assert Entrega.objects.count() == 0
    assert services.saldo_utilizavel(estoque_arroz) == D("20")


def test_falha_em_um_item_desfaz_a_entrega_inteira(familia, estoque_arroz, voluntario):
    feijao = Item.objects.create(nome="Feijão", unidade="kg")  # sem estoque
    with pytest.raises(services.SaldoInsuficiente):
        services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5")), (feijao, D("1"))])
    assert services.saldo_utilizavel(estoque_arroz) == D("20")  # a baixa do arroz foi desfeita
    assert Entrega.objects.count() == 0


def test_lote_vencido_nao_pode_sair_em_entrega(familia, arroz, voluntario):
    MovimentacaoEstoque.objects.create(
        item=arroz, tipo=Tipo.ENTRADA, quantidade=D("10"), restante=D("10"),
        data_validade=services.hoje() - timedelta(days=1),
    )
    with pytest.raises(services.SaldoInsuficiente):
        services.registrar_entrega(familia, voluntario, [(arroz, D("1"))])


def test_sai_primeiro_o_lote_que_vence_primeiro(familia, arroz, voluntario):
    hoje = services.hoje()
    perto = services.registrar_entrada(arroz, D("5"), hoje + timedelta(days=10))
    longe = services.registrar_entrada(arroz, D("5"), hoje + timedelta(days=100))
    services.registrar_entrega(familia, voluntario, [(arroz, D("6"))])
    perto.refresh_from_db()
    longe.refresh_from_db()
    assert perto.restante == 0
    assert longe.restante == D("4")


def test_familia_inativa_nao_recebe(familia, estoque_arroz, voluntario):
    familia.ativa = False
    familia.save()
    with pytest.raises(services.FamiliaInativa):
        services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("1"))])


def test_entrega_sem_itens_e_recusada(familia, voluntario):
    with pytest.raises(services.ErroDeRegra):
        services.registrar_entrega(familia, voluntario, [])


def test_cancelar_devolve_estoque_e_libera_o_mes(familia, estoque_arroz, voluntario, presidente):
    entrega = services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5"))])
    services.cancelar_entrega(entrega, presidente)
    assert services.saldo_utilizavel(estoque_arroz) == D("20")
    assert MovimentacaoEstoque.objects.filter(tipo=Tipo.ESTORNO).count() == 1
    services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5"))])  # mês liberado
    with pytest.raises(services.ErroDeRegra):
        services.cancelar_entrega(entrega, presidente)  # não cancela duas vezes


def test_banco_barra_duplicidade_mesmo_sem_a_regra_de_servico(familia, voluntario):
    Entrega.objects.create(familia=familia, usuario=voluntario, data_entrega=date(2026, 5, 3))
    with pytest.raises(IntegrityError), transaction.atomic():
        Entrega.objects.create(familia=familia, usuario=voluntario, data_entrega=date(2026, 5, 20))


def test_entrada_exige_validade_para_perecivel_e_quantidade_positiva(arroz):
    with pytest.raises(services.ErroDeRegra):
        services.registrar_entrada(arroz, D("5"), None)
    with pytest.raises(services.ErroDeRegra):
        services.registrar_entrada(arroz, D("0"), services.hoje() + timedelta(days=30))


def test_alerta_de_validade_na_janela_de_15_dias(arroz):
    hoje = services.hoje()
    services.registrar_entrada(arroz, D("10"), hoje + timedelta(days=10))
    longe = Item.objects.create(nome="Macarrão", unidade="pacote")
    services.registrar_entrada(longe, D("10"), hoje + timedelta(days=40))
    nomes = [lote.item.nome for lote in services.alertas()["vencendo"]]
    assert nomes == ["Arroz"]


def test_alerta_de_estoque_baixo_some_apos_reposicao(arroz):
    hoje = services.hoje()
    services.registrar_entrada(arroz, D("2"), hoje + timedelta(days=200))  # mínimo é 5
    assert [b["item"] for b in services.alertas()["baixos"]] == [arroz]
    services.registrar_entrada(arroz, D("10"), hoje + timedelta(days=200))
    assert services.alertas()["baixos"] == []


def test_descartar_vencidos_zera_o_lote_e_mantem_historico(arroz):
    lote = MovimentacaoEstoque.objects.create(
        item=arroz, tipo=Tipo.ENTRADA, quantidade=D("10"), restante=D("10"),
        data_validade=services.hoje() - timedelta(days=3),
    )
    assert services.descartar_vencidos(arroz) == D("10")
    lote.refresh_from_db()
    assert lote.restante == 0
    assert MovimentacaoEstoque.objects.filter(tipo=Tipo.SAIDA, origem="descarte de vencido").count() == 1


def test_relatorio_mensal_confere_com_os_registros(familia, estoque_arroz, voluntario):
    services.registrar_entrega(familia, voluntario, [(estoque_arroz, D("5"))])
    hoje = services.hoje()
    r = services.relatorio_mensal(hoje.year, hoje.month)
    assert r["total_familias"] == 1
    assert r["entregue"][0]["total"] == D("5")
    assert r["doado"][0]["total"] == D("20")


@pytest.mark.parametrize("texto,ok", [("2", True), ("1,5", True), ("0", False), ("-1", False),
                                      ("abc", False), ("1.234", False), ("1e9", False)])
def test_parse_quantidade(texto, ok):
    if ok:
        assert services.parse_quantidade(texto) > 0
    else:
        with pytest.raises(ValueError):
            services.parse_quantidade(texto)
