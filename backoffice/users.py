"""User management for system administrators: every account (staff, committee, artists, organisations)."""
import csv

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import DISTRICTS, Profile, User
from core.permissions import role_required
from portal.models import AuditLog
from portal.services import audit, notify

admin_only = role_required(User.SYSADMIN)


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "role", "district", "is_active", "email_verified", "sms_opt_in"]
        help_texts = {"district": "Required for district officers. It limits what they can see."}

    def clean(self):
        d = super().clean()
        if d.get("role") == User.DISTRICT_OFFICER and not d.get("district"):
            self.add_error("district", "District officers must be linked to a district.")
        return d


def send_set_password(request, user):
    form = PasswordResetForm({"email": user.email})
    if form.is_valid():
        form.save(request=request, use_https=request.is_secure(), email_template_name="emails/password_reset.txt",
                  subject_template_name="emails/password_reset_subject.txt")


def end_sessions(user):
    """Sign the user out everywhere (used on deactivation and role changes)."""
    n = 0
    for s in Session.objects.filter(expire_date__gte=timezone.now()):
        if str(s.get_decoded().get("_auth_user_id")) == str(user.pk):
            s.delete()
            n += 1
    return n


@admin_only
def user_list(request):
    qs = User.objects.select_related("profile").order_by("-date_joined")
    f = request.GET
    if f.get("q"):
        q = f["q"]
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q)
                       | Q(profile__org_name__icontains=q) | Q(profile__registration_number__icontains=q))
    if f.get("role"):
        qs = qs.filter(role=f["role"])
    if f.get("district"):
        qs = qs.filter(district=f["district"])
    if f.get("state") == "active":
        qs = qs.filter(is_active=True)
    elif f.get("state") == "inactive":
        qs = qs.filter(is_active=False)
    elif f.get("state") == "never":
        qs = qs.filter(last_login__isnull=True)
    elif f.get("state") == "nomfa":
        qs = qs.filter(role__in=User.STAFF_ROLES, mfa_enabled=False)
    if f.get("export") == "csv":
        audit(request, "users.export", None, count=qs.count())
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="nacb-users.csv"'
        resp.write("﻿")
        w = csv.writer(resp)
        w.writerow(["Email", "Name", "Role", "District", "Active", "Email verified", "MFA", "Joined", "Last sign-in"])
        for u in qs:
            w.writerow([u.email, u.get_full_name(), u.get_role_display(), u.get_district_display(), u.is_active,
                        u.email_verified, u.mfa_enabled, u.date_joined.date(), u.last_login or ""])
        return resp
    counts = {r: User.objects.filter(role=r).count() for r, _ in User.ROLE_CHOICES}
    page = Paginator(qs, 30).get_page(f.get("page"))
    return render(request, "backoffice/user_list.html", {
        "page": page, "f": f, "roles": User.ROLE_CHOICES, "districts": DISTRICTS, "counts": counts,
        "total": User.objects.count(), "inactive": User.objects.filter(is_active=False).count()})


@admin_only
def user_create(request):
    form = UserForm(request.POST or None, initial={"is_active": True, "role": request.GET.get("role", User.OFFICER)})
    if request.method == "POST" and form.is_valid():
        u = form.save(commit=False)
        u.is_staff = u.role == User.SYSADMIN
        u.set_unusable_password()
        u.save()
        send_set_password(request, u)
        audit(request, "users.created", u, role=u.role)
        messages.success(request, f"Account created for {u.email}. A link to set their password has been emailed.")
        return redirect("backoffice:user_detail", pk=u.pk)
    return render(request, "backoffice/user_form.html", {"form": form, "creating": True})


