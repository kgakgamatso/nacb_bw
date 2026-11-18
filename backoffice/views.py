import csv
import io
import secrets
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.forms import SignupForm
from accounts.models import DISTRICTS, Discipline, Profile, User
from core.permissions import district_scope, role_required, staff_required
from endorsements.models import EndorsementRequest as ER
from events.models import Event, Registration
from grants.models import GrantApplication as GA, GrantCall
from portal.models import AuditLog, Communication, ContactMessage
from portal.services import audit, notify

DISTRICT_LABELS = dict(DISTRICTS)


def _registry_qs(request):
    qs = Profile.objects.select_related("user", "primary_discipline")
    return district_scope(qs, request.user)


def _apply_registry_filters(qs, f):
    if f.get("q"):
        q = f["q"]
        qs = qs.filter(Q(registration_number__icontains=q) | Q(org_name__icontains=q) | Q(stage_name__icontains=q)
                       | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__email__icontains=q)
                       | Q(national_id__iexact=q) | Q(phone__icontains=q))
    for key, field in [("status", "status"), ("district", "district"), ("type", "account_type"), ("gender", "gender"),
                       ("level", "experience_level")]:
        if f.get(key):
            qs = qs.filter(**{field: f[key]})
    if f.get("discipline"):
        qs = qs.filter(Q(primary_discipline__slug=f["discipline"]) | Q(disciplines__slug=f["discipline"])).distinct()
    return qs


# ------------------------------------------------------------------ dashboard (FR-7.2)

@staff_required
def dashboard(request):
    user = request.user
    f = request.GET
    profiles = _registry_qs(request)
    apps = district_scope(GA.objects.exclude(status=GA.DRAFT), user, "profile__district")
    ends = district_scope(ER.objects.all(), user, "profile__district")
    if f.get("district"):
        profiles = profiles.filter(district=f["district"])
        apps = apps.filter(profile__district=f["district"])
        ends = ends.filter(profile__district=f["district"])
    if f.get("discipline"):
        profiles = profiles.filter(primary_discipline__slug=f["discipline"])
        apps = apps.filter(category__slug=f["discipline"])
    today = timezone.localdate()
    tasks = {
        "registrations": profiles.filter(status=Profile.PENDING).count(),
        "grants_new": apps.filter(status=GA.SUBMITTED).count(),
        "grants_mine": apps.filter(assigned_to=user, status__in=[GA.UNDER_REVIEW, GA.SUBMITTED]).count(),
        "grants_recommended": apps.filter(status=GA.RECOMMENDED).count() if user.can_approve else None,
        "endorsements": ends.filter(status__in=[ER.SUBMITTED, ER.UNDER_REVIEW, ER.APPROVED]).count(),
        "endorsements_overdue": ends.filter(status__in=ER.OPEN, due_date__lt=today).count(),
        "messages": ContactMessage.objects.filter(resolved=False).count(),
    }
    month_ago = timezone.now() - timedelta(days=30)
    stats = {
        "verified": profiles.filter(status=Profile.VERIFIED).count(),
        "total": profiles.count(),
        "new_30": profiles.filter(created_at__gte=month_ago).count(),
        "apps_total": apps.count(),
        "approved": apps.filter(status=GA.APPROVED).count(),
        "awarded": apps.filter(status=GA.APPROVED).aggregate(s=Sum("amount_awarded"))["s"] or 0,
        "requested": apps.aggregate(s=Sum("amount_requested"))["s"] or 0,
    }
    by_district = _counts(profiles.values_list("district").annotate(c=Count("id")), DISTRICT_LABELS)
    by_discipline = list(profiles.exclude(primary_discipline=None).values_list("primary_discipline__name")
                         .annotate(c=Count("id")).order_by("-c")[:8])
    return render(request, "backoffice/dashboard.html", {
        "tasks": tasks, "stats": stats, "by_district": by_district, "by_discipline": by_discipline,
        "max_d": max([c for _, c in by_district] or [1]), "max_disc": max([c for _, c in by_discipline] or [1]),
        "my_grants": apps.filter(assigned_to=user, status__in=GA.OPEN_STAFF)[:6],
        "pending_regs": profiles.filter(status=Profile.PENDING).order_by("submitted_at")[:6],
        "urgent_ends": ends.filter(status__in=ER.OPEN).order_by("due_date")[:6],
        "calls": GrantCall.objects.filter(status="published").annotate(n=Count("applications", filter=~Q(applications__status=GA.DRAFT)))[:5],
        "districts": DISTRICTS, "disciplines": Discipline.objects.all(), "f": f, "today": today,
    })


