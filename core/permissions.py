from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Allow access only to authenticated users whose role is in `roles`.
    System administrators (superusers) always pass."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in roles:
                return view(request, *args, **kwargs)
            raise PermissionDenied
        return wrapped

    return decorator


def staff_required(view):
    from accounts.models import User

    return role_required(*User.STAFF_ROLES)(view)


def creative_required(view):
    from accounts.models import User

    return role_required(User.ARTIST, User.ORGANISATION)(view)


def district_scope(qs, user, field="district"):
    """District officers only see records from their own district (least privilege)."""
    from accounts.models import User

    if user.role == User.DISTRICT_OFFICER and not user.is_superuser:
        return qs.filter(**{field: user.district})
    return qs
