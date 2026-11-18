from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class MFAEnforcementMiddleware:
    """When REQUIRE_STAFF_MFA is on, NACB staff must enrol in MFA before using the system."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (settings.REQUIRE_STAFF_MFA and user and user.is_authenticated
                and user.is_nacb_staff and not user.mfa_enabled):
            allowed = (reverse("accounts:mfa_setup"), reverse("accounts:logout"), settings.STATIC_URL)
            if not request.path.startswith(tuple("/" + a.lstrip("/") for a in allowed)):
                return redirect("accounts:mfa_setup")
        return self.get_response(request)
