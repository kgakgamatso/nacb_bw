"""Cross-cutting services: audit logging and multi-channel notifications (FR-8, FR-9.3)."""
import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger("nacb")


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def audit(request, action, obj=None, actor=None, **details):
    from .models import AuditLog

    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        object_repr=str(obj)[:250] if obj is not None else "",
        details={k: (v if isinstance(v, (str, int, float, bool, type(None), list, dict)) else str(v)) for k, v in details.items()},
        ip_address=client_ip(request),
    )


def send_sms(phone, message):
    """Pluggable SMS gateway. Returns True when the message was handed off."""
    if not phone:
        return False
    if settings.SMS_BACKEND == "http" and settings.SMS_URL:
        payload = json.dumps({"to": phone, "from": settings.SMS_SENDER_ID, "message": message[:459]}).encode()
        req = urllib.request.Request(settings.SMS_URL, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {settings.SMS_API_KEY}"})
        try:
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception as exc:  # gateway failure must not break the user flow
            logger.warning("SMS send failed: %s", exc)
            return False
    logger.info("[SMS to %s] %s", phone, message)
    return True


def notify(user, title, message="", link="", email=True, sms=False):
    """Create an in-app notification and optionally send email / SMS."""
    from .models import Notification

    n = Notification.objects.create(user=user, title=title, message=message, link=link)
    if email and user.email:
        body = render_to_string("emails/notification.txt", {
            "user": user, "title": title, "message": message,
            "link": (settings.SITE_URL + link) if link.startswith("/") else link,
        })
        try:
            send_mail(f"NACB: {title}", body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
            n.emailed = True
        except Exception as exc:
            logger.warning("Email to %s failed: %s", user.email, exc)
    if sms and user.sms_opt_in:
        phone = user.phone or getattr(getattr(user, "profile", None), "phone", "")
        n.sms_sent = send_sms(phone, f"NACB: {title}. {message[:200]}")
    n.save(update_fields=["emailed", "sms_sent"])
    return n


def notify_staff(title, message="", link="", roles=None, district=None):
    from accounts.models import User

    roles = roles or [User.OFFICER]
    from django.db.models import Q

    cond = Q(role__in=roles)
    if district:
        cond |= Q(role=User.DISTRICT_OFFICER, district=district)
    for u in User.objects.filter(cond, is_active=True).distinct():
        notify(u, title, message, link, email=False)
