from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import DISTRICTS, Discipline


class Event(models.Model):
    TYPES = [
        ("festival", "Festival"), ("competition", "Competition"), ("workshop", "Workshop"),
        ("training", "Training / masterclass"), ("exhibition", "Exhibition"), ("performance", "Performance"),
        ("programme", "Programme"), ("meeting", "Stakeholder engagement"),
    ]
    STATUS = [("draft", "Draft"), ("published", "Published"), ("cancelled", "Cancelled")]

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    event_type = models.CharField(max_length=12, choices=TYPES)
    summary = models.CharField(max_length=300)
    description = models.TextField(help_text="HTML allowed")
    image = models.ImageField(upload_to="events/", blank=True)
    disciplines = models.ManyToManyField(Discipline, blank=True)
    district = models.CharField(max_length=20, choices=DISTRICTS)
    venue = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    # Registration (FR-5.2, 5.3)
    registration_required = models.BooleanField(default=True)
    registration_opens = models.DateTimeField(null=True, blank=True)
    registration_closes = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for unlimited")
    waitlist_enabled = models.BooleanField(default=True)
    registered_only = models.BooleanField("only verified register members may register", default=False)
    is_competition = models.BooleanField(default=False, help_text="Ask registrants for an entry title / description")
    related_call = models.ForeignKey("grants.GrantCall", null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    organiser_contact = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:detail", args=[self.slug])

    @property
    def confirmed_count(self):
        return self.registrations.filter(status__in=[Registration.CONFIRMED, Registration.ATTENDED]).count()

    @property
    def waitlist_count(self):
        return self.registrations.filter(status=Registration.WAITLISTED).count()

    @property
    def spaces_left(self):
        if self.capacity is None:
            return None
        return max(0, self.capacity - self.confirmed_count)

    @property
    def is_past(self):
        return self.ends_at < timezone.now()

    @property
    def registration_open(self):
        now = timezone.now()
        if not self.registration_required or self.status != "published" or self.is_past:
            return False
        if self.registration_opens and now < self.registration_opens:
            return False
        if self.registration_closes and now > self.registration_closes:
            return False
        return True

    @property
    def is_full(self):
        return self.spaces_left == 0

    def register(self, user, **extra):
        """Confirm or waitlist atomically, respecting capacity."""
        with transaction.atomic():
            Event.objects.select_for_update().filter(pk=self.pk).first()
            reg, created = Registration.objects.get_or_create(event=self, user=user, defaults=extra)
            if not created and reg.status != Registration.CANCELLED:
                return reg, False
            for k, v in extra.items():
                setattr(reg, k, v)
            if self.is_full:
                if not self.waitlist_enabled:
                    if created:
                        reg.delete()
                    return None, False
                reg.status = Registration.WAITLISTED
            else:
                reg.status = Registration.CONFIRMED
            reg.save()
            return reg, True

    def promote_waitlist(self):
        """Move the earliest waitlisted registrants into freed places. Returns promoted registrations."""
        promoted = []
        with transaction.atomic():
            while not self.is_full:
                nxt = self.registrations.filter(status=Registration.WAITLISTED).order_by("created_at").first()
                if not nxt:
                    break
                nxt.status = Registration.CONFIRMED
                nxt.save(update_fields=["status"])
                promoted.append(nxt)
        return promoted


class Registration(models.Model):
    CONFIRMED, WAITLISTED, CANCELLED, ATTENDED, NO_SHOW = "confirmed", "waitlisted", "cancelled", "attended", "no_show"
    STATUS = [(CONFIRMED, "Confirmed"), (WAITLISTED, "Waitlisted"), (CANCELLED, "Cancelled"),
              (ATTENDED, "Attended"), (NO_SHOW, "Did not attend")]
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_registrations")
    status = models.CharField(max_length=10, choices=STATUS, default=CONFIRMED, db_index=True)
    entry_title = models.CharField("entry / act title", max_length=200, blank=True)
    entry_description = models.TextField("entry description", blank=True)
    group_size = models.PositiveIntegerField("number of people in your group", default=1)
    special_requirements = models.CharField("accessibility or special requirements", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("event", "user")]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user} → {self.event}"
