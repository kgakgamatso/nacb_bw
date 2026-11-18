class SecurityHeadersMiddleware:
    """Content-Security-Policy and related headers (OWASP A05)."""

    CSP = (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; frame-src https://www.youtube-nocookie.com https://www.google.com; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
