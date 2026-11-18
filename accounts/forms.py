from django import forms
from django.contrib.auth import password_validation
from django.utils import timezone

from .models import DISTRICTS, Discipline, PortfolioItem, Profile, User


class DateInput(forms.DateInput):
    input_type = "date"


class SignupForm(forms.Form):
    account_type = forms.ChoiceField(
        choices=Profile.ACCOUNT_TYPES, widget=forms.RadioSelect, initial=Profile.INDIVIDUAL,
        label="I am registering as",
    )
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Surname")
    org_name = forms.CharField(max_length=200, required=False, label="Organisation name",
                               help_text="Required for organisations. Your own name above is recorded as the contact person.")
    email = forms.EmailField(help_text="We will send a verification link to this address.")
    phone = forms.CharField(max_length=20, label="Mobile number", help_text="For example +267 71 234 567. Used for SMS updates.")
    district = forms.ChoiceField(choices=[("", "Select district")] + DISTRICTS)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text=password_validation.password_validators_help_text_html())
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    sms_opt_in = forms.BooleanField(required=False, initial=True, label="Send me SMS notifications about my applications")
    consent = forms.BooleanField(
        label="I consent to NACB processing my personal information for the National Artist Register and related services, "
              "in line with the Botswana Data Protection Act.",
    )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in or resetting your password.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("account_type") == Profile.ORGANISATION and not data.get("org_name"):
            self.add_error("org_name", "Please enter your organisation's name.")
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords do not match.")
        if p1:
            tmp = User(email=data.get("email", ""), first_name=data.get("first_name", ""), last_name=data.get("last_name", ""))
            try:
                password_validation.validate_password(p1, tmp)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return data

    def save(self, assisted_by=None):
        d = self.cleaned_data
        is_org = d["account_type"] == Profile.ORGANISATION
        user = User.objects.create_user(
            email=d["email"], password=d["password1"], first_name=d["first_name"], last_name=d["last_name"],
            phone=d["phone"], district=d["district"], sms_opt_in=d.get("sms_opt_in", False),
            role=User.ORGANISATION if is_org else User.ARTIST,
        )
        profile = user.profile
        profile.account_type = d["account_type"]
        profile.phone = d["phone"]
        profile.district = d["district"]
        profile.consent_data_processing = True
        profile.consent_at = timezone.now()
        profile.assisted_by = assisted_by
        if is_org:
            profile.org_name = d["org_name"]
            profile.contact_person = f"{d['first_name']} {d['last_name']}"
        profile.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class MFACodeForm(forms.Form):
    code = forms.CharField(max_length=8, label="6-digit code",
                           widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True}))


class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "sms_opt_in", "preferred_language"]


INDIVIDUAL_FIELDS = ["stage_name", "id_type", "national_id", "date_of_birth", "gender", "citizenship"]
ORG_FIELDS = ["org_name", "org_type", "org_reg_number", "contact_person", "member_count", "year_established"]
COMMON_FIELDS = [
    "district", "town", "physical_address", "postal_address", "phone", "alt_phone",
    "primary_discipline", "disciplines", "experience_level", "years_experience",
    "bio", "training", "achievements", "website", "facebook", "instagram", "youtube", "other_link",
    "avatar", "id_document",
]


class ProfileForm(forms.ModelForm):
    """Register profile; fields adapt to individual vs organisation (FR-2.2, FR-3.1)."""

    SECTIONS = [
        ("Identity", INDIVIDUAL_FIELDS + ORG_FIELDS),
        ("Location & contact", ["district", "town", "physical_address", "postal_address", "phone", "alt_phone"]),
        ("Creative practice", ["primary_discipline", "disciplines", "experience_level", "years_experience", "bio", "training", "achievements"]),
        ("Online presence", ["website", "facebook", "instagram", "youtube", "other_link"]),
        ("Documents & photo", ["avatar", "id_document"]),
    ]

    class Meta:
        model = Profile
        fields = INDIVIDUAL_FIELDS + ORG_FIELDS + COMMON_FIELDS
        widgets = {
            "date_of_birth": DateInput(),
            "disciplines": forms.CheckboxSelectMultiple,
            "physical_address": forms.Textarea(attrs={"rows": 2}),
            "bio": forms.Textarea(attrs={"rows": 5}),
            "training": forms.Textarea(attrs={"rows": 3}),
            "achievements": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "national_id": "Kept confidential and used only for verification.",
            "disciplines": "Select all disciplines you practise.",
            "id_document": "PDF or image, max 5 MB. Individuals: certified Omang/passport. Organisations: registration certificate.",
            "stage_name": "Optional. The name you perform or publish under.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        drop = ORG_FIELDS if self.instance.account_type == Profile.INDIVIDUAL else INDIVIDUAL_FIELDS
        for f in drop:
            self.fields.pop(f, None)
        self.fields["primary_discipline"].queryset = Discipline.objects.all()
        self.fields["disciplines"].queryset = Discipline.objects.all()
        for name, _ in self.instance.required_fields():
            if name in self.fields:
                self.fields[name].widget.attrs["data-required-for-verification"] = "1"

    def sections(self):
        for title, names in self.SECTIONS:
            fields = [self[n] for n in names if n in self.fields]
            if fields:
                yield title, fields

    def clean_national_id(self):
        nid = self.cleaned_data.get("national_id", "").strip().upper()
        if nid and self.cleaned_data.get("id_type") == "omang" and not (nid.isdigit() and len(nid) == 9):
            raise forms.ValidationError("An Omang number has 9 digits.")
        if nid and Profile.objects.filter(national_id=nid).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This ID number is already registered. Please contact NACB if you believe this is an error.")
        return nid

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob and dob > timezone.now().date():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return dob


class PrivacyForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["is_public", "show_bio", "show_portfolio", "show_email", "show_phone"]
        labels = {
            "show_bio": "Show my biography",
            "show_portfolio": "Show my public portfolio items",
            "show_email": "Show my email address",
            "show_phone": "Show my phone number",
        }


class PortfolioForm(forms.ModelForm):
    class Meta:
        model = PortfolioItem
        fields = ["title", "kind", "year", "description", "file", "url", "is_public"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        labels = {"url": "Link (YouTube, SoundCloud, website…)", "is_public": "Show on my public profile"}

    def clean(self):
        data = super().clean()
        if not data.get("file") and not data.get("url"):
            raise forms.ValidationError("Upload a file or provide a link.")
        return data
