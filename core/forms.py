from decimal import Decimal

from django import forms

from .models import Familia, Item
from .services import hoje

CAMPOS_TEXTO_FAMILIA = ("nome_responsavel", "contato", "bairro", "observacoes")


def sem_html(valor):
    """Defesa em profundidade contra XSS: rejeita marcação no servidor (a saída também é escapada)."""
    if valor and ("<" in valor or ">" in valor):
        raise forms.ValidationError("Não use os caracteres < e > neste campo.")
    return valor


class FamiliaForm(forms.ModelForm):
    class Meta:
        model = Familia
        fields = ["nome_responsavel", "contato", "bairro", "num_pessoas", "observacoes"]
        widgets = {
            "contato": forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off"}),
            "num_pessoas": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        dados = super().clean()
        for campo in CAMPOS_TEXTO_FAMILIA:
            valor = dados.get(campo)
            if valor:
                try:
                    sem_html(valor)
                except forms.ValidationError as erro:
                    self.add_error(campo, erro)
        return dados


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["nome", "unidade", "estoque_minimo", "perecivel"]
        widgets = {"estoque_minimo": forms.NumberInput(attrs={"min": 0, "step": "0.01", "inputmode": "decimal"})}

    def clean_nome(self):
        return sem_html(self.cleaned_data["nome"].strip())


class EntradaForm(forms.Form):
    item = forms.ModelChoiceField(Item.objects.none(), label="Item")
    quantidade = forms.DecimalField(
        label="Quantidade recebida", min_value=Decimal("0.01"), max_value=Decimal("99999"),
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    data_validade = forms.DateField(
        label="Data de validade", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Obrigatória para itens que vencem.",
    )
    origem = forms.CharField(label="Origem da doação (opcional)", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(ativo=True)

    def clean_origem(self):
        return sem_html(self.cleaned_data["origem"].strip())

    def clean(self):
        dados = super().clean()
        item, validade = dados.get("item"), dados.get("data_validade")
        if item and item.perecivel and not validade:
            self.add_error("data_validade", "Informe a data de validade deste item.")
        if validade and validade < hoje():
            self.add_error("data_validade", "Este lote já está vencido. Confira a data.")
        return dados


class EntregaForm(forms.Form):
    familia = forms.ModelChoiceField(Familia.objects.none(), label="Família")
    data_entrega = forms.DateField(
        label="Data da entrega", initial=hoje, widget=forms.DateInput(attrs={"type": "date"})
    )
    observacao = forms.CharField(label="Observação (opcional)", max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["familia"].queryset = Familia.objects.filter(ativa=True)

    def clean_data_entrega(self):
        data = self.cleaned_data["data_entrega"]
        if data > hoje():
            raise forms.ValidationError("A data da entrega não pode estar no futuro.")
        return data

    def clean_observacao(self):
        return sem_html(self.cleaned_data["observacao"].strip())
