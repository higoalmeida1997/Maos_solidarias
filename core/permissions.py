from functools import wraps

from django.core.exceptions import PermissionDenied

GRUPO_PRESIDENTE = "Presidente"
GRUPO_VOLUNTARIO = "Voluntario"


def eh_presidente(user):
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=GRUPO_PRESIDENTE).exists())
    )


def presidente_required(view):
    """Autorização no servidor: só a presidente executa a operação (403 caso contrário)."""

    @wraps(view)
    def envolvido(request, *args, **kwargs):
        if not eh_presidente(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvido
