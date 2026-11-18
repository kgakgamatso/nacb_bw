import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from core.storage import private_storage
from core.validators import validate_document

TURNAROUND_WORKING_DAYS = 10


def add_working_days(start, days):
    d = start
    while days > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d


PURPOSES = [
    ("travel", "Travel / visa for performance or exhibition abroad"),
    ("festival", "Participation in a festival or showcase"),
    ("funding", "Funding or sponsorship application"),
    ("permit", "Venue, filming or event permit"),
    ("competition", "Competition entry"),
    ("residency", "Residency, scholarship or study"),
    ("other", "Other support"),
]


class LetterTemplate(models.Model):
    """Staff-controlled letter template (FR-6.4). Placeholders: {name} {registration_number} {discipline}
    {recipient} {recipient_address} {event} {event_date} {destination} {purpose} {date} {reference}."""

    name = models.CharField(max_length=120)
    purpose = models.CharField(max_length=12, choices=PURPOSES, blank=True, help_text="Default template for this purpose")
    body = models.TextField()
    signatory_name = models.CharField(max_length=120)
    signatory_title = models.CharField(max_length=150, default="Chief Executive Officer")
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def render(self, req):
        p = req.profile
        ctx = {
            "name": p.display_name, "registration_number": p.registration_number or "",
            "discipline": str(p.primary_discipline or ""), "recipient": req.recipient_name,
            "recipient_address": req.recipient_address, "event": req.event_name,
            "event_date": req.event_date.strftime("%d %B %Y") if req.event_date else "",
            "destination": req.destination, "purpose": req.get_purpose_display(),
            "date": timezone.localdate().strftime("%d %B %Y"), "reference": req.reference,
        }
        try:
            return self.body.format(**ctx)
        except (KeyError, IndexError, ValueError):
            return self.body


def endorsement_doc_path(instance, filename):
    return f"endorsements/{instance.reference}/{filename}"


class EndorsementRequest(models.Model):
    SUBMITTED, UNDER_REVIEW, INFO_REQUIRED, APPROVED, ISSUED, REJECTED, WITHDRAWN = (
        "submitted", "under_review", "info_required", "approved", "issued", "rejected", "withdrawn")
    STATUS = [(SUBMITTED, "Submitted"), (UNDER_REVIEW, "Under review"), (INFO_REQUIRED, "Additional information required"),
              (APPROVED, "Approved, letter being prepared"), (ISSUED, "Letter issued"), (REJECTED, "Declined"),
              (WITHDRAWN, "Withdrawn")]
    OPEN = (SUBMITTED, UNDER_REVIEW, INFO_REQUIRED, APPROVED)

    reference = models.CharField(max_length=30, unique=True)
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="endorsements")
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT, related_name="endorsements")
    purpose = models.CharField(max_length=12, choices=PURPOSES)
    recipient_name = models.CharField("letter addressed to (organisation / embassy)", max_length=200)
    recipient_address = models.TextField("recipient address", blank=True)
    event_name = models.CharField("event / programme / opportunity", max_length=200)
    event_date = models.DateField(null=True, blank=True)
    destination = models.CharField("city / country", max_length=120, blank=True)
    justification = models.TextField("why do you need NACB's support?")
    supporting_document = models.FileField(upload_to=endorsement_doc_path, storage=private_storage, blank=True,
                                           validators=[validate_document],
                                           help_text="Invitation letter, acceptance, call for entries etc. (PDF/image, max 5 MB)")
    status = models.CharField(max_length=15, choices=STATUS, default=SUBMITTED, db_index=True)
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_endorsements")
    staff_message = models.TextField(blank=True)
    template = models.ForeignKey(LetterTemplate, null=True, blank=True, on_delete=models.SET_NULL)
    letter_body = models.TextField(blank=True)
    signatory_name = models.CharField(max_length=120, blank=True)
    signatory_title = models.CharField(max_length=150, blank=True)
    verification_code = models.CharField(max_length=12, default="", blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="endorsement_decisions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} to {self.event_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            n = EndorsementRequest.objects.filter(reference__startswith=f"EN-{year}").count() + 1
            self.reference = f"EN-{year}-{n:05d}"
            while EndorsementRequest.objects.filter(reference=self.reference).exists():
                n += 1
                self.reference = f"EN-{year}-{n:05d}"
        if not self.due_date:
            self.due_date = add_working_days(timezone.localdate(), TURNAROUND_WORKING_DAYS)
        if not self.verification_code:
            self.verification_code = secrets.token_hex(4).upper()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("endorsements:detail", args=[self.reference])

    @property
    def is_overdue(self):
        return self.status in self.OPEN and self.due_date and self.due_date < timezone.localdate()

    @property
    def working_days_left(self):
        if not self.due_date:
            return None
        d, n = timezone.localdate(), 0
        while d < self.due_date:
            d += timedelta(days=1)
            if d.weekday() < 5:
                n += 1
        return n


class EndorsementEvent(models.Model):
    request = models.ForeignKey(EndorsementRequest, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    to_status = models.CharField(max_length=15, blank=True)
    note = models.TextField(blank=True)
    internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def to_label(self):
        return dict(EndorsementRequest.STATUS).get(self.to_status, "")
