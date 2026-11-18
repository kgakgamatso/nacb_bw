from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.storage import private_storage
from core.validators import UploadValidator, validate_document

DISTRICTS = [
    ("gaborone", "Gaborone"),
    ("francistown", "Francistown"),
    ("lobatse", "Lobatse"),
    ("selebi_phikwe", "Selebi-Phikwe"),
    ("jwaneng", "Jwaneng"),
    ("sowa", "Sowa Town"),
    ("central", "Central"),
    ("chobe", "Chobe"),
    ("ghanzi", "Ghanzi"),
    ("kgalagadi", "Kgalagadi"),
    ("kgatleng", "Kgatleng"),
    ("kweneng", "Kweneng"),
    ("north_east", "North-East"),
    ("north_west", "North-West"),
    ("south_east", "South-East"),
    ("southern", "Southern"),
]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.SYSADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    ARTIST = "artist"
    ORGANISATION = "organisation"
    OFFICER = "officer"
    DISTRICT_OFFICER = "district_officer"
    APPROVER = "approver"
    SYSADMIN = "sysadmin"
    COMMITTEE = "committee"
    ROLE_CHOICES = [
        (ARTIST, "Individual Artist"),
        (ORGANISATION, "Organisation"),
        (OFFICER, "NACB Officer"),
        (DISTRICT_OFFICER, "District Officer"),
        (APPROVER, "Approver / Manager"),
        (SYSADMIN, "System Administrator"),
        (COMMITTEE, "Assessment Committee Member"),
    ]
    STAFF_ROLES = (OFFICER, DISTRICT_OFFICER, APPROVER, SYSADMIN)
    CREATIVE_ROLES = (ARTIST, ORGANISATION)

    username = None
    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ARTIST)
    phone = models.CharField(max_length=20, blank=True)
    district = models.CharField(max_length=20, choices=DISTRICTS, blank=True)
    email_verified = models.BooleanField(default=False)
    sms_opt_in = models.BooleanField("Receive SMS notifications", default=True)
    preferred_language = models.CharField(max_length=2, choices=[("en", "English"), ("tn", "Setswana")], default="en")
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=64, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def is_creative(self):
        return self.role in self.CREATIVE_ROLES

    @property
    def is_nacb_staff(self):
        return self.role in self.STAFF_ROLES or self.is_superuser

    @property
    def can_approve(self):
        return self.role in (self.APPROVER, self.SYSADMIN) or self.is_superuser

    @property
    def display_name(self):
        profile = getattr(self, "profile", None)
        if profile and profile.account_type == Profile.ORGANISATION and profile.org_name:
            return profile.org_name
        return self.get_full_name() or self.email


class Discipline(models.Model):
    GROUPS = [
        ("performing", "Performing Arts"),
        ("visual", "Visual Arts"),
        ("literary", "Literary Arts"),
        ("music", "Music"),
        ("film", "Film, Media & Digital"),
        ("craft", "Crafts & Design"),
        ("heritage", "Cultural Heritage"),
    ]
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(unique=True)
    group = models.CharField(max_length=20, choices=GROUPS)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["group", "name"]

    def __str__(self):
        return self.name


def avatar_path(instance, filename):
    return f"avatars/{instance.user_id}/{filename}"


def private_path(instance, filename):
    return f"registry/{instance.user_id}/{filename}"


