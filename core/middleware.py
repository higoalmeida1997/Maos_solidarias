class CabecalhosDeSegurancaMiddleware:
    """Content-Security-Policy restritiva, sem scripts nem estilos inline, e sem cache de páginas."""

    CSP = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/gestao-interna/"):  # o admin do Django usa scripts inline
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "no-store"  # voltar após "Sair" não reabre telas
        return response
