from django.contrib import admin

from .models import Entrega, EntregaItem, Familia, Item, MovimentacaoEstoque


@admin.register(Familia)
class FamiliaAdmin(admin.ModelAdmin):
    list_display = ("nome_responsavel", "bairro", "num_pessoas", "ativa")
    search_fields = ("nome_responsavel",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("nome", "unidade", "estoque_minimo", "ativo")


@admin.register(MovimentacaoEstoque)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ("data_movimento", "tipo", "item", "quantidade", "data_validade")
    list_filter = ("tipo",)

    # O livro-razão não é editado nem apagado pelo painel (correção é por ajuste).
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EntregaItemInline(admin.TabularInline):
    model = EntregaItem
    extra = 0
    can_delete = False
    readonly_fields = ("item", "quantidade")


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    list_display = ("data_entrega", "familia", "usuario", "cancelada")
    inlines = [EntregaItemInline]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