@admin_only
def user_detail(request, pk):
    u = get_object_or_404(User.objects.select_related("profile"), pk=pk)
    form = UserForm(request.POST or None, instance=u)
    if request.method == "POST" and form.is_valid():
        if u == request.user and (form.cleaned_data["role"] != u.role or not form.cleaned_data["is_active"]):
            messages.error(request, "You cannot change your own role or deactivate yourself.")
            return redirect("backoffice:user_detail", pk=pk)
        before = {f: getattr(u, f) for f in form.changed_data}
        role_changed = "role" in form.changed_data
        u = form.save(commit=False)
        u.is_staff = u.role == User.SYSADMIN or u.is_superuser
        u.save()
        if u.role in User.CREATIVE_ROLES and not hasattr(u, "profile"):
            Profile.objects.create(user=u, account_type=Profile.ORGANISATION if u.role == User.ORGANISATION else Profile.INDIVIDUAL)
        if role_changed or not u.is_active:
            end_sessions(u)
        audit(request, "users.updated", u, changed={k: str(v) for k, v in before.items()})
        messages.success(request, "User updated." + (" Their open sessions were ended." if role_changed or not u.is_active else ""))
        return redirect("backoffice:user_detail", pk=pk)
    locked = cache.get(f"login-fail:{u.email.lower()}", 0) >= settings.LOGIN_MAX_ATTEMPTS
    activity = AuditLog.objects.filter(Q(actor=u) | Q(object_type="accounts.User", object_id=str(u.pk))).select_related("actor")[:40]
    logins = AuditLog.objects.filter(actor=u, action__in=["auth.login", "auth.logout"])[:10]
    failed = AuditLog.objects.filter(action="auth.login_failed", details__email=u.email)[:10]
    return render(request, "backoffice/user_detail.html", {"u": u, "form": form, "locked": locked, "activity": activity,
                                                           "logins": logins, "failed": failed})


@admin_only
@require_POST
def user_action(request, pk):
    u = get_object_or_404(User, pk=pk)
    action = request.POST.get("action")
    if u == request.user and action in ("deactivate", "signout"):
        messages.error(request, "You cannot do that to your own account.")
        return redirect("backoffice:user_detail", pk=pk)
    if action == "reset_password":
        send_set_password(request, u)
        msg = "Password reset link emailed."
    elif action == "reset_mfa":
        u.mfa_enabled, u.mfa_secret = False, ""
        u.save(update_fields=["mfa_enabled", "mfa_secret"])
        notify(u, "Two-step verification was reset", "An administrator reset your two-step verification. Set it up again from Account settings.")
        msg = "Two-step verification reset."
    elif action == "unlock":
        cache.delete(f"login-fail:{u.email.lower()}")
        msg = "Sign-in lockout cleared."
    elif action == "deactivate":
        u.is_active = False
        u.save(update_fields=["is_active"])
        n = end_sessions(u)
        msg = f"Account deactivated ({n} session(s) ended). The user can no longer sign in."
    elif action == "activate":
        u.is_active = True
        u.save(update_fields=["is_active"])
        msg = "Account reactivated."
    elif action == "signout":
        msg = f"Signed out of {end_sessions(u)} session(s)."
    elif action == "verify_email":
        u.email_verified = True
        u.save(update_fields=["email_verified"])
        msg = "Email marked as verified."
    else:
        messages.error(request, "Unknown action.")
        return redirect("backoffice:user_detail", pk=pk)
    audit(request, f"users.{action}", u)
    messages.success(request, msg)
    return redirect("backoffice:user_detail", pk=pk)


@admin_only
@require_POST
def user_bulk(request):
    ids = [i for i in request.POST.getlist("ids") if i.isdigit()]
    action = request.POST.get("bulk")
    qs = User.objects.filter(pk__in=ids).exclude(pk=request.user.pk)
    n = qs.count()
    if action == "deactivate":
        for u in qs:
            end_sessions(u)
        qs.update(is_active=False)
    elif action == "activate":
        qs.update(is_active=True)
    elif action == "reset_password":
        for u in qs:
            send_set_password(request, u)
    else:
        messages.error(request, "Choose an action.")
        return redirect("backoffice:user_list")
    audit(request, f"users.bulk_{action}", None, count=n)
    messages.success(request, f"{n} account(s) updated.")
    return redirect(request.POST.get("next") or "backoffice:user_list")
