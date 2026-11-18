from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import DISTRICTS, Discipline, Profile
from core.storage import private_storage
from core.validators import validate_document


class DocumentType(models.Model):
    """Configurable compliance document (certified ID, CV, bank confirmation, quotations…)."""

    APPLIES = [("both", "All applicants"), ("individual", "Individuals only"), ("organisation", "Organisations only")]
    name = models.CharField(max_length=120)
    code = models.SlugField(unique=True)
    description = models.CharField(max_length=300, blank=True)
    applies_to = models.CharField(max_length=12, choices=APPLIES, default="both")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def applies(self, account_type):
        return self.applies_to in ("both", account_type)


class GrantCall(models.Model):
    """An open call for applications under a funding instrument (FR-4.1, FR-4.8)."""

    INSTRUMENTS = [("acg", "Arts and Culture Grant"), ("bcaf", "Botswana Creative Arts Fund"),
                   ("bursary", "Training & Development Bursary"), ("other", "Other funding instrument")]
    STATUS = [("draft", "Draft"), ("published", "Published"), ("closed", "Closed")]
    APPLICANT_TYPES = [("both", "Individuals and organisations"), ("individual", "Individuals only"), ("organisation", "Organisations only")]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    reference = models.CharField(max_length=30, unique=True, help_text="e.g. ACG-2026-02")
    instrument = models.CharField(max_length=10, choices=INSTRUMENTS, default="acg")
    summary = models.CharField(max_length=300)
    description = models.TextField(help_text="HTML allowed")
    eligibility = models.TextField("eligibility criteria", help_text="HTML allowed")
    guidelines_file = models.FileField(upload_to="grant-guidelines/", blank=True)
    disciplines = models.ManyToManyField(Discipline, blank=True, help_text="Leave empty to accept all disciplines")
    applicant_types = models.CharField(max_length=12, choices=APPLICANT_TYPES, default="both")
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    requires_verified_registration = models.BooleanField(default=True)
    citizens_only = models.BooleanField(default=True)
    min_age = models.PositiveIntegerField(default=18)
    required_documents = models.ManyToManyField(DocumentType, blank=True)
    approval_levels = models.PositiveSmallIntegerField(
        default=2, choices=[(1, "Single: officer decides"), (2, "Two-level: officer recommends, approver decides")])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-closes_at"]

    def __str__(self):
        return f"{self.title} ({self.reference})"

    def get_absolute_url(self):
        return reverse("grants:call_detail", args=[self.slug])

    @property
    def is_open(self):
        now = timezone.now()
        return self.status == "published" and self.opens_at <= now <= self.closes_at

    @property
    def phase(self):
        now = timezone.now()
        if self.status != "published":
            return self.get_status_display()
        if now < self.opens_at:
            return "Opening soon"
        if now > self.closes_at:
            return "Closed"
        return "Open"

    @property
    def elapsed_pct(self):
        total = (self.closes_at - self.opens_at).total_seconds()
        done = (timezone.now() - self.opens_at).total_seconds()
        return max(0, min(100, int(done * 100 / total))) if total > 0 else 100

    @property
    def days_left(self):
        return max(0, (self.closes_at - timezone.now()).days)

    def documents_for(self, account_type):
        return [d for d in self.required_documents.all() if d.applies(account_type)]


class ScoringCriterion(models.Model):
    call = models.ForeignKey(GrantCall, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    max_score = models.PositiveIntegerField(default=10)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} (/{self.max_score})"


