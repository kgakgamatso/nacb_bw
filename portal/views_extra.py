"""Jobs, tenders and data-protection (privacy rights) views."""
import json

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import DataRequest, Page, Tender, Vacancy
from .services import audit, notify_staff


def vacancies(request):
    qs = Vacancy.objects.published()
    now = timezone.now()
    return render(request, "portal/vacancies.html", {"open": qs.filter(closing_date__gte=now),
                                                     "closed": qs.filter(closing_date__lt=now).order_by("-closing_date")[:10]})


def vacancy_detail(request, slug):
    return render(request, "portal/vacancy_detail.html", {"v": get_object_or_404(Vacancy.objects.published(), slug=slug)})


def tenders(request):
    qs = Tender.objects.published()
    cat = request.GET.get("category")
    if cat:
        qs = qs.filter(category=cat)
    now = timezone.now()
    return render(request, "portal/tenders.html", {"open": qs.filter(closing_date__gte=now),
                                                   "closed": qs.filter(closing_date__lt=now).order_by("-closing_date")[:15],
                                                   "categories": Tender.CATEGORIES, "cat": cat})


def tender_detail(request, slug):
    return render(request, "portal/tender_detail.html", {"t": get_object_or_404(Tender.objects.published(), slug=slug)})


class DataRequestForm(forms.ModelForm):
    class Meta:
        model = DataRequest
        fields = ["name", "email", "request_type", "details"]
        widgets = {"details": forms.Textarea(attrs={"rows": 4})}
        labels = {"request_type": "What would you like to do?", "details": "Details of your request"}


def data_protection(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name(), "email": request.user.email}
    form = DataRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        dr = form.save(commit=False)
        if request.user.is_authenticated:
            dr.user = request.user
        dr.save()
        audit(request, "privacy.request_submitted", dr, type=dr.request_type)
        notify_staff("Data protection request received", f"{dr.get_request_type_display()}, respond by {dr.due_date:%d %b %Y}",
                     "/admin/portal/datarequest/")
        messages.success(request, f"Your request has been received. NACB will respond by {dr.due_date:%d %B %Y}.")
        return redirect("portal:data_protection")
    return render(request, "portal/data_protection.html", {
        "form": form, "page": Page.objects.published().filter(slug="data-protection").first(),
        "my_requests": request.user.data_requests.all() if request.user.is_authenticated else []})


@login_required
def my_data_export(request):
    """Right of access: download everything NACB holds about the signed-in user (machine-readable JSON)."""
    u = request.user
    data = {"exported_at": timezone.now().isoformat(),
            "account": {"email": u.email, "first_name": u.first_name, "last_name": u.last_name, "phone": u.phone,
                        "district": u.district, "role": u.role, "date_joined": u.date_joined.isoformat(),
                        "sms_opt_in": u.sms_opt_in, "mfa_enabled": u.mfa_enabled}}
    p = getattr(u, "profile", None)
    if p:
        fields = ["account_type", "registration_number", "status", "id_type", "national_id", "date_of_birth", "gender",
                  "citizenship", "stage_name", "org_name", "org_type", "org_reg_number", "contact_person", "district", "town",
                  "physical_address", "postal_address", "phone", "alt_phone", "experience_level", "years_experience", "bio",
                  "training", "achievements", "website", "facebook", "instagram", "youtube", "is_public", "show_email",
                  "show_phone", "consent_at"]
        data["register_profile"] = {f: str(getattr(p, f)) if getattr(p, f) is not None else None for f in fields}
        data["register_profile"]["disciplines"] = [d.name for d in p.disciplines.all()]
        data["portfolio"] = [{"title": i.title, "kind": i.kind, "year": i.year, "url": i.url} for i in p.portfolio.all()]
    data["grant_applications"] = [{"reference": a.reference, "call": a.call.title, "project": a.project_title,
                                   "status": a.get_status_display(), "amount_requested": str(a.amount_requested),
                                   "amount_awarded": str(a.amount_awarded)} for a in u.grant_applications.all()]
    data["endorsements"] = [{"reference": e.reference, "event": e.event_name, "status": e.get_status_display()}
                            for e in u.endorsements.all()]
    data["event_registrations"] = [{"event": r.event.title, "status": r.get_status_display()} for r in u.event_registrations.all()]
    data["notifications"] = [{"title": n.title, "date": n.created_at.isoformat()} for n in u.notifications.all()[:500]]
    audit(request, "privacy.data_exported", u)
    resp = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json")
    resp["Content-Disposition"] = 'attachment; filename="my-nacb-data.json"'
    return resp