def _counts(rows, labels):
    return sorted([(labels.get(k, k or "Not stated"), c) for k, c in rows], key=lambda x: -x[1])


# ------------------------------------------------------------------ registry admin (FR-3.3, 3.4, 2.6)

@staff_required
def registry(request):
    qs = _apply_registry_filters(_registry_qs(request), request.GET)
    if request.GET.get("export") == "csv":
        return _export_registry(request, qs)
    page = Paginator(qs.order_by("-created_at"), 30).get_page(request.GET.get("page"))
    return render(request, "backoffice/registry.html", {
        "page": page, "f": request.GET, "statuses": Profile.STATUS_CHOICES, "districts": DISTRICTS,
        "disciplines": Discipline.objects.all(), "types": Profile.ACCOUNT_TYPES, "genders": Profile.GENDERS,
        "levels": Profile.EXPERIENCE_LEVELS, "total": qs.count()})


def _export_registry(request, qs):
    audit(request, "registry.export", None, count=qs.count(), filters=dict(request.GET.items()))
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="national-artist-register-{timezone.now():%Y%m%d}.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    w.writerow(["Registration no.", "Status", "Type", "Name", "Organisation", "Org type", "Email", "Phone", "Gender",
                "Date of birth", "Citizenship", "District", "Town", "Primary discipline", "Other disciplines",
                "Experience", "Years", "Public listing", "Registered", "Verified"])
    for p in qs.prefetch_related("disciplines"):
        w.writerow([p.registration_number, p.get_status_display(), p.get_account_type_display(), p.user.get_full_name(),
                    p.org_name, p.get_org_type_display(), p.user.email, p.phone, p.get_gender_display(),
                    p.date_of_birth or "", p.get_citizenship_display(), p.get_district_display(), p.town,
                    p.primary_discipline or "", "; ".join(d.name for d in p.disciplines.all()),
                    p.get_experience_level_display(), p.years_experience or "", "Yes" if p.is_public else "No",
                    timezone.localtime(p.created_at).strftime("%Y-%m-%d"),
                    p.verified_at and timezone.localtime(p.verified_at).strftime("%Y-%m-%d")])
    return resp


@staff_required
def registry_detail(request, pk):
    p = get_object_or_404(_registry_qs(request), pk=pk)
    audit(request, "registry.viewed", p)
    dup = Profile.objects.filter(national_id=p.national_id).exclude(pk=p.pk) if p.national_id else Profile.objects.none()
    return render(request, "backoffice/registry_detail.html", {
        "p": p, "duplicates": dup, "missing": p.missing_fields(), "items": p.portfolio.all(),
        "apps": p.grant_applications.exclude(status=GA.DRAFT), "ends": p.endorsements.all(),
        "history": AuditLog.objects.filter(object_type="accounts.Profile", object_id=str(p.pk))[:15]})


