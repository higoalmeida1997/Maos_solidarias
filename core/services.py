"""Camada de regras de negócio (RF01 a RF05).

As Views só validam o formato e chamam estas funções; nenhuma regra fica nas telas.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import Entrega, EntregaItem, Familia, Item, MovimentacaoEstoque

Tipo = MovimentacaoEstoque.Tipo
ZERO = Decimal("0")
CENTAVO = Decimal("0.01")


class ErroDeRegra(Exception):
    """Violação de regra de negócio com mensagem pronta para o usuário."""


class EntregaDuplicada(ErroDeRegra):
    def __init__(self, data_anterior):
        self.data_anterior = data_anterior
        super().__init__(f"Esta família já recebeu a cesta em {data_anterior:%d/%m/%Y}.")


class SaldoInsuficiente(ErroDeRegra):
    pass


class FamiliaInativa(ErroDeRegra):
    pass


def hoje():
    return timezone.localdate()


def parse_quantidade(texto):
    """Converte texto digitado em Decimal > 0 com no máximo 2 casas; ValueError com mensagem clara."""
    try:
        valor = Decimal(str(texto).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError("Informe um número, por exemplo 2 ou 1,5.")
    if not valor.is_finite() or valor <= 0:
        raise ValueError("Informe uma quantidade maior que zero.")
    if valor > Decimal("99999"):
        raise ValueError("Quantidade grande demais. Confira o valor.")
    if valor != valor.quantize(CENTAVO):
        raise ValueError("Use no máximo 2 casas decimais.")
    return valor.quantize(CENTAVO)


# ---------------------------------------------------------------- estoque (RF02)

def lotes_utilizaveis(item, data):
    """Lotes com saldo e dentro da validade na data informada."""
    return MovimentacaoEstoque.objects.filter(
        item=item, tipo=Tipo.ENTRADA, restante__gt=0
    ).filter(Q(data_validade__isnull=True) | Q(data_validade__gte=data))


def saldo_utilizavel(item, data=None):
    """Saldo calculado (nunca digitado): soma do que resta nos lotes dentro da validade."""
    total = lotes_utilizaveis(item, data or hoje()).aggregate(t=Sum("restante"))["t"]
    return total or ZERO


def registrar_entrada(item, quantidade, data_validade=None, origem=""):
    if quantidade <= 0:
        raise ErroDeRegra("A quantidade deve ser maior que zero.")
    if not item.ativo:
        raise ErroDeRegra("Este item está inativo.")
    if item.perecivel and data_validade is None:
        raise ErroDeRegra("Informe a data de validade deste item.")
    return MovimentacaoEstoque.objects.create(
        item=item, tipo=Tipo.ENTRADA, quantidade=quantidade, restante=quantidade,
        data_validade=data_validade, origem=origem[:100],
    )


def descartar_vencidos(item, data=None):
    """Registra a saída de lotes vencidos (descarte), preservando o histórico. Retorna o total."""
    data = data or hoje()
    total = ZERO
    with transaction.atomic():
        vencidos = MovimentacaoEstoque.objects.select_for_update().filter(
            item=item, tipo=Tipo.ENTRADA, restante__gt=0, data_validade__lt=data
        )
        for lote in vencidos:
            MovimentacaoEstoque.objects.create(
                item=item, tipo=Tipo.SAIDA, quantidade=lote.restante, restante=0,
                data_validade=lote.data_validade, origem="descarte de vencido", lote=lote,
            )
            total += lote.restante
            lote.restante = ZERO
            lote.save(update_fields=["restante"])
    return total


def alertas(data=None, dias=None):
    """RF04: lotes vencendo na janela, lotes vencidos e itens abaixo do estoque mínimo."""
    data = data or hoje()
    dias = settings.ALERTA_VALIDADE_DIAS if dias is None else dias
    lotes = MovimentacaoEstoque.objects.filter(
        tipo=Tipo.ENTRADA, restante__gt=0, item__ativo=True
    ).select_related("item")
    vencidos = lotes.filter(data_validade__lt=data).order_by("data_validade")
    vencendo = lotes.filter(
        data_validade__gte=data, data_validade__lte=data + timedelta(days=dias)
    ).order_by("data_validade")
    baixos = []
    for item in Item.objects.filter(ativo=True, estoque_minimo__gt=0):
        saldo = saldo_utilizavel(item, data)
        if saldo < item.estoque_minimo:
            baixos.append({"item": item, "saldo": saldo})
    return {"vencidos": vencidos, "vencendo": vencendo, "baixos": baixos, "dias": dias}


# ---------------------------------------------------------------- entregas (RF03)

def _consumir(entrega, item, quantidade, data):
    lotes = list(
        lotes_utilizaveis(item, data)
        .select_for_update()
        .order_by(F("data_validade").asc(nulls_last=True), "id")
    )
    disponivel = sum((lote.restante for lote in lotes), ZERO)
    if disponivel < quantidade:
        raise SaldoInsuficiente(
            f"Saldo insuficiente de {item.nome}: disponível {disponivel:.2f} {item.get_unidade_display()}."
        )
    faltante = quantidade
    for lote in lotes:  # sai primeiro o que vence primeiro
        if faltante <= 0:
            break
        usar = min(lote.restante, faltante)
        lote.restante -= usar
        lote.save(update_fields=["restante"])
        MovimentacaoEstoque.objects.create(
            item=item, tipo=Tipo.SAIDA, quantidade=usar, restante=0,
            data_validade=lote.data_validade, origem="entrega", entrega=entrega, lote=lote,
        )
        faltante -= usar
    EntregaItem.objects.create(entrega=entrega, item=item, quantidade=quantidade)


def registrar_entrega(familia, usuario, itens, data_entrega=None, observacao=""):
    """Grava a entrega e baixa o estoque em uma única transação.

    Regras: família ativa; uma entrega ativa por família por mês; todos os itens com saldo
    dentro da validade. Qualquer falha desfaz tudo (nada é gravado pela metade).
    """
    data_entrega = data_entrega or hoje()
    agregados = {}
    for item, quantidade in itens:
        if quantidade <= 0:
            raise ErroDeRegra("As quantidades devem ser maiores que zero.")
        atual = agregados.get(item.pk, (item, ZERO))[1]
        agregados[item.pk] = (item, atual + quantidade)
    if not agregados:
        raise ErroDeRegra("Selecione ao menos um item com quantidade maior que zero.")

    mes = data_entrega.strftime("%Y-%m")
    try:
        with transaction.atomic():
            familia = Familia.objects.select_for_update().get(pk=familia.pk)
            if not familia.ativa:
                raise FamiliaInativa("Esta família está inativa e não pode receber entregas.")
            anterior = Entrega.objects.filter(
                familia=familia, mes_referencia=mes, cancelada=False
            ).first()
            if anterior:
                raise EntregaDuplicada(anterior.data_entrega)
            entrega = Entrega.objects.create(
                familia=familia, usuario=usuario, data_entrega=data_entrega,
                mes_referencia=mes, observacao=observacao[:200],
            )
            for item, quantidade in agregados.values():
                _consumir(entrega, item, quantidade, data_entrega)
    except IntegrityError:  # corrida entre dois voluntários: o banco barrou a segunda
        anterior = Entrega.objects.filter(
            familia=familia, mes_referencia=mes, cancelada=False
        ).first()
        raise EntregaDuplicada(anterior.data_entrega if anterior else data_entrega)
    return entrega


def cancelar_entrega(entrega, usuario):
    """Cancela (só a presidente, verificado na View) e estorna o estoque nos lotes de origem."""
    with transaction.atomic():
        entrega = Entrega.objects.select_for_update().get(pk=entrega.pk)
        if entrega.cancelada:
            raise ErroDeRegra("Esta entrega já foi cancelada.")
        saidas = MovimentacaoEstoque.objects.filter(entrega=entrega, tipo=Tipo.SAIDA).select_related("lote")
        for saida in saidas:
            lote = MovimentacaoEstoque.objects.select_for_update().get(pk=saida.lote_id)
            lote.restante += saida.quantidade
            lote.save(update_fields=["restante"])
            MovimentacaoEstoque.objects.create(
                item=saida.item, tipo=Tipo.ESTORNO, quantidade=saida.quantidade, restante=0,
                data_validade=saida.data_validade, origem="cancelamento de entrega",
                entrega=entrega, lote=lote,
            )
        entrega.cancelada = True
        entrega.cancelada_em = timezone.now()
        entrega.cancelada_por = usuario
        entrega.save(update_fields=["cancelada", "cancelada_em", "cancelada_por"])
    return entrega


# ---------------------------------------------------------------- relatório (RF05)

def relatorio_mensal(ano, mes):
    """Dados agregados do mês (sem dados pessoais das famílias)."""
    mes_ref = f"{ano:04d}-{mes:02d}"
    entregas = Entrega.objects.filter(mes_referencia=mes_ref, cancelada=False)
    entregue = (
        EntregaItem.objects.filter(entrega__in=entregas)
        .values("item__nome", "item__unidade").annotate(total=Sum("quantidade")).order_by("item__nome")
    )
    doado = (
        MovimentacaoEstoque.objects.filter(
            tipo=Tipo.ENTRADA, data_movimento__year=ano, data_movimento__month=mes
        )
        .values("item__nome", "item__unidade").annotate(total=Sum("quantidade")).order_by("item__nome")
    )
    return {
        "mes_referencia": mes_ref,
        "total_familias": entregas.values("familia").distinct().count(),
        "total_entregas": entregas.count(),
        "entregue": list(entregue),
        "doado": list(doado),
    }
