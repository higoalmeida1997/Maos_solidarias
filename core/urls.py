from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import path

from . import views

urlpatterns = [
    path("entrar/", login_not_required(views.LoginView.as_view()), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.home, name="home"),
    path("familias/", views.familia_lista, name="familia_lista"),
    path("familias/nova/", views.familia_nova, name="familia_nova"),
    path("familias/<int:pk>/editar/", views.familia_editar, name="familia_editar"),
    path("familias/<int:pk>/alternar/", views.familia_alternar, name="familia_alternar"),
    path("estoque/", views.estoque, name="estoque"),
    path("estoque/entrada/", views.entrada_nova, name="entrada_nova"),
    path("estoque/item/novo/", views.item_novo, name="item_novo"),
    path("estoque/<int:pk>/descartar-vencidos/", views.descartar_vencidos, name="descartar_vencidos"),
    path("entregas/", views.entrega_lista, name="entrega_lista"),
    path("entregas/nova/", views.entrega_nova, name="entrega_nova"),
    path("entregas/<int:pk>/", views.entrega_detalhe, name="entrega_detalhe"),
    path("entregas/<int:pk>/cancelar/", views.entrega_cancelar, name="entrega_cancelar"),
    path("relatorio/", views.relatorio, name="relatorio"),
]