@staff_required
@require_POST
def registry_action(request, pk):
    p = get_object_or_404(_registry_qs(request), pk=pk)
    action, note = request.POST.get("action"), request.POST.get("note", "").strip()
    if action == "verify":
        if p.missing_fields():
            messages.error(request, "Cannot verify: required information is missing: " + ", ".join(p.missing_fields()))
            return redirect("backoffice:registry_detail", pk=pk)
        p.assign_registration_number()
        p.status, p.verified_by, p.verified_at, p.status_note = Profile.VERIFIED, request.user, timezone.now(), ""
        p.save()
        notify(p.user, "You are now on the National Artist Register",
               f"Your registration number is {p.registration_number}. You can now apply for grants and request endorsements.",
               "/dashboard/", sms=True)
    elif action in ("flag", "suspend"):
        if not note:
            messages.error(request, "Please give a reason so the registrant knows what to fix.")
            return redirect("backoffice:registry_detail", pk=pk)
        p.status, p.status_note = (Profile.FLAGGED if action == "flag" else Profile.SUSPENDED), note
        p.save()
        notify(p.user, "Action needed on your registration" if action == "flag" else "Your registration has been suspended",
               note, "/accounts/profile/", sms=True)
    elif action == "reopen":
        p.status = Profile.PENDING
        p.save()
    else:
        messages.error(request, "Unknown action.")
        return redirect("backoffice:registry_detail", pk=pk)
    audit(request, f"registry.{action}", p, note=note)
    messages.success(request, f"Registration updated: {p.get_status_display()}.")
    return redirect("backoffice:registry_detail", pk=pk)


@role_required(User.DISTRICT_OFFICER, User.OFFICER, User.SYSADMIN)
def assisted_registration(request):
    """District officers capture registrations on behalf of walk-in artists (user class: District Officers)."""
    form = SignupForm(request.POST or None, initial={"district": request.user.district})
    form.fields["password1"].required = form.fields["password2"].required = False
    form.fields["password1"].help_text = "Leave blank. The artist will receive a link to set their own password."
    if request.method == "POST":
        data = request.POST.copy()
        temp = secrets.token_urlsafe(12) + "aA1!"
        data["password1"] = data["password2"] = temp
        form = SignupForm(data)
        if form.is_valid():
            user = form.save(assisted_by=request.user)
            audit(request, "registry.assisted_signup", user.profile)
            from django.contrib.auth.forms import PasswordResetForm
            prf = PasswordResetForm({"email": user.email})
            if prf.is_valid():
                prf.save(request=request, use_https=request.is_secure(), from_email=None,
                         email_template_name="emails/password_reset.txt",
                         subject_template_name="emails/password_reset_subject.txt")
            messages.success(request, f"Account created for {user.display_name}. They have been emailed a link to set a password. "
                                      "Complete their profile below.")
            return redirect("backoffice:registry_edit", pk=user.profile.pk)
    return render(request, "backoffice/assisted_registration.html", {"form": form})


@role_required(User.DISTRICT_OFFICER, User.OFFICER, User.SYSADMIN)
def registry_edit(request, pk):
    from accounts.forms import ProfileForm
    p = get_object_or_404(_registry_qs(request), pk=pk)
    form = ProfileForm(request.POST or None, request.FILES or None, instance=p)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "registry.staff_edit", p, fields=form.changed_data)
        if "submit" in request.POST and not p.missing_fields() and p.status == Profile.INCOMPLETE:
            p.status, p.submitted_at = Profile.PENDING, timezone.now()
            p.save(update_fields=["status", "submitted_at"])
        messages.success(request, "Registration saved.")
        return redirect("backoffice:registry_detail", pk=pk)
    return render(request, "backoffice/registry_edit.html", {"form": form, "p": p})


IMPORT_COLUMNS = ["email", "first_name", "last_name", "account_type", "org_name", "phone", "district", "town",
                  "primary_discipline", "gender", "date_of_birth"]


class ImportForm(forms.Form):
    file = forms.FileField(help_text="CSV with header row: " + ", ".join(IMPORT_COLUMNS))
    dry_run = forms.BooleanField(required=False, initial=True, label="Validate only (do not save)")