class GrantApplication(models.Model):
    DRAFT, SUBMITTED, UNDER_REVIEW, INFO_REQUIRED = "draft", "submitted", "under_review", "info_required"
    RECOMMENDED, APPROVED, REJECTED, WITHDRAWN = "recommended", "approved", "rejected", "withdrawn"
    STATUS = [
        (DRAFT, "Draft"), (SUBMITTED, "Submitted"), (UNDER_REVIEW, "Under review"),
        (INFO_REQUIRED, "Additional information required"), (RECOMMENDED, "Recommended, awaiting approval"),
        (APPROVED, "Approved"), (REJECTED, "Not successful"), (WITHDRAWN, "Withdrawn"),
    ]
    EDITABLE = (DRAFT, INFO_REQUIRED)
    OPEN_STAFF = (SUBMITTED, UNDER_REVIEW, INFO_REQUIRED, RECOMMENDED)

    reference = models.CharField(max_length=30, unique=True)
    call = models.ForeignKey(GrantCall, on_delete=models.PROTECT, related_name="applications")
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="grant_applications")
    profile = models.ForeignKey(Profile, on_delete=models.PROTECT, related_name="grant_applications")
    status = models.CharField(max_length=15, choices=STATUS, default=DRAFT, db_index=True)

    # Step 1, project
    project_title = models.CharField(max_length=200, blank=True)
    category = models.ForeignKey(Discipline, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="art form / category")
    summary = models.CharField("project summary", max_length=500, blank=True)
    description = models.TextField("project description", blank=True)
    objectives = models.TextField(blank=True)
    district = models.CharField("where will the project take place?", max_length=20, choices=DISTRICTS, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    # Step 2, plan & impact
    timeline = models.TextField("timeline & milestones", blank=True)
    beneficiaries = models.TextField("target audience / beneficiaries", blank=True)
    expected_impact = models.TextField("expected impact & commercial potential", blank=True)
    jobs_created = models.PositiveIntegerField("jobs / opportunities created", null=True, blank=True)
    partners = models.TextField("partners & collaborators", blank=True)
    # Step 3, budget
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_project_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    other_funding = models.TextField("other funding sources / own contribution", blank=True)
    # Step 5
    declaration = models.BooleanField(default=False)

    # Workflow
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_grants")
    info_request = models.TextField(blank=True)
    amount_awarded = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    decision_note = models.TextField("decision note (shared with applicant)", blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="grant_decisions")
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.reference} to {self.project_title or 'Untitled'}"

    def save(self, *args, **kwargs):
        if not self.reference:
            year = timezone.now().year
            n = GrantApplication.objects.filter(reference__startswith=f"GR-{year}").count() + 1
            self.reference = f"GR-{year}-{n:05d}"
            while GrantApplication.objects.filter(reference=self.reference).exists():
                n += 1
                self.reference = f"GR-{year}-{n:05d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("grants:application_detail", args=[self.reference])

    @property
    def is_editable(self):
        return self.status in self.EDITABLE and (self.call.is_open or self.status == self.INFO_REQUIRED)

    @property
    def budget_total(self):
        return sum((i.total for i in self.budget_items.all()), Decimal("0"))

    @property
    def average_score(self):
        reviews = list(self.reviews.all())
        if not reviews:
            return None
        return round(sum(r.percentage for r in reviews) / len(reviews), 1)

    # ---------------------------------------------------------------- checks (FR-4.3)
    def required_documents(self):
        return self.call.documents_for(self.profile.account_type)

    def document_status(self):
        uploaded = {d.doc_type_id for d in self.documents.all()}
        return [(dt, dt.id in uploaded) for dt in self.required_documents()]

    def step_completion(self):
        return {
            1: all([self.project_title, self.category_id, self.summary, self.description, self.objectives,
                    self.district, self.start_date, self.end_date]),
            2: all([self.timeline, self.beneficiaries, self.expected_impact]),
            3: bool(self.amount_requested and self.total_project_cost and self.budget_items.exists()),
            4: all(ok for _, ok in self.document_status()),
        }

    def eligibility_checks(self):
        call, profile = self.call, self.profile
        checks = []
        checks.append(("Call is open for applications", call.is_open or self.status == self.INFO_REQUIRED,
                       f"Closes {timezone.localtime(call.closes_at):%d %b %Y %H:%M}"))
        if call.requires_verified_registration:
            checks.append(("Verified on the National Artist Register", profile.is_verified,
                           profile.registration_number or profile.get_status_display()))
        types_ok = call.applicant_types in ("both", profile.account_type)
        checks.append(("Applicant type is eligible", types_ok, call.get_applicant_types_display()))
        if call.citizens_only and profile.account_type == Profile.INDIVIDUAL:
            checks.append(("Citizen of Botswana", profile.citizenship == "citizen", profile.get_citizenship_display() or "Not stated"))
        if profile.account_type == Profile.INDIVIDUAL and call.min_age and profile.date_of_birth:
            today = timezone.now().date()
            dob = profile.date_of_birth
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            checks.append((f"Aged {call.min_age} or older", age >= call.min_age, f"{age} years"))
        allowed = list(call.disciplines.all())
        if allowed and self.category_id:
            checks.append(("Art form is covered by this call", self.category in allowed, str(self.category)))
        if self.amount_requested is not None:
            ok = call.min_amount <= self.amount_requested <= call.max_amount
            checks.append(("Amount within funding range", ok, f"P{call.min_amount:,.0f} to P{call.max_amount:,.0f}"))
        if self.amount_requested and self.total_project_cost:
            checks.append(("Requested amount does not exceed project cost",
                           self.amount_requested <= self.total_project_cost, ""))
        if self.start_date and self.end_date:
            checks.append(("Project dates are valid", self.end_date >= self.start_date, ""))
        missing_docs = [dt.name for dt, ok in self.document_status() if not ok]
        checks.append(("All compliance documents uploaded", not missing_docs,
                       ("Missing: " + ", ".join(missing_docs)) if missing_docs else "Complete"))
        dup = GrantApplication.objects.filter(call=call, applicant=self.applicant).exclude(pk=self.pk).exclude(
            status__in=[self.DRAFT, self.WITHDRAWN]).exists()
        checks.append(("One application per applicant per call", not dup, ""))
        return checks

    def can_submit(self):
        steps = self.step_completion()
        return all(steps.values()) and all(ok for _, ok, _ in self.eligibility_checks())

    def completeness(self):
        steps = self.step_completion()
        return int(sum(steps.values()) * 100 / len(steps))


