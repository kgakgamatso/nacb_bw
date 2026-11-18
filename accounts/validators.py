import re

from django.core.exceptions import ValidationError


class ComplexityValidator:
    """Require upper, lower, digit and symbol characters."""

    def validate(self, password, user=None):
        checks = [r"[A-Z]", r"[a-z]", r"\d", r"[^A-Za-z0-9]"]
        if not all(re.search(c, password) for c in checks):
            raise ValidationError(self.get_help_text(), code="password_too_simple")

    def get_help_text(self):
        return "Your password must include upper- and lower-case letters, a number and a symbol."