@role_required(User.OFFICER, User.SYSADMIN)
def registry_import(request):
    """Bulk import with row-level validation (FR-3.4, migration of legacy data)."""
    form = ImportForm(request.POST or None, request.FILES or None)
    report = None
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["file"].read().decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
        disciplines = {d.name.lower(): d for d in Discipline.objects.all()} | {d.slug: d for d in Discipline.objects.all()}
        districts = {v.lower(): k for k, v in DISTRICTS} | {k: k for k, _ in DISTRICTS}
        report = {"ok": 0, "errors": [], "created": 0}
        seen = set()
        with transaction.atomic():
            for i, row in enumerate(rows, start=2):
                errs = []
                email = (row.get("email") or "").strip().lower()
                if not email or "@" not in email:
                    errs.append("invalid email")
                elif email in seen or User.objects.filter(email=email).exists():
                    errs.append("duplicate email")
                seen.add(email)
                district = districts.get((row.get("district") or "").strip().lower())
                if not district:
                    errs.append(f"unknown district '{row.get('district')}'")
                disc = disciplines.get((row.get("primary_discipline") or "").strip().lower())
                if row.get("primary_discipline") and not disc:
                    errs.append(f"unknown discipline '{row.get('primary_discipline')}'")
                atype = (row.get("account_type") or "individual").strip().lower()
                if atype not in ("individual", "organisation"):
                    errs.append("account_type must be individual or organisation")
                if errs:
                    report["errors"].append((i, email, errs))
                    continue
                report["ok"] += 1
                if not form.cleaned_data["dry_run"]:
                    user = User.objects.create_user(
                        email=email, password=None, first_name=row.get("first_name", "").strip(),
                        last_name=row.get("last_name", "").strip(), phone=row.get("phone", "").strip(), district=district,
                        role=User.ORGANISATION if atype == "organisation" else User.ARTIST)
                    user.set_unusable_password()
                    user.save()
                    p = user.profile
                    p.account_type, p.district, p.town, p.phone = atype, district, row.get("town", ""), row.get("phone", "")
                    p.org_name, p.primary_discipline = row.get("org_name", ""), disc
                    p.gender = (row.get("gender") or "").strip().lower() if (row.get("gender") or "").strip().lower() in dict(Profile.GENDERS) else ""
                    try:
                        from datetime import date
                        p.date_of_birth = date.fromisoformat(row["date_of_birth"]) if row.get("date_of_birth") else None
                    except ValueError:
                        p.date_of_birth = None
                    p.save()
                    report["created"] += 1
        audit(request, "registry.import", None, rows=len(rows), created=report["created"], errors=len(report["errors"]),
              dry_run=form.cleaned_data["dry_run"])
        if report["created"]:
            messages.success(request, f"Imported {report['created']} registrations. Imported users set their password via 'Forgot password'.")
    return render(request, "backoffice/registry_import.html", {"form": form, "report": report, "columns": IMPORT_COLUMNS})


@staff_required
def data_quality(request):
    qs = _registry_qs(request)
    dup_ids = (qs.exclude(national_id="").values("national_id").annotate(n=Count("id")).filter(n__gt=1))
    stale = timezone.now() - timedelta(days=30)
    checks = [
        ("Duplicate ID numbers", qs.filter(national_id__in=[d["national_id"] for d in dup_ids])),
        ("Missing phone number", qs.filter(phone="")),
        ("Missing district", qs.filter(district="")),
        ("No primary discipline", qs.filter(primary_discipline=None)),
        ("Pending verification > 10 days", qs.filter(status=Profile.PENDING, submitted_at__lt=timezone.now() - timedelta(days=10))),
        ("Incomplete for > 30 days", qs.filter(status=Profile.INCOMPLETE, created_at__lt=stale)),
        ("Email not verified", qs.filter(user__email_verified=False)),
    ]
    return render(request, "backoffice/data_quality.html", {"checks": [(t, q.count(), q[:10]) for t, q in checks]})


# ------------------------------------------------------------------ reports (FR-9.2)

