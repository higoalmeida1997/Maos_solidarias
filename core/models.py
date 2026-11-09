from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from decimal import Decimal

validar_contato = RegexValidator(
    r"^[0-9 ()+-]{8,20}$", "Use apenas números, espaços, parênteses, + e - (8 a 20 caracteres)."
)


class Familia(models.Model):
    nome_responsavel = models.CharField("Nome do responsável", max_length=150)
    contato = models.CharField(
        "Contato (telefone/WhatsApp)", max_length=20, blank=True, validators=[validar_contato]
    )
    bairro = models.CharField("Bairro", max_length=80)
    num_pessoas = models.PositiveIntegerField(
        "Número de pessoas", validators=[MinValueValidator(1)]
    )
    observacoes = models.TextField("Observações", blank=True, max_length=500)
    ativa = models.BooleanField("Ativa", default=True)
    data_cadastro = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ["nome_responsavel"]
        verbose_name = "família"
        verbose_name_plural = "famílias"

    def __str__(self):
        return f"{self.nome_responsavel} ({self.bairro})"


class Item(models.Model):
    class Unidade(models.TextChoices):
        KG = "kg", "kg"
        UN = "un", "unidade"
        LITRO = "l", "litro"
        PACOTE = "pacote", "pacote"

    nome = models.CharField("Nome", max_length=80, unique=True)
    unidade = models.CharField("Unidade", max_length=10, choices=Unidade.choices)
    estoque_minimo = models.DecimalField(
        "Estoque mínimo", max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0"))],
    )
    perecivel = models.BooleanField("Exige data de validade", default=True)
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class MovimentacaoEstoque(models.Model):
    """Livro-razão do estoque: nunca editado nem apagado; erros são corrigidos por ajuste.

    Cada ENTRADA é um lote e guarda em `restante` o que ainda não saiu. Cada SAÍDA aponta para o
    lote de onde saiu (`lote`), o que permite estornar e descartar com rastreabilidade.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída"
        ESTORNO = "estorno", "Estorno"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movimentacoes")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    restante = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_validade = models.DateField(null=True, blank=True)
    data_movimento = models.DateTimeField(default=timezone.now)
    origem = models.CharField(max_length=100, blank=True)
    entrega = models.ForeignKey(
        "Entrega", null=True, blank=True, on_delete=models.PROTECT, related_name="movimentacoes"
    )
    lote = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="consumos"
    )

    class Meta:
        ordering = ["-data_movimento", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="mov_quantidade_positiva"),
            models.CheckConstraint(condition=Q(restante__gte=0), name="mov_restante_nao_negativo"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.quantidade} {self.item}"


class Entrega(models.Model):
    familia = models.ForeignKey(Familia, on_delete=models.PROTECT, related_name="entregas")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_registradas"
    )
    data_entrega = models.DateField()
    mes_referencia = models.CharField(max_length=7)  # AAAA-MM
    observacao = models.CharField(max_length=200, blank=True)
    cancelada = models.BooleanField(default=False)
    cancelada_em = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="entregas_canceladas",
    )

    class Meta:
        ordering = ["-data_entrega", "-id"]
        constraints = [
            # Segunda proteção contra duplicidade, no banco: uma entrega ativa por família por mês.
            models.UniqueConstraint(
                fields=["familia", "mes_referencia"],
                condition=Q(cancelada=False),
                name="uniq_entrega_familia_mes",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.mes_referencia:
            self.mes_referencia = self.data_entrega.strftime("%Y-%m")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Entrega {self.data_entrega:%d/%m/%Y} - {self.familia}"


class EntregaItem(models.Model):
    entrega = models.ForeignKey(Entrega, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entrega", "item"], name="uniq_entregaitem"),
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="entregaitem_qtd_positiva"),
        ]