class BudgetItem(models.Model):
    CATEGORIES = [("personnel", "Personnel / artist fees"), ("materials", "Materials & equipment"),
                  ("venue", "Venue & logistics"), ("travel", "Travel & accommodation"),
                  ("marketing", "Marketing & publicity"), ("production", "Production"), ("other", "Other")]
    application = models.ForeignKey(GrantApplication, on_delete=models.CASCADE, related_name="budget_items")
    category = models.CharField(max_length=12, choices=CATEGORIES)
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def total(self):
        return (self.quantity or 0) * (self.unit_cost or 0)


def application_doc_path(instance, filename):
    return f"grants/{instance.application.reference}/{filename}"


class ApplicationDocument(models.Model):
    application = models.ForeignKey(GrantApplication, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    file = models.FileField(upload_to=application_doc_path, storage=private_storage, validators=[validate_document])
    uploaded_at = models.DateTimeField(auto_now=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = [("application", "doc_type")]

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]


class Review(models.Model):
    """Officer / panel evaluation with configurable scoring (FR-4.5)."""

    RECOMMEND = [("approve", "Recommend approval"), ("reject", "Recommend rejection"), ("more_info", "Needs more information")]
    application = models.ForeignKey(GrantApplication, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scores = models.JSONField(default=dict)
    total = models.PositiveIntegerField(default=0)
    max_total = models.PositiveIntegerField(default=0)
    recommendation = models.CharField(max_length=10, choices=RECOMMEND)
    recommended_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    comments = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("application", "reviewer")]

    @property
    def percentage(self):
        return round(self.total * 100 / self.max_total, 1) if self.max_total else 0


class ApplicationEvent(models.Model):
    """Status history, comments and audit trail per application (FR-4.7)."""

    application = models.ForeignKey(GrantApplication, on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    from_status = models.CharField(max_length=15, blank=True)
    to_status = models.CharField(max_length=15, blank=True)
    note = models.TextField(blank=True)
    internal = models.BooleanField(default=False, help_text="Internal notes are hidden from the applicant")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def to_label(self):
        return dict(GrantApplication.STATUS).get(self.to_status, "")


# ====================================================================== Committee assessment (after call closes)

class CommitteeSession(models.Model):
    """Assessment committee sitting for a grant call. Held only after the closing date: the committee scores
    every eligible application, records a decision per application, produces a summary report and publishes results."""

    SCHEDULED, IN_PROGRESS, CONCLUDED, PUBLISHED = "scheduled", "in_progress", "concluded", "published"
    STATUS = [(SCHEDULED, "Scheduled"), (IN_PROGRESS, "Assessment in progress"),
              (CONCLUDED, "Decisions recorded"), (PUBLISHED, "Results published")]

    call = models.ForeignKey(GrantCall, on_delete=models.PROTECT, related_name="committee_sessions")
    title = models.CharField(max_length=200)
    meeting_date = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    chair = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="chaired_sessions")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="committee_sessions",
                                     help_text="Committee members who score applications (staff or external panellists)")
    secretary = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=12, choices=STATUS, default=SCHEDULED)
    budget_available = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    minutes = models.TextField("minutes / resolutions", blank=True)
    conflicts_declared = models.TextField("declarations of interest", blank=True)
    concluded_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-meeting_date"]

    def __str__(self):
        return f"{self.title} ({self.call.reference})"

    def get_absolute_url(self):
        return reverse("grants:committee_detail", args=[self.pk])

    @property
    def call_closed(self):
        return timezone.now() >= self.call.closes_at

    def is_member(self, user):
        return user.is_superuser or user.pk == self.chair_id or self.members.filter(pk=user.pk).exists()

    def applications(self):
        return self.call.applications.exclude(status__in=[GrantApplication.DRAFT, GrantApplication.WITHDRAWN])

    def totals(self):
        decided = self.decisions.all()
        approved = [d for d in decided if d.decision == CommitteeDecision.APPROVE]
        return {
            "applications": self.applications().count(),
            "decided": decided.exclude(decision=CommitteeDecision.PENDING).count(),
            "approved": len(approved),
            "rejected": decided.filter(decision=CommitteeDecision.REJECT).count(),
            "deferred": decided.filter(decision=CommitteeDecision.DEFER).count(),
            "amount": sum((d.amount or Decimal("0")) for d in approved),
        }


