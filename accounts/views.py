import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.permissions import creative_required
from portal.services import audit, notify, notify_staff

from . import totp
from .forms import AccountForm, LoginForm, MFACodeForm, PortfolioForm, PrivacyForm, ProfileForm, SignupForm
from .models import PortfolioItem, Profile, User

EMAIL_SALT = "nacb-email-verify"


def send_verification(request, user):
    token = signing.dumps(user.pk, salt=EMAIL_SALT)
    link = reverse("accounts:verify_email", args=[token])
    notify(user, "Verify your email address",
           "Welcome to the NACB Digital Platform. Please confirm your email address to activate notifications.", link)


def signup(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    form = SignupForm(request.POST or None, initial={"account_type": request.GET.get("type", Profile.INDIVIDUAL)})
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit(request, "account.signup", user, actor=user, account_type=user.role)
        send_verification(request, user)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Your account has been created. Next, complete your National Artist Register profile.")
        return redirect("accounts:profile_edit")
    return render(request, "accounts/signup.html", {"form": form})


def verify_email(request, token):
    try:
        pk = signing.loads(token, salt=EMAIL_SALT, max_age=60 * 60 * 72)
    except signing.BadSignature:
        messages.error(request, "This verification link is invalid or has expired.")
        return redirect("portal:home")
    user = get_object_or_404(User, pk=pk)
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    audit(request, "account.email_verified", user, actor=user)
    messages.success(request, "Thank you. Your email address is verified.")
    return redirect("portal:dashboard" if request.user.is_authenticated else "accounts:login")


@login_required
@require_POST
def resend_verification(request):
    send_verification(request, request.user)
    messages.info(request, "We have sent a new verification link to your email address.")
    return redirect("portal:dashboard")


def _lock_key(request, email):
    return f"login-fail:{email.lower()}"


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return reverse(settings.LOGIN_REDIRECT_URL)


def login_view(request):
    if request.user.is_authenticated:
        return redirect("portal:dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        key = _lock_key(request, email)
        attempts = cache.get(key, 0)
        if attempts >= settings.LOGIN_MAX_ATTEMPTS:
            messages.error(request, f"Too many failed attempts. Please wait {settings.LOGIN_LOCKOUT_MINUTES} minutes or reset your password.")
            audit(request, "auth.locked_out", None, email=email)
            return render(request, "accounts/login.html", {"form": form})
        user = authenticate(request, email=email, password=form.cleaned_data["password"])
        if user is None:
            cache.set(key, attempts + 1, settings.LOGIN_LOCKOUT_MINUTES * 60)
            audit(request, "auth.login_failed", None, email=email)
            form.add_error(None, "Incorrect email or password.")
        else:
            cache.delete(key)
            if user.mfa_enabled:
                request.session["mfa_user"] = user.pk
                request.session["mfa_next"] = _safe_next(request)
                return redirect("accounts:mfa_verify")
            login(request, user)
            return redirect(_safe_next(request))
    return render(request, "accounts/login.html", {"form": form, "next": request.GET.get("next", "")})


def mfa_verify(request):
    pk = request.session.get("mfa_user")
    if not pk:
        return redirect("accounts:login")
    user = get_object_or_404(User, pk=pk)
    form = MFACodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        key = f"mfa-fail:{pk}"
        fails = cache.get(key, 0)
        if fails < 5 and totp.verify(user.mfa_secret, form.cleaned_data["code"]):
            nxt = request.session.pop("mfa_next", reverse("portal:dashboard"))
            request.session.pop("mfa_user", None)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            cache.delete(key)
            return redirect(nxt)
        cache.set(key, fails + 1, 900)
        audit(request, "auth.mfa_failed", user, actor=user)
        form.add_error("code", "That code is not valid. Check your authenticator app and try again.")
    return render(request, "accounts/mfa_verify.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("portal:home")


@login_required
def account_settings(request):
    post = request.POST if request.method == "POST" else None
    form = AccountForm(post if post and "save_account" in post else None, instance=request.user, prefix="acc")
    pw_form = PasswordChangeForm(request.user, post if post and "change_password" in post else None, prefix="pw")
    if form.is_bound and form.is_valid():
        form.save()
        audit(request, "account.updated", request.user)
        messages.success(request, "Account details saved.")
        return redirect("accounts:settings")
    if pw_form.is_bound and pw_form.is_valid():
        user = pw_form.save()
        update_session_auth_hash(request, user)
        audit(request, "account.password_changed", user)
        notify(user, "Your password was changed", "If you did not make this change, contact NACB immediately.")
        messages.success(request, "Password changed.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {"form": form, "pw_form": pw_form})


@login_required
def mfa_setup(request):
    user = request.user
    if user.mfa_enabled:
        return render(request, "accounts/mfa_setup.html", {"enabled": True})
    secret = request.session.get("mfa_pending") or totp.generate_secret()
    request.session["mfa_pending"] = secret
    form = MFACodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if totp.verify(secret, form.cleaned_data["code"]):
            user.mfa_secret, user.mfa_enabled = secret, True
            user.save(update_fields=["mfa_secret", "mfa_enabled"])
            request.session.pop("mfa_pending", None)
            audit(request, "account.mfa_enabled", user)
            messages.success(request, "Two-step verification is now on for your account.")
            return redirect("accounts:settings")
        form.add_error("code", "Code not recognised. Make sure your phone's clock is correct and try again.")
    spaced = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return render(request, "accounts/mfa_setup.html", {
        "form": form, "secret": spaced, "uri": totp.provisioning_uri(secret, user.email)})


@login_required
@require_POST
def mfa_disable(request):
    user = request.user
    if settings.REQUIRE_STAFF_MFA and user.is_nacb_staff:
        messages.error(request, "Two-step verification is mandatory for staff accounts.")
        return redirect("accounts:settings")
    if not totp.verify(user.mfa_secret, request.POST.get("code")):
        messages.error(request, "Enter a valid code from your authenticator app to turn off two-step verification.")
        return redirect("accounts:mfa_setup")
    user.mfa_enabled, user.mfa_secret = False, ""
    user.save(update_fields=["mfa_enabled", "mfa_secret"])
    audit(request, "account.mfa_disabled", user)
    messages.success(request, "Two-step verification turned off.")
    return redirect("accounts:settings")


# ---------------------------------------------------------------- Register profile

@creative_required
def profile_edit(request):
    profile = request.user.profile
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        changed = form.changed_data
        profile = form.save()
        if profile.status == Profile.VERIFIED and set(changed) & {"national_id", "org_reg_number", "id_document", "org_name"}:
            profile.status = Profile.PENDING
            profile.save(update_fields=["status"])
            messages.warning(request, "You changed identity details, so your registration will be re-verified by NACB.")
        audit(request, "registry.profile_updated", profile, fields=changed)
        if "submit" in request.POST:
            return submit_profile(request)
        messages.success(request, "Profile saved.")
        return redirect("accounts:profile_edit")
    return render(request, "accounts/profile_edit.html", {
        "form": form, "profile": profile, "required_names": [f for f, _ in profile.required_fields()]})


def submit_profile(request):
    profile = request.user.profile
    missing = profile.missing_fields()
    if missing:
        messages.error(request, "Please complete the following before submitting: " + ", ".join(missing))
        return redirect("accounts:profile_edit")
    if profile.status in (Profile.INCOMPLETE, Profile.FLAGGED):
        profile.status = Profile.PENDING
        profile.submitted_at = timezone.now()
        profile.save(update_fields=["status", "submitted_at"])
        audit(request, "registry.submitted", profile)
        notify(request.user, "Registration submitted",
               "Your National Artist Register application has been received and will be verified by NACB.",
               reverse("portal:dashboard"), sms=True)
        notify_staff("New registration awaiting verification", profile.display_name,
                     reverse("backoffice:registry_detail", args=[profile.pk]), district=profile.district)
        messages.success(request, "Submitted for verification. We will notify you once NACB has reviewed your registration.")
    else:
        messages.success(request, "Profile saved.")
    return redirect("portal:dashboard")


@creative_required
def privacy(request):
    profile = request.user.profile
    form = PrivacyForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "registry.privacy_updated", profile, **form.cleaned_data)
        messages.success(request, "Privacy settings saved.")
        return redirect("accounts:privacy")
    return render(request, "accounts/privacy.html", {"form": form, "profile": profile})


@creative_required
def portfolio(request):
    profile = request.user.profile
    form = PortfolioForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.profile = profile
        item.save()
        audit(request, "registry.portfolio_added", item)
        messages.success(request, f"“{item.title}” added to your portfolio.")
        return redirect("accounts:portfolio")
    return render(request, "accounts/portfolio.html", {"form": form, "items": profile.portfolio.all(), "profile": profile})


@creative_required
@require_POST
def portfolio_delete(request, pk):
    item = get_object_or_404(PortfolioItem, pk=pk, profile__user=request.user)
    audit(request, "registry.portfolio_deleted", item)
    item.file.delete(save=False)
    item.delete()
    messages.info(request, "Portfolio item removed.")
    return redirect("accounts:portfolio")


def _serve(fieldfile, as_attachment=False):
    if not fieldfile:
        raise Http404
    ctype = mimetypes.guess_type(fieldfile.name)[0] or "application/octet-stream"
    resp = FileResponse(fieldfile.open("rb"), content_type=ctype, as_attachment=as_attachment,
                        filename=fieldfile.name.rsplit("/", 1)[-1])
    resp["Cache-Control"] = "private, no-store"
    return resp


def portfolio_file(request, pk):
    item = get_object_or_404(PortfolioItem, pk=pk)
    user = request.user
    if not (item.publicly_visible() or (user.is_authenticated and (user.is_nacb_staff or item.profile.user_id == user.pk))):
        raise PermissionDenied
    return _serve(item.file)


@login_required
def id_document(request, pk):
    profile = get_object_or_404(Profile, pk=pk)
    if not (request.user.is_nacb_staff or profile.user_id == request.user.pk):
        raise PermissionDenied
    if request.user.is_nacb_staff:
        audit(request, "registry.id_document_viewed", profile)
    return _serve(profile.id_document)
