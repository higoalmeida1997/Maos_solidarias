import csv
import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .forms import EntradaForm, EntregaForm, FamiliaForm, ItemForm
from .models import Entrega, Familia, Item
from .permissions import presidente_required

auditoria = logging.getLogger("core.auditoria")

# ------------------------------------------------------------------ login (RNF01)

MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 15 * 60
MSG_BLOQUEIO = "Não foi possível entrar. Aguarde alguns minutos e tente novamente."


def _chaves_login(username):
    base = username.strip().lower()[:150]
    return f"login:falhas:{base}", f"login:bloqueio:{base}"


class LoginView(auth_views.LoginView):
    """Login com bloqueio de 15 min após 5 falhas; mensagens genéricas (não revelam se o usuário existe)."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        _, bloqueio = _chaves_login(request.POST.get("username", ""))
        if cache.get(bloqueio):
            form = self.get_form()
            form.add_error(None, MSG_BLOQUEIO)
            return auth_views.LoginView.form_invalid(self, form)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        usuario = self.request.POST.get("username", "")
        falhas, bloqueio = _chaves_login(usuario)
        total = cache.get(falhas, 0) + 1
        cache.set(falhas, total, BLOQUEIO_SEGUNDOS)
        if total >= MAX_TENTATIVAS:
            cache.set(bloqueio, True, BLOQUEIO_SEGUNDOS)
            auditoria.warning("Login bloqueado por tentativas repetidas: %s", usuario[:50])
        return super().form_invalid(form)

    def form_valid(self, form):
        falhas, bloqueio = _chaves_login(self.request.POST.get("username", ""))
        cache.delete_many([falhas, bloqueio])
        return super().form_valid(form)


# ------------------------------------------------------------------ início

def home(request):
    return render(request, "core/home.html", {"alertas": services.alertas()})


# ------------------------------------------------------------------ famílias (RF01)

def familia_lista(request):
    q = request.GET.get("q", "").strip()[:100]
    mostrar_inativas = request.GET.get("inativas") == "1"
    familias = Familia.objects.all()
    if not mostrar_inativas:
        familias = familias.filter(ativa=True)
    if q:
        familias = familias.filter(nome_responsavel__icontains=q)  # ORM: consulta parametrizada
    pagina = Paginator(familias, 25).get_page(request.GET.get("pagina"))
    return render(request, "core/familia_lista.html", {
        "pagina": pagina, "q": q, "mostrar_inativas": mostrar_inativas,
    })


def _salvar_familia(request, instancia=None):
    form = FamiliaForm(request.POST or None, instance=instancia)
    duplicado = False
    if request.method == "POST" and form.is_valid():
        if instancia is None and form.cleaned_data["contato"]:
            duplicado = Familia.objects.filter(
                nome_responsavel__iexact=form.cleaned_data["nome_responsavel"],
                contato=form.cleaned_data["contato"],
            ).exists()
        if duplicado and not request.POST.get("confirmar_duplicado"):
            messages.warning(request, "Já existe uma família com este nome e contato. "
                                      "Marque a confirmação abaixo se for outra família.")
        else:
            familia = form.save()
            messages.success(request, f"Família de {familia.nome_responsavel} salva.")
            return redirect("familia_lista")
    return render(request, "core/familia_form.html", {
        "form": form, "instancia": instancia,
        "duplicado": duplicado and not request.POST.get("confirmar_duplicado"),
    })


def familia_nova(request):
    return _salvar_familia(request)


def familia_editar(request, pk):
    return _salvar_familia(request, get_object_or_404(Familia, pk=pk))


@require_POST
@presidente_required
def familia_alternar(request, pk):
    familia = get_object_or_404(Familia, pk=pk)
    familia.ativa = not familia.ativa
    familia.save(update_fields=["ativa"])
    auditoria.info("Família %s %s por %s", familia.pk, "ativada" if familia.ativa else "inativada", request.user)
    messages.success(request, "Família ativada." if familia.ativa else "Família inativada (o histórico foi mantido).")
    return redirect("familia_lista")


# ------------------------------------------------------------------ estoque (RF02, RF04)

def estoque(request):
    itens = [
        {"item": item, "saldo": services.saldo_utilizavel(item)}
        for item in Item.objects.filter(ativo=True)
    ]
    return render(request, "core/estoque.html", {"itens": itens, "alertas": services.alertas()})


def entrada_nova(request):
    form = EntradaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            services.registrar_entrada(d["item"], d["quantidade"], d["data_validade"], d["origem"])
        except services.ErroDeRegra as erro:
            form.add_error(None, str(erro))
        else:
            messages.success(request, f"Entrada registrada: {d['quantidade']} de {d['item'].nome}.")
            return redirect("estoque")
    return render(request, "core/entrada_form.html", {"form": form})


@presidente_required
def item_novo(request):
    form = ItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Item cadastrado.")
        return redirect("estoque")
    return render(request, "core/item_form.html", {"form": form})


@require_POST
@presidente_required
def descartar_vencidos(request, pk):
    item = get_object_or_404(Item, pk=pk)
    total = services.descartar_vencidos(item)
    auditoria.info("Descarte de vencidos de %s (%s) por %s", item.nome, total, request.user)
    messages.success(request, f"Descartado: {total} de {item.nome} vencido.")
    return redirect("estoque")


# ------------------------------------------------------------------ entregas (RF03)

def _linhas_itens(post=None):
    linhas = []
    for item in Item.objects.filter(ativo=True):
        valor = post.get(f"qtd_{item.pk}", "") if post else ""
        linhas.append({"item": item, "saldo": services.saldo_utilizavel(item), "valor": valor, "erro": ""})
    return linhas


def entrega_nova(request):
    form = EntregaForm(request.POST or None)
    linhas = _linhas_itens(request.POST if request.method == "POST" else None)
    erro_regra = ""
    if request.method == "POST":
        itens, itens_ok = [], True
        for linha in linhas:
            texto = linha["valor"].strip()
            if not texto:
                continue
            try:
                itens.append((linha["item"], services.parse_quantidade(texto)))
            except ValueError as erro:
                linha["erro"] = str(erro)
                itens_ok = False
        if form.is_valid() and itens_ok:
            d = form.cleaned_data
            try:
                entrega = services.registrar_entrega(
                    d["familia"], request.user, itens, d["data_entrega"], d["observacao"]
                )
            except services.ErroDeRegra as erro:
                erro_regra = str(erro)
                if isinstance(erro, services.EntregaDuplicada):
                    erro_regra += " Nenhuma alteração foi feita no estoque."
            else:
                messages.success(request, "Entrega registrada.")
                return redirect("entrega_detalhe", pk=entrega.pk)
    return render(request, "core/entrega_form.html", {
        "form": form, "linhas": linhas, "erro_regra": erro_regra,
    })


def entrega_lista(request):
    mes = request.GET.get("mes", "")
    try:
        ano_i, mes_i = (int(p) for p in mes.split("-"))
        date(ano_i, mes_i, 1)
    except (ValueError, TypeError):
        hoje = services.hoje()
        ano_i, mes_i = hoje.year, hoje.month
    mes_ref = f"{ano_i:04d}-{mes_i:02d}"
    entregas = Entrega.objects.filter(mes_referencia=mes_ref).select_related("familia", "usuario")
    return render(request, "core/entrega_lista.html", {"entregas": entregas, "mes_ref": mes_ref})


def entrega_detalhe(request, pk):
    entrega = get_object_or_404(Entrega.objects.select_related("familia", "usuario"), pk=pk)
    return render(request, "core/entrega_detalhe.html", {
        "entrega": entrega, "itens": entrega.itens.select_related("item"),
        "alertas": services.alertas(),
    })


@require_POST
@presidente_required
def entrega_cancelar(request, pk):
    entrega = get_object_or_404(Entrega, pk=pk)
    try:
        services.cancelar_entrega(entrega, request.user)
    except services.ErroDeRegra as erro:
        messages.error(request, str(erro))
    else:
        auditoria.info("Entrega %s cancelada por %s", entrega.pk, request.user)
        messages.success(request, "Entrega cancelada e estoque devolvido.")
    return redirect("entrega_detalhe", pk=pk)


# ------------------------------------------------------------------ relatório (RF05)

def _celula_csv(valor):
    """Evita injeção de fórmulas ao abrir o CSV em planilhas."""
    texto = str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


@presidente_required
def relatorio(request):
    hoje = services.hoje()
    try:
        ano = int(request.GET.get("ano", hoje.year))
        mes = int(request.GET.get("mes", hoje.month))
        date(ano, mes, 1)
    except (ValueError, TypeError):
        ano, mes = hoje.year, hoje.month
    dados = services.relatorio_mensal(ano, mes)
    if request.GET.get("formato") == "csv":
        resposta = HttpResponse(content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = f'attachment; filename="relatorio-{dados["mes_referencia"]}.csv"'
        w = csv.writer(resposta)
        w.writerow(["Mês", dados["mes_referencia"]])
        w.writerow(["Famílias atendidas", dados["total_familias"]])
        w.writerow([])
        w.writerow(["Entregue", "Unidade", "Quantidade"])
        for linha in dados["entregue"]:
            w.writerow([_celula_csv(linha["item__nome"]), linha["item__unidade"], linha["total"]])
        w.writerow([])
        w.writerow(["Doações recebidas", "Unidade", "Quantidade"])
        for linha in dados["doado"]:
            w.writerow([_celula_csv(linha["item__nome"]), linha["item__unidade"], linha["total"]])
        auditoria.info("Relatório %s exportado por %s", dados["mes_referencia"], request.user)
        return resposta
    return render(request, "core/relatorio.html", {"dados": dados, "ano": ano, "mes": mes})