class CommitteeDecision(models.Model):
    PENDING, APPROVE, REJECT, DEFER = "pending", "approve", "reject", "defer"
    CHOICES = [(PENDING, "Not yet decided"), (APPROVE, "Fund"), (REJECT, "Do not fund"), (DEFER, "Defer / more information")]
    session = models.ForeignKey(CommitteeSession, on_delete=models.CASCADE, related_name="decisions")
    application = models.OneToOneField(GrantApplication, on_delete=models.CASCADE, related_name="committee_decision")
    decision = models.CharField(max_length=8, choices=CHOICES, default=PENDING)
    amount = models.DecimalField("amount approved (BWP)", max_digits=12, decimal_places=2, null=True, blank=True)
    conditions = models.TextField("conditions of award", blank=True)
    reason = models.TextField("reason / feedback to applicant", blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rank", "application__reference"]


# ====================================================================== Grant monitoring & grantee reporting

class GrantAgreement(models.Model):
    """Created when an award is published. Drives continuous reporting and monitoring."""

    FREQUENCY = [("monthly", "Monthly"), ("quarterly", "Quarterly"), ("milestone", "At each milestone")]
    HEALTH = [("on_track", "On track"), ("at_risk", "At risk"), ("off_track", "Off track / default"), ("completed", "Completed & closed")]
    FREQ_DAYS = {"monthly": 30, "quarterly": 91, "milestone": 60}
    application = models.OneToOneField(GrantApplication, on_delete=models.CASCADE, related_name="agreement")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    conditions = models.TextField(blank=True)
    frequency = models.CharField("reporting frequency", max_length=10, choices=FREQUENCY, default="quarterly")
    signed_at = models.DateField("agreement signed", null=True, blank=True)
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    next_report_due = models.DateField(null=True, blank=True)
    health = models.CharField("monitoring status", max_length=10, choices=HEALTH, default="on_track")
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="monitored_grants")
    closed_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Agreement {self.application.reference}"

    @property
    def is_overdue(self):
        return self.health != "completed" and self.next_report_due and self.next_report_due < timezone.localdate()

    def advance_due_date(self):
        from datetime import timedelta
        base = max(self.next_report_due or timezone.localdate(), timezone.localdate())
        self.next_report_due = base + timedelta(days=self.FREQ_DAYS[self.frequency])


def report_path(instance, filename):
    return f"grant-reports/{instance.agreement.application.reference}/{filename}"


class GrantReport(models.Model):
    TYPES = [("progress", "Progress report"), ("financial", "Financial report"), ("final", "Final / close-out report")]
    SUBMITTED, ACCEPTED, REVISION = "submitted", "accepted", "revision"
    STATUS = [(SUBMITTED, "Submitted, under review"), (ACCEPTED, "Accepted"), (REVISION, "Revision requested")]
    agreement = models.ForeignKey(GrantAgreement, on_delete=models.CASCADE, related_name="reports")
    report_type = models.CharField(max_length=10, choices=TYPES, default="progress")
    period = models.CharField("reporting period", max_length=60, help_text="e.g. Jan to Mar 2027")
    progress = models.TextField("activities completed and progress against objectives")
    challenges = models.TextField("challenges and how you are addressing them", blank=True)
    beneficiaries_reached = models.PositiveIntegerField(null=True, blank=True)
    jobs_created = models.PositiveIntegerField(null=True, blank=True)
    spent_to_date = models.DecimalField("grant funds spent to date (BWP)", max_digits=12, decimal_places=2, null=True, blank=True)
    percent_complete = models.PositiveIntegerField("project % complete", default=0)
    attachment = models.FileField("evidence (receipts, photos or PDF, max 5 MB)", upload_to=report_path,
                                  storage=private_storage, blank=True, validators=[validate_document])
    status = models.CharField(max_length=10, choices=STATUS, default=SUBMITTED)
    feedback = models.TextField("NACB feedback", blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]


class MonitoringVisit(models.Model):
    agreement = models.ForeignKey(GrantAgreement, on_delete=models.CASCADE, related_name="visits")
    visit_date = models.DateField()
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    findings = models.TextField()
    health = models.CharField(max_length=10, choices=GrantAgreement.HEALTH)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visit_date"]
