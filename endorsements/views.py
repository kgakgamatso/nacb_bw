from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.views import _serve
from core.permissions import creative_required, district_scope, staff_required
from portal.services import audit, notify, notify_staff

from .models import EndorsementEvent, EndorsementRequest as ER, LetterTemplate


class RequestForm(forms.ModelForm):
    class Meta:
        model = ER
        fields = ["purpose", "recipient_name", "recipient_address", "event_name", "event_date", "destination",
                  "justification", "supporting_document"]
        widgets = {"event_date": forms.DateInput(attrs={"type": "date"}),
                   "recipient_address": forms.Textarea(attrs={"rows": 2}),
                   "justification": forms.Textarea(attrs={"rows": 5})}


class StaffActionForm(forms.Form):
    ACTIONS = [("under_review", "Start review"), ("info_required", "Request more information"),
               ("approved", "Approve & prepare letter"), ("rejected", "Decline")]
    action = forms.ChoiceField(choices=ACTIONS)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False, label="Message to applicant")
    assigned_to = forms.ModelChoiceField(queryset=User.objects.filter(role__in=User.STAFF_ROLES), required=False)

    def clean(self):
        d = super().clean()
        if d.get("action") in ("info_required", "rejected") and not d.get("message"):
            self.add_error("message", "Please explain to the applicant.")
        return d


class LetterForm(forms.ModelForm):
    class Meta:
        model = ER
        fields = ["template", "letter_body", "signatory_name", "signatory_title"]
        widgets = {"letter_body": forms.Textarea(attrs={"rows": 14})}


def _log(req, actor, status, note="", internal=False, request=None):
    EndorsementEvent.objects.create(request=req, actor=actor, to_status=status, note=note, internal=internal)
    audit(request, f"endorsement.{status or 'comment'}", req, actor=actor)


# ------------------------------------------------------------------ applicant

def info(request):
    return render(request, "endorsements/info.html")


@creative_required
def create(request):
    profile = request.user.profile
    if not profile.is_verified:
        messages.warning(request, "Endorsement requests are available to verified members of the National Artist Register. "
                                  "Complete and submit your registration first.")
        return redirect("endorsements:info")
    form = RequestForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        req = form.save(commit=False)
        req.applicant, req.profile = request.user, profile
        req.save()
        _log(req, request.user, ER.SUBMITTED, request=request)
        notify(request.user, f"Endorsement request {req.reference} received",
               f"Target turnaround: by {req.due_date:%d %B %Y} (10 working days).", req.get_absolute_url(), sms=True)
        notify_staff("New endorsement request", f"{req.reference} to {profile.display_name}",
                     reverse("endorsements:manage_detail", args=[req.reference]), district=profile.district)
        messages.success(request, f"Request {req.reference} submitted. Expected response by {req.due_date:%d %B %Y}.")
        return redirect(req)
    return render(request, "endorsements/form.html", {"form": form})


@creative_required
def mine(request):
    return render(request, "endorsements/mine.html", {"reqs": request.user.endorsements.all()})


def detail(request, ref):
    if not request.user.is_authenticated:
        return redirect(f"/accounts/login/?next={request.path}")
    req = get_object_or_404(ER, reference=ref)
    if req.applicant_id != request.user.pk:
        if request.user.is_nacb_staff:
            return redirect("endorsements:manage_detail", ref=ref)
        raise PermissionDenied
    form = None
    if req.status == ER.INFO_REQUIRED:
        form = RequestForm(request.POST or None, request.FILES or None, instance=req)
        if request.method == "POST" and form.is_valid():
            form.save()
            req.status = ER.SUBMITTED
            req.save(update_fields=["status"])
            _log(req, request.user, ER.SUBMITTED, "Updated with additional information", request=request)
            if req.assigned_to:
                notify(req.assigned_to, f"{req.reference} updated by applicant", "",
                       reverse("endorsements:manage_detail", args=[ref]), email=False)
            messages.success(request, "Request updated and resubmitted.")
            return redirect(req)
    return render(request, "endorsements/detail.html", {"req": req, "form": form, "history": req.history.filter(internal=False)})


def letter(request, ref):
    req = get_object_or_404(ER, reference=ref, status=ER.ISSUED)
    user = request.user
    if not user.is_authenticated or not (user.is_nacb_staff or req.applicant_id == user.pk):
        raise PermissionDenied
    verify_url = request.build_absolute_uri(reverse("endorsements:verify") + f"?ref={req.reference}&code={req.verification_code}")
    return render(request, "endorsements/letter.html", {"req": req, "verify_url": verify_url})


def verify(request):
    """Public letter authenticity check (anti-fraud)."""
    ref, code = request.GET.get("ref", "").strip(), request.GET.get("code", "").strip().upper()
    result = None
    if ref and code:
        result = ER.objects.filter(reference=ref, verification_code=code, status=ER.ISSUED).select_related("profile").first() or False
    return render(request, "endorsements/verify.html", {"result": result, "ref": ref, "code": code})


