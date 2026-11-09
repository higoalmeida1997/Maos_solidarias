"""Dados 100% fictícios para o teste de desempenho do RNF03 (200 famílias, 30 itens, 12 meses)."""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core import services
from core.models import Entrega, Familia, Item


class Command(BaseCommand):
    help = "Cria dados fictícios de demonstração (somente com DEBUG ligado, ou use --forcar)."

    def add_arguments(self, parser):
        parser.add_argument("--forcar", action="store_true")

    def handle(self, *args, **opcoes):
        if not settings.DEBUG and not opcoes["forcar"]:
            raise CommandError("Recusado: não gere dados fictícios em produção (use --forcar se for teste).")

        usuario, _ = User.objects.get_or_create(username="demo-sem-login")
        usuario.set_unusable_password()
        usuario.save()

        familias = Familia.objects.bulk_create(
            [Familia(nome_responsavel=f"Família Teste {n:03d}", bairro="Bairro Teste", num_pessoas=1 + n % 6)
             for n in range(1, 201)]
        )
        itens = []
        for n in range(1, 31):
            item, _ = Item.objects.get_or_create(
                nome=f"Item Teste {n:02d}",
                defaults={"unidade": "kg", "estoque_minimo": Decimal("10"), "perecivel": True},
            )
            services.registrar_entrada(item, Decimal("500"), services.hoje() + timedelta(days=5 + 12 * n), "Doação fictícia")
            itens.append(item)

        hoje = services.hoje()
        historico = []
        for meses_atras in range(12, 0, -1):
            ano, mes = hoje.year, hoje.month - meses_atras
            while mes <= 0:
                mes += 12
                ano -= 1
            for familia in familias[:150]:
                historico.append(Entrega(familia=familia, usuario=usuario, data_entrega=date(ano, mes, 15),
                                         mes_referencia=f"{ano:04d}-{mes:02d}"))
        Entrega.objects.bulk_create(historico)
        self.stdout.write(self.style.SUCCESS("Dados fictícios criados: 200 famílias, 30 itens, 12 meses de entregas."))