@staff_required
def reports(request):
    profiles = _registry_qs(request).filter(status=Profile.VERIFIED)
    apps = district_scope(GA.objects.exclude(status=GA.DRAFT), request.user, "profile__district")
    call_id = request.GET.get("call")
    if call_id:
        apps = apps.filter(call_id=call_id)
    today = timezone.localdate()
    ages = {"18 to 24": 0, "25 to 35": 0, "36 to 50": 0, "51+": 0, "Under 18": 0}
    for dob in profiles.exclude(date_of_birth=None).values_list("date_of_birth", flat=True):
        a = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        key = "Under 18" if a < 18 else "18 to 24" if a <= 24 else "25 to 35" if a <= 35 else "36 to 50" if a <= 50 else "51+"
        ages[key] += 1
    sections = {
        "Registered creatives by district": _counts(profiles.values_list("district").annotate(c=Count("id")), DISTRICT_LABELS),
        "Registered creatives by discipline group": _counts(
            profiles.exclude(primary_discipline=None).values_list("primary_discipline__group").annotate(c=Count("id")), dict(Discipline.GROUPS)),
        "Registered creatives by gender": _counts(profiles.values_list("gender").annotate(c=Count("id")), dict(Profile.GENDERS)),
        "Registered creatives by age band (youth: 18 to 35)": [(k, v) for k, v in ages.items() if v],
        "Registered creatives by type": _counts(profiles.values_list("account_type").annotate(c=Count("id")), dict(Profile.ACCOUNT_TYPES)),
        "Grant applications by status": _counts(apps.values_list("status").annotate(c=Count("id")), dict(GA.STATUS)),
        "Grant applications by district": _counts(apps.values_list("profile__district").annotate(c=Count("id")), DISTRICT_LABELS),
        "Grant applications by art form": _counts(apps.exclude(category=None).values_list("category__name").annotate(c=Count("id")), {}),
    }
    sections = {k: (v, max([c for _, c in v] or [1])) for k, v in sections.items()}
    money = apps.aggregate(req=Sum("amount_requested"), awd=Sum("amount_awarded", filter=Q(status=GA.APPROVED)))
    by_call = GrantCall.objects.annotate(
        n=Count("applications", filter=~Q(applications__status=GA.DRAFT)),
        approved=Count("applications", filter=Q(applications__status=GA.APPROVED)),
        awarded=Sum("applications__amount_awarded", filter=Q(applications__status=GA.APPROVED)),
        requested=Sum("applications__amount_requested", filter=~Q(applications__status=GA.DRAFT)))
    event_stats = Event.objects.annotate(
        confirmed=Count("registrations", filter=Q(registrations__status__in=[Registration.CONFIRMED, Registration.ATTENDED])),
        attended=Count("registrations", filter=Q(registrations__status=Registration.ATTENDED)),
        waitlisted=Count("registrations", filter=Q(registrations__status=Registration.WAITLISTED))).order_by("-starts_at")[:10]
    end_stats = _counts(ER.objects.values_list("status").annotate(c=Count("id")), dict(ER.STATUS))
    if request.GET.get("export"):
        return _export_report(request, sections, by_call)
    return render(request, "backoffice/reports.html", {
        "sections": sections, "money": money, "by_call": by_call, "event_stats": event_stats, "end_stats": end_stats,
        "calls": GrantCall.objects.all(), "call_id": call_id})


def _export_report(request, sections, by_call):
    audit(request, "report.export", None)
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="nacb-statistics-{timezone.now():%Y%m%d}.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    for title, (rows, _) in sections.items():
        w.writerow([title])
        for label, c in rows:
            w.writerow([label, c])
        w.writerow([])
    w.writerow(["Grant calls"])
    w.writerow(["Reference", "Title", "Applications", "Approved", "Requested (BWP)", "Awarded (BWP)"])
    for c in by_call:
        w.writerow([c.reference, c.title, c.n, c.approved, c.requested or 0, c.awarded or 0])
    return resp


# ------------------------------------------------------------------ communications (FR-8.3)

