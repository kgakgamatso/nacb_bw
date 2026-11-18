from django import forms
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from core.permissions import role_required, staff_required
from events.models import Event
from portal.services import audit, notify_staff

from .models import CSRProgramme, Partner, PartnershipEnquiry, SponsorshipPackage


class EnquiryForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # spam trap

    class Meta:
        model = PartnershipEnquiry
        fields = ["organisation", "contact_name", "position", "email", "phone", "interest", "event", "package", "programme",
                  "budget", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4})}
        labels = {"event": "Event (if sponsoring one)", "package": "Sponsorship package", "programme": "CSR programme"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.filter(status="published", ends_at__gte=timezone.now())
        self.fields["package"].queryset = SponsorshipPackage.objects.filter(active=True).select_related("event")
        self.fields["programme"].queryset = CSRProgramme.objects.filter(active=True)
        for f in ("event", "package", "programme"):
            self.fields[f].required = False


def partner(request):
    initial = {k: request.GET[k] for k in ("interest", "event", "package", "programme") if request.GET.get(k)}
    form = EnquiryForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("website"):
            return redirect("partnerships:partner")
        enq = form.save()
        audit(request, "partnership.enquiry", enq, interest=enq.interest)
        notify_staff("New partnership enquiry", f"{enq.organisation}: {enq.get_interest_display()}",
                     reverse("partnerships:manage_detail", args=[enq.pk]), roles=[User.OFFICER, User.APPROVER])
        messages.success(request, "Thank you. Our partnerships team will contact you within 3 working days.")
        return redirect(reverse("partnerships:partner") + "#enquire")
    now = timezone.now()
    partners = Partner.objects.filter(active=True)
    groups = {}
    for p in partners:
        groups.setdefault(p.get_partner_type_display(), []).append(p)
    events = (Event.objects.filter(status="published", ends_at__gte=now, sponsorship_packages__active=True)
              .distinct().prefetch_related("sponsorship_packages")[:4])
    programmes = CSRProgramme.objects.filter(active=True)
    totals = programmes.aggregate(target=Sum("target_amount"), raised=Sum("raised_amount"))
    return render(request, "partnerships/partner.html", {
        "form": form, "groups": groups, "events": events, "programmes": programmes, "totals": totals,
        "general_packages": SponsorshipPackage.objects.filter(event=None, active=True)})


def programme(request, slug):
    p = get_object_or_404(CSRProgramme, slug=slug, active=True)
    return render(request, "partnerships/programme.html", {"p": p, "others": CSRProgramme.objects.filter(active=True).exclude(pk=p.pk)[:3]})


# ------------------------------------------------------------------ staff

@staff_required
def manage_list(request):
    qs = PartnershipEnquiry.objects.select_related("event", "programme", "handled_by")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    if request.GET.get("q"):
        q = request.GET["q"]
        qs = qs.filter(Q(organisation__icontains=q) | Q(contact_name__icontains=q) | Q(email__icontains=q))
    return render(request, "partnerships/manage_list.html", {
        "enquiries": qs, "statuses": PartnershipEnquiry.STATUS, "status": status,
        "open_count": PartnershipEnquiry.objects.filter(status__in=["new", "contacted", "proposal"]).count()})


@staff_required
def manage_detail(request, pk):
    enq = get_object_or_404(PartnershipEnquiry, pk=pk)
    return render(request, "partnerships/manage_detail.html", {"e": enq, "statuses": PartnershipEnquiry.STATUS})


@role_required(User.OFFICER, User.APPROVER, User.SYSADMIN)
@require_POST
def manage_update(request, pk):
    enq = get_object_or_404(PartnershipEnquiry, pk=pk)
    new = request.POST.get("status")
    if new in dict(PartnershipEnquiry.STATUS):
        enq.status = new
    note = request.POST.get("note", "").strip()
    if note:
        stamp = timezone.localtime().strftime("%d %b %Y %H:%M")
        enq.notes = f"{stamp}, {request.user.get_full_name()}: {note}\n" + enq.notes
    enq.handled_by = enq.handled_by or request.user
    enq.save()
    if new == "agreed" and enq.package_id:
        SponsorshipPackage.objects.filter(pk=enq.package_id).update(slots_taken=enq.package.slots_taken + 1)
    audit(request, f"partnership.{enq.status}", enq)
    messages.success(request, "Enquiry updated.")
    return redirect("partnerships:manage_detail", pk=pk)
