import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.validators import UploadValidator


class PublishQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status="published", publish_at__lte=timezone.now())


class Publishable(models.Model):
    """Draft → (scheduled) published → archived lifecycle for CMS content (FR-1.2)."""

    STATUS = [("draft", "Draft"), ("published", "Published"), ("archived", "Archived")]
    status = models.CharField(max_length=10, choices=STATUS, default="draft", db_index=True)
    publish_at = models.DateTimeField(default=timezone.now, help_text="Set a future date to schedule publication")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublishQuerySet.as_manager()

    class Meta:
        abstract = True

    @property
    def is_live(self):
        return self.status == "published" and self.publish_at <= timezone.now()


class Page(Publishable):
    """Free-form CMS page, e.g. About, Mandate, The Act, Services, Privacy."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    title_tn = models.CharField("title (Setswana)", max_length=200, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(help_text="HTML allowed (trusted staff only)")
    body_tn = models.TextField("body (Setswana)", blank=True)
    show_in_footer = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("portal:page", args=[self.slug])


class NewsPost(Publishable):
    CATEGORIES = [("news", "News"), ("press", "Press release"), ("announcement", "Announcement"),
                  ("opportunity", "Opportunity"), ("feature", "Artist feature")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    category = models.CharField(max_length=15, choices=CATEGORIES, default="news")
    summary = models.CharField(max_length=300)
    body = models.TextField(help_text="HTML allowed (trusted staff only)")
    image = models.ImageField(upload_to="news/", blank=True)
    video_url = models.URLField("embedded video (YouTube) URL", blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    related_event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="news")
    related_call = models.ForeignKey("grants.GrantCall", null=True, blank=True, on_delete=models.SET_NULL, related_name="news")
    featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["-publish_at"]
        verbose_name = "news article"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("portal:news_detail", args=[self.slug])

    @property
    def embed_url(self):
        url = self.video_url
        if "youtube.com/watch?v=" in url:
            return "https://www.youtube-nocookie.com/embed/" + url.split("v=")[1].split("&")[0]
        if "youtu.be/" in url:
            return "https://www.youtube-nocookie.com/embed/" + url.rsplit("/", 1)[1]
        return ""


class Resource(Publishable):
    CATEGORIES = [("guidelines", "Guidelines"), ("forms", "Forms & templates"), ("reports", "Annual reports"),
                  ("policy", "Policy & legislation"), ("publications", "Publications & research")]
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=15, choices=CATEGORIES)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="resources/", blank=True, validators=[UploadValidator(max_mb=5)])
    external_url = models.URLField(blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    downloads = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["category", "-year", "title"]

    def __str__(self):
        return self.title


class GalleryAlbum(Publishable):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="albums")

    class Meta:
        ordering = ["-publish_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("portal:album", args=[self.slug])

    @property
    def cover(self):
        return self.images.first()


class GalleryImage(models.Model):
    album = models.ForeignKey(GalleryAlbum, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=200, blank=True)
    credit = models.CharField("photo credit", max_length=120, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]


class FAQ(models.Model):
    CATEGORIES = [("general", "General"), ("registration", "Registration"), ("grants", "Grants & funding"),
                  ("events", "Events & programmes"), ("endorsements", "Endorsements"), ("account", "Account & security")]
    question = models.CharField(max_length=300)
    answer = models.TextField()
    category = models.CharField(max_length=15, choices=CATEGORIES, default="general")
    order = models.PositiveIntegerField(default=0)
    published = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "order"]
        verbose_name = "FAQ"

    def __str__(self):
        return self.question


class LeadershipMember(models.Model):
    GROUPS = [("board", "Board of Directors"), ("management", "Executive Management")]
    name = models.CharField(max_length=120)
    position = models.CharField(max_length=150)
    group = models.CharField(max_length=12, choices=GROUPS)
    photo = models.ImageField(upload_to="leadership/", blank=True)
    bio = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["group", "order"]

    def __str__(self):
        return f"{self.name} to {self.position}"


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120, blank=True)
    interests = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)
    token = models.CharField(max_length=40, default=secrets.token_urlsafe, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class ContactMessage(models.Model):
    CATEGORIES = [("general", "General enquiry"), ("registration", "Registration support"), ("grants", "Grants"),
                  ("events", "Events & programmes"), ("endorsements", "Endorsements"), ("feedback", "Website feedback"),
                  ("complaint", "Complaint")]
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    category = models.CharField(max_length=15, choices=CATEGORIES, default="general")
    subject = models.CharField(max_length=200)
    message = models.TextField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="handled_messages")
    response = models.TextField(blank=True)

    class Meta:
        ordering = ["resolved", "-created_at"]

    def __str__(self):
        return f"{self.subject} to {self.name}"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    emailed = models.BooleanField(default=False)
    sms_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    """Immutable record of user actions and system changes (FR-9.3)."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60, db_index=True)
    object_type = models.CharField(max_length=60, blank=True, db_index=True)
    object_id = models.CharField(max_length=40, blank=True)
    object_repr = models.CharField(max_length=250, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor} {self.action} {self.object_repr}"