class Profile(models.Model):
    """National Arts & Creative Industry Register entry (FR-3)."""

    INDIVIDUAL = "individual"
    ORGANISATION = "organisation"
    ACCOUNT_TYPES = [(INDIVIDUAL, "Individual artist / practitioner"), (ORGANISATION, "Organisation / creative enterprise")]

    INCOMPLETE = "incomplete"
    PENDING = "pending"
    VERIFIED = "verified"
    FLAGGED = "flagged"
    SUSPENDED = "suspended"
    STATUS_CHOICES = [
        (INCOMPLETE, "Incomplete"),
        (PENDING, "Pending verification"),
        (VERIFIED, "Verified"),
        (FLAGGED, "Flagged, action required"),
        (SUSPENDED, "Suspended"),
    ]

    ORG_TYPES = [
        ("company", "Company (Pty) Ltd"),
        ("association", "Association"),
        ("society", "Society"),
        ("trust", "Trust"),
        ("cooperative", "Cooperative"),
        ("group", "Informal group / ensemble"),
        ("ngo", "NGO / Non-profit"),
    ]
    EXPERIENCE_LEVELS = [("emerging", "Emerging (0 to 3 years)"), ("developing", "Developing (4 to 9 years)"), ("established", "Established (10+ years)")]
    GENDERS = [("female", "Female"), ("male", "Male"), ("other", "Other"), ("undisclosed", "Prefer not to say")]
    ID_TYPES = [("omang", "Omang (National ID)"), ("passport", "Passport"), ("permit", "Residence permit")]
    CITIZENSHIP = [("citizen", "Citizen of Botswana"), ("resident", "Permanent resident")]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default=INDIVIDUAL)
    registration_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=INCOMPLETE, db_index=True)
    status_note = models.TextField(blank=True, help_text="Reason for flag / suspension (visible to the registrant)")
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_profiles")
    verified_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Individual
    id_type = models.CharField(max_length=10, choices=ID_TYPES, blank=True)
    national_id = models.CharField("ID / passport number", max_length=30, blank=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=12, choices=GENDERS, blank=True)
    citizenship = models.CharField(max_length=10, choices=CITIZENSHIP, blank=True)
    stage_name = models.CharField(max_length=120, blank=True)

    # Organisation
    org_name = models.CharField("organisation name", max_length=200, blank=True)
    org_type = models.CharField("organisation type", max_length=20, choices=ORG_TYPES, blank=True)
    org_reg_number = models.CharField("CIPA / Registrar number", max_length=50, blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    member_count = models.PositiveIntegerField("number of members / employees", null=True, blank=True)
    year_established = models.PositiveIntegerField(null=True, blank=True)

    # Location & contact
    district = models.CharField(max_length=20, choices=DISTRICTS, blank=True, db_index=True)
    town = models.CharField("town / village", max_length=100, blank=True)
    physical_address = models.TextField(blank=True)
    postal_address = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    alt_phone = models.CharField("alternative phone", max_length=20, blank=True)

    # Practice
    primary_discipline = models.ForeignKey(Discipline, null=True, blank=True, on_delete=models.SET_NULL, related_name="primary_profiles")
    disciplines = models.ManyToManyField(Discipline, blank=True, related_name="profiles")
    experience_level = models.CharField(max_length=12, choices=EXPERIENCE_LEVELS, blank=True)
    years_experience = models.PositiveIntegerField(null=True, blank=True)
    bio = models.TextField("biography / description", blank=True)
    training = models.TextField("education & training", blank=True)
    achievements = models.TextField("notable achievements & past projects", blank=True)
    website = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField("YouTube / video channel", blank=True)
    other_link = models.URLField("other portfolio link", blank=True)

    avatar = models.ImageField(upload_to=avatar_path, blank=True, validators=[UploadValidator(["jpg", "jpeg", "png", "webp"], 3)])
    id_document = models.FileField(
        "certified copy of ID / registration certificate", upload_to=private_path, storage=private_storage,
        blank=True, validators=[validate_document],
    )

    # Privacy (FR-3.5)
    is_public = models.BooleanField("list me in the public Artist Directory", default=False)
    show_email = models.BooleanField(default=False)
    show_phone = models.BooleanField(default=False)
    show_bio = models.BooleanField(default=True)
    show_portfolio = models.BooleanField(default=True)
    consent_data_processing = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)

    assisted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="assisted_registrations",
        help_text="District officer who captured this registration on behalf of the registrant",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_name} ({self.registration_number or self.get_status_display()})"

    @property
    def display_name(self):
        if self.account_type == self.ORGANISATION:
            return self.org_name or self.user.email
        return self.stage_name or self.user.get_full_name() or self.user.email

    @property
    def is_verified(self):
        return self.status == self.VERIFIED

    def get_absolute_url(self):
        return reverse("portal:artist_detail", args=[self.pk])

    def required_fields(self):
        common = [
            ("district", "District"), ("town", "Town / village"), ("phone", "Phone number"),
            ("primary_discipline", "Primary discipline"), ("experience_level", "Experience level"),
            ("bio", "Biography / description"), ("id_document", "Identity / registration document"),
        ]
        if self.account_type == self.ORGANISATION:
            return [("org_name", "Organisation name"), ("org_type", "Organisation type"),
                    ("org_reg_number", "Registration number"), ("contact_person", "Contact person")] + common
        return [("id_type", "ID type"), ("national_id", "ID number"), ("date_of_birth", "Date of birth"),
                ("gender", "Gender"), ("citizenship", "Citizenship")] + common

    def missing_fields(self):
        return [label for field, label in self.required_fields() if not getattr(self, field)]

    def completeness(self):
        req = self.required_fields()
        done = len(req) - len(self.missing_fields())
        return int(done * 100 / len(req))

    def assign_registration_number(self):
        if self.registration_number:
            return
        prefix = "ORG" if self.account_type == self.ORGANISATION else "ART"
        year = timezone.now().year
        count = Profile.objects.filter(registration_number__startswith=f"NACB-{prefix}-{year}").count() + 1
        self.registration_number = f"NACB-{prefix}-{year}-{count:05d}"

    @property
    def masked_id(self):
        if not self.national_id:
            return ""
        return "•" * max(0, len(self.national_id) - 3) + self.national_id[-3:]


def portfolio_path(instance, filename):
    return f"portfolio/{instance.profile.user_id}/{filename}"


class PortfolioItem(models.Model):
    KINDS = [
        ("image", "Image / artwork"),
        ("video", "Video (link)"),
        ("audio", "Audio / music"),
        ("document", "Document / publication"),
        ("cv", "CV / company profile"),
        ("link", "Web link / press"),
    ]
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="portfolio")
    title = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=KINDS)
    description = models.TextField(blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    file = models.FileField(upload_to=portfolio_path, storage=private_storage, blank=True,
                            validators=[UploadValidator(["pdf", "jpg", "jpeg", "png", "gif", "webp", "mp3", "mp4", "doc", "docx"], 5)])
    url = models.URLField(blank=True)
    is_public = models.BooleanField(default=True, help_text="CVs are never shown publicly")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_image(self):
        return self.file and self.file.name.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "gif", "webp")

    def publicly_visible(self):
        p = self.profile
        return p.is_public and p.is_verified and p.show_portfolio and self.is_public and self.kind != "cv"