class CommunicationForm(forms.Form):
    subject = forms.CharField(max_length=200)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}), label="Message")
    audience = forms.ChoiceField(choices=[("verified", "Verified register members"), ("all", "All creative accounts")])
    account_type = forms.ChoiceField(choices=[("", "Individuals and organisations")] + Profile.ACCOUNT_TYPES, required=False)
    district = forms.ChoiceField(choices=[("", "All districts")] + DISTRICTS, required=False)
    discipline = forms.ModelChoiceField(queryset=Discipline.objects.all(), required=False, empty_label="All disciplines")
    send_email = forms.BooleanField(required=False, initial=True)
    send_sms = forms.BooleanField(required=False, label="Also send SMS (to users who opted in)")
    link = forms.CharField(required=False, help_text="Optional link, e.g. /grants/ or /events/…")


@role_required(User.OFFICER, User.APPROVER, User.SYSADMIN)
def communications(request):
    form = CommunicationForm(request.POST or None)
    preview = None
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        users = User.objects.filter(role__in=User.CREATIVE_ROLES, is_active=True)
        if d["audience"] == "verified":
            users = users.filter(profile__status=Profile.VERIFIED)
        if d["account_type"]:
            users = users.filter(profile__account_type=d["account_type"])
        if d["district"]:
            users = users.filter(profile__district=d["district"])
        if d["discipline"]:
            users = users.filter(Q(profile__primary_discipline=d["discipline"]) | Q(profile__disciplines=d["discipline"]))
        users = users.distinct()
        if "send" in request.POST:
            n = 0
            for u in users:
                notify(u, d["subject"], d["body"], d["link"], email=d["send_email"], sms=d["send_sms"])
                n += 1
            comm = Communication.objects.create(
                sender=request.user, subject=d["subject"], body=d["body"], recipient_count=n,
                channels=",".join(c for c, on in [("inapp", True), ("email", d["send_email"]), ("sms", d["send_sms"])] if on),
                filters={k: str(v) for k, v in d.items() if k in ("audience", "account_type", "district", "discipline") and v})
            audit(request, "communication.sent", comm, recipients=n)
            messages.success(request, f"Message sent to {n} recipient(s).")
            return redirect("backoffice:communications")
        preview = users.count()
    return render(request, "backoffice/communications.html", {
        "form": form, "preview": preview, "history": Communication.objects.select_related("sender")[:15]})


# ------------------------------------------------------------------ support inbox (FR-8.2)

@staff_required
def contact_messages(request):
    qs = ContactMessage.objects.all()
    if request.GET.get("show") != "all":
        qs = qs.filter(resolved=False)
    return render(request, "backoffice/messages.html", {"msgs": qs[:100], "show": request.GET.get("show")})


@staff_required
def contact_message(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    if request.method == "POST":
        response = request.POST.get("response", "").strip()
        if response:
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(f"Re: {msg.subject}", response, settings.DEFAULT_FROM_EMAIL, [msg.email], fail_silently=True)
        msg.response, msg.resolved, msg.handled_by = response, True, request.user
        msg.save()
        audit(request, "contact.resolved", msg)
        messages.success(request, "Message marked as resolved" + (" and reply emailed." if response else "."))
        return redirect("backoffice:messages")
    return render(request, "backoffice/message_detail.html", {"msg": msg})


# ------------------------------------------------------------------ audit & users (FR-9.1, 9.3, 9.4)

@role_required(User.APPROVER, User.SYSADMIN)
def audit_log(request):
    qs = AuditLog.objects.select_related("actor")
    f = request.GET
    if f.get("action"):
        qs = qs.filter(action__startswith=f["action"])
    if f.get("q"):
        qs = qs.filter(Q(object_repr__icontains=f["q"]) | Q(actor__email__icontains=f["q"]))
    if f.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
        w = csv.writer(resp)
        w.writerow(["Time", "Actor", "Action", "Object", "Details", "IP"])
        for a in qs[:20000]:
            w.writerow([timezone.localtime(a.created_at).isoformat(), a.actor or "", a.action, a.object_repr, a.details, a.ip_address])
        return resp
    page = Paginator(qs, 50).get_page(f.get("page"))
    prefixes = ["auth", "account", "registry", "grant", "endorsement", "event", "communication", "contact", "report"]
    return render(request, "backoffice/audit.html", {"page": page, "f": f, "prefixes": prefixes})
