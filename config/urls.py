from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Painel administrativo em endereço não padrão (RNF02: configuração segura)
    path("gestao-interna/", admin.site.urls),
    path("", include("core.urls")),
]