class Communication(models.Model):
    """Targeted bulk message to registered users (FR-8.3)."""

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    filters = models.JSONField(default=dict, blank=True)
    channels = models.CharField(max_length=40, default="inapp,email")
    recipient_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject


class Vacancy(Publishable):
    """NACB job vacancies (careers)."""

    TYPES = [("permanent", "Permanent"), ("contract", "Fixed-term contract"), ("internship", "Internship / attachment"),
             ("consultancy", "Consultancy"), ("volunteer", "Volunteer")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    reference = models.CharField(max_length=40)
    department = models.CharField(max_length=120)
    location = models.CharField(max_length=120, default="Gaborone")
    employment_type = models.CharField(max_length=12, choices=TYPES, default="permanent")
    grade = models.CharField("grade / salary scale", max_length=60, blank=True)
    summary = models.CharField(max_length=300)
    description = models.TextField("duties & responsibilities", help_text="HTML allowed")
    requirements = models.TextField("qualifications & experience", help_text="HTML allowed")
    how_to_apply = models.TextField(default="Send a cover letter, CV and certified copies of certificates to recruitment@nacb.org.bw quoting the reference number.")
    closing_date = models.DateTimeField()
    document = models.FileField("job profile (PDF, max 5 MB)", upload_to="vacancies/", blank=True, validators=[UploadValidator(["pdf"], 5)])

    class Meta:
        ordering = ["closing_date"]
        verbose_name_plural = "vacancies"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("portal:vacancy_detail", args=[self.slug])

    @property
    def is_open(self):
        return self.closing_date >= timezone.now()


class Tender(Publishable):
    """Procurement notices: tenders, quotations, expressions of interest, awards."""

    CATEGORIES = [("goods", "Goods"), ("services", "Services"), ("works", "Works"), ("consultancy", "Consultancy"),
                  ("eoi", "Expression of interest")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    reference = models.CharField("tender number", max_length=40)
    category = models.CharField(max_length=12, choices=CATEGORIES)
    summary = models.CharField(max_length=300)
    description = models.TextField(help_text="HTML allowed")
    eligibility = models.TextField("eligibility & compulsory requirements", blank=True, help_text="HTML allowed")
    briefing = models.CharField("pre-bid meeting / site visit", max_length=200, blank=True)
    closing_date = models.DateTimeField()
    submission = models.TextField("how to submit", default="Sealed bids to be deposited in the tender box at NACB Head Office before the closing date and time.")
    document = models.FileField("tender document (PDF, max 5 MB)", upload_to="tenders/", blank=True, validators=[UploadValidator(["pdf"], 5)])
    contact = models.CharField(max_length=200, default="procurement@nacb.org.bw")
    award_notice = models.TextField("award notice (published after evaluation)", blank=True)

    class Meta:
        ordering = ["closing_date"]

    def __str__(self):
        return f"{self.reference} to {self.title}"

    def get_absolute_url(self):
        return reverse("portal:tender_detail", args=[self.slug])

    @property
    def is_open(self):
        return self.closing_date >= timezone.now()


class DataRequest(models.Model):
    """Data-subject rights requests under the Botswana Data Protection Act (access, correction, deletion, objection)."""

    TYPES = [("access", "Access: a copy of my data"), ("correction", "Correction of my data"),
             ("deletion", "Deletion / closing my account"), ("objection", "Object to or restrict processing"),
             ("withdraw", "Withdraw consent")]
    STATUS = [("open", "Received"), ("in_progress", "In progress"), ("completed", "Completed"), ("declined", "Declined (with reason)")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="data_requests")
    name = models.CharField(max_length=150)
    email = models.EmailField()
    request_type = models.CharField(max_length=12, choices=TYPES)
    details = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS, default="open")
    response = models.TextField(blank=True)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.due_date:
            from datetime import timedelta
            self.due_date = timezone.localdate() + timedelta(days=30)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_request_type_display()} to {self.email}"