def document(request, ref):
    req = get_object_or_404(ER, reference=ref)
    if not request.user.is_authenticated or not (request.user.is_nacb_staff or req.applicant_id == request.user.pk):
        raise PermissionDenied
    return _serve(req.supporting_document)


# ------------------------------------------------------------------ staff

@staff_required
def manage_list(request):
    qs = district_scope(ER.objects.select_related("profile", "applicant", "assigned_to"), request.user, "profile__district")
    status = request.GET.get("status")
    qs = qs.filter(status=status) if status else qs.filter(status__in=ER.OPEN)
    if request.GET.get("q"):
        q = request.GET["q"]
        qs = qs.filter(Q(reference__icontains=q) | Q(event_name__icontains=q) | Q(profile__org_name__icontains=q)
                       | Q(applicant__last_name__icontains=q))
    return render(request, "endorsements/manage_list.html", {"reqs": qs.order_by("due_date"), "statuses": ER.STATUS,
                                                             "status": status, "today": timezone.localdate()})


@staff_required
def manage_detail(request, ref):
    req = get_object_or_404(district_scope(ER.objects.all(), request.user, "profile__district"), reference=ref)
    action_form = StaffActionForm(initial={"assigned_to": req.assigned_to})
    letter_form = None
    if req.status in (ER.APPROVED, ER.ISSUED):
        if not req.letter_body:
            tpl = LetterTemplate.objects.filter(active=True, purpose=req.purpose).first() or LetterTemplate.objects.filter(active=True).first()
            if tpl:
                req.template, req.letter_body = tpl, tpl.render(req)
                req.signatory_name, req.signatory_title = tpl.signatory_name, tpl.signatory_title
        letter_form = LetterForm(instance=req)
    return render(request, "endorsements/manage_detail.html", {
        "req": req, "action_form": action_form, "letter_form": letter_form,
        "history": req.history.select_related("actor"), "templates": LetterTemplate.objects.filter(active=True)})


@staff_required
@require_POST
def manage_action(request, ref):
    req = get_object_or_404(district_scope(ER.objects.all(), request.user, "profile__district"), reference=ref)
    form = StaffActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect("endorsements:manage_detail", ref=ref)
    if req.status in (ER.ISSUED, ER.REJECTED, ER.WITHDRAWN):
        messages.error(request, "This request is already closed.")
        return redirect("endorsements:manage_detail", ref=ref)
    action, msg = form.cleaned_data["action"], form.cleaned_data["message"]
    req.assigned_to = form.cleaned_data["assigned_to"] or req.assigned_to or request.user
    req.status, req.staff_message = action, msg or req.staff_message
    if action in (ER.APPROVED, ER.REJECTED):
        req.decided_by = request.user
    req.save()
    _log(req, request.user, action, msg, request=request)
    titles = {ER.UNDER_REVIEW: "is being reviewed", ER.INFO_REQUIRED: "needs more information",
              ER.APPROVED: "has been approved", ER.REJECTED: "was declined"}
    notify(req.applicant, f"Endorsement {req.reference} {titles[action]}", msg, req.get_absolute_url(),
           sms=action != ER.UNDER_REVIEW)
    messages.success(request, f"Request updated: {req.get_status_display()}.")
    return redirect("endorsements:manage_detail", ref=ref)


@staff_required
@require_POST
def manage_letter(request, ref):
    req = get_object_or_404(district_scope(ER.objects.all(), request.user, "profile__district"),
                            reference=ref, status__in=[ER.APPROVED, ER.ISSUED])
    if "regenerate" in request.POST:
        tpl = get_object_or_404(LetterTemplate, pk=request.POST.get("template"))
        req.template, req.letter_body = tpl, tpl.render(req)
        req.signatory_name, req.signatory_title = tpl.signatory_name, tpl.signatory_title
        req.save()
        messages.info(request, "Letter regenerated from template.")
        return redirect("endorsements:manage_detail", ref=ref)
    form = LetterForm(request.POST, instance=req)
    if form.is_valid():
        req = form.save()
        if "issue" in request.POST and req.status != ER.ISSUED:
            req.status, req.issued_at = ER.ISSUED, timezone.now()
            req.save(update_fields=["status", "issued_at"])
            _log(req, request.user, ER.ISSUED, request=request)
            notify(req.applicant, f"Your endorsement letter {req.reference} is ready",
                   "Sign in to view, print or download your letter.", reverse("endorsements:letter", args=[ref]), sms=True)
            messages.success(request, "Letter issued to the applicant.")
        else:
            audit(request, "endorsement.letter_saved", req)
            messages.success(request, "Letter saved.")
    return redirect("endorsements:manage_detail", ref=ref)
