from .permissions import eh_presidente


def perfil(request):
    return {"eh_presidente": eh_presidente(request.user)}
