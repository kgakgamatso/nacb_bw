from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_save
from django.dispatch import receiver

from portal.services import audit

from .models import Profile, User


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created and instance.role in User.CREATIVE_ROLES:
        Profile.objects.get_or_create(
            user=instance,
            defaults={"account_type": Profile.ORGANISATION if instance.role == User.ORGANISATION else Profile.INDIVIDUAL},
        )


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    audit(request, "auth.login", user, actor=user)


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user:
        audit(request, "auth.logout", user, actor=user)
