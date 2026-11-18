from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import DISTRICTS
from core.validators import UploadValidator


class Partner(models.Model):
    """Organisations that support NACB: sponsors, CSR funders, government, development and media partners."""

    TYPES = [("corporate", "Corporate partner"), ("government", "Government partner"), ("development", "Development partner"),
             ("media", "Media partner"), ("education", "Education partner"), ("community", "Community partner")]
    name = models.CharField(max_length=150)
    partner_type = models.CharField(max_length=12, choices=TYPES)
    logo = models.ImageField(upload_to="partners/", blank=True, validators=[UploadValidator(["png", "jpg", "jpeg", "webp"], 2)])
    website = models.URLField(blank=True)
    description = models.TextField(blank=True, help_text="What this partnership supports")
    since = models.PositiveIntegerField("partner since (year)", null=True, blank=True)
    active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False, help_text="Show on the home page")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class SponsorshipPackage(models.Model):
    """What a sponsor receives at a given level, optionally tied to an event."""

    LEVELS = [("headline", "Headline sponsor"), ("gold", "Gold"), ("silver", "Silver"), ("bronze", "Bronze"),
              ("inkind", "In-kind (goods or services)"), ("prize", "Prize sponsor")]
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.CASCADE, related_name="sponsorship_packages",
                              help_text="Leave empty for a general package available across NACB events")
    level = models.CharField(max_length=10, choices=LEVELS)
    amount = models.DecimalField("contribution (BWP)", max_digits=12, decimal_places=2, null=True, blank=True)
    benefits = models.TextField(help_text="One benefit per line")
    slots = models.PositiveIntegerField(default=1)
    slots_taken = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["event", "-amount"]

    def __str__(self):
        return f"{self.get_level_display()}{' for ' + self.event.title if self.event else ''}"

    @property
    def available(self):
        return self.active and self.slots_taken < self.slots

    def benefit_list(self):
        return [b.strip() for b in self.benefits.splitlines() if b.strip()]


class CSRProgramme(models.Model):
    """A fundable programme companies can support through corporate social responsibility (CSR) budgets."""

    THEMES = [("youth", "Youth and skills"), ("schools", "Arts in schools"), ("livelihoods", "Rural livelihoods"),
              ("heritage", "Heritage and culture"), ("digital", "Digital creativity"), ("inclusion", "Disability and inclusion")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    theme = models.CharField(max_length=12, choices=THEMES)
    summary = models.CharField(max_length=300)
    description = models.TextField(help_text="HTML allowed")
    district = models.CharField(max_length=20, choices=DISTRICTS, blank=True, help_text="Leave empty for national programmes")
    target_amount = models.DecimalField("funding needed (BWP)", max_digits=12, decimal_places=2)
    raised_amount = models.DecimalField("funding secured (BWP)", max_digits=12, decimal_places=2, default=Decimal("0"))
    beneficiaries = models.PositiveIntegerField("people who will benefit", null=True, blank=True)
    what_funds_buy = models.TextField("what contributions pay for", blank=True, help_text="One item per line, e.g. P5,000: instruments for one school")
    image = models.ImageField(upload_to="csr/", blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-active", "title"]
        verbose_name = "CSR programme"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("partnerships:programme", args=[self.slug])

    @property
    def percent(self):
        return int(min(100, self.raised_amount * 100 / self.target_amount)) if self.target_amount else 0

    @property
    def remaining(self):
        return max(Decimal("0"), self.target_amount - self.raised_amount)

    def items(self):
        return [b.strip() for b in self.what_funds_buy.splitlines() if b.strip()]


class PartnershipEnquiry(models.Model):
    """A lead from an organisation that wants to sponsor, fund CSR or partner with NACB."""

    INTERESTS = [("event", "Sponsor an event"), ("csr", "Fund a CSR programme"), ("partnership", "Long-term partnership or MoU"),
                 ("inkind", "In-kind support (goods, venues, media, services)"), ("other", "Something else")]
    BUDGETS = [("", "Not sure yet"), ("lt25", "Under P25,000"), ("25-100", "P25,000 to P100,000"),
               ("100-500", "P100,000 to P500,000"), ("gt500", "Over P500,000")]
    STATUS = [("new", "New"), ("contacted", "Contacted"), ("proposal", "Proposal sent"), ("agreed", "Agreed"), ("declined", "Not proceeding")]

    organisation = models.CharField(max_length=200)
    contact_name = models.CharField(max_length=150)
    position = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    interest = models.CharField("how would you like to support?", max_length=12, choices=INTERESTS)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="sponsor_enquiries")
    package = models.ForeignKey(SponsorshipPackage, null=True, blank=True, on_delete=models.SET_NULL)
    programme = models.ForeignKey(CSRProgramme, null=True, blank=True, on_delete=models.SET_NULL, related_name="enquiries")
    budget = models.CharField("indicative budget", max_length=8, choices=BUDGETS, blank=True)
    message = models.TextField("tell us about your goals", blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="new", db_index=True)
    notes = models.TextField("internal notes", blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "partnership enquiries"

    def __str__(self):
        return f"{self.organisation}: {self.get_interest_display()}"

    @property
    def age_days(self):
        return (timezone.now() - self.created_at).days
