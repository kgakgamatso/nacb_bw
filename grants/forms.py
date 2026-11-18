from django import forms
from django.forms import inlineformset_factory

from accounts.models import User

from .models import BudgetItem, GrantApplication, Review


class DateInput(forms.DateInput):
    input_type = "date"


class ProjectForm(forms.ModelForm):
    class Meta:
        model = GrantApplication
        fields = ["project_title", "category", "summary", "description", "objectives", "district", "start_date", "end_date"]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
            "description": forms.Textarea(attrs={"rows": 7}),
            "objectives": forms.Textarea(attrs={"rows": 4}),
            "start_date": DateInput(), "end_date": DateInput(),
        }
        help_texts = {
            "summary": "One or two sentences (max 500 characters) describing the project.",
            "objectives": "List the specific, measurable objectives of the project.",
        }

    def __init__(self, *args, call=None, **kwargs):
        super().__init__(*args, **kwargs)
        if call is not None and call.disciplines.exists():
            self.fields["category"].queryset = call.disciplines.all()

    def clean(self):
        d = super().clean()
        if d.get("start_date") and d.get("end_date") and d["end_date"] < d["start_date"]:
            self.add_error("end_date", "End date must be after the start date.")
        return d


class ImpactForm(forms.ModelForm):
    class Meta:
        model = GrantApplication
        fields = ["timeline", "beneficiaries", "expected_impact", "jobs_created", "partners"]
        widgets = {f: forms.Textarea(attrs={"rows": 4}) for f in ["timeline", "beneficiaries", "expected_impact", "partners"]}
        help_texts = {
            "timeline": "Key activities and milestones with approximate dates.",
            "expected_impact": "How will the project benefit the creative sector, audiences and your career or business?",
        }


class BudgetForm(forms.ModelForm):
    class Meta:
        model = GrantApplication
        fields = ["amount_requested", "total_project_cost", "other_funding"]
        widgets = {"other_funding": forms.Textarea(attrs={"rows": 3})}
        labels = {"amount_requested": "Amount requested from NACB (BWP)", "total_project_cost": "Total project cost (BWP)"}

    def __init__(self, *args, call=None, **kwargs):
        super().__init__(*args, **kwargs)
        if call:
            self.fields["amount_requested"].help_text = f"Between P{call.min_amount:,.0f} and P{call.max_amount:,.0f}."

    def clean(self):
        d = super().clean()
        if d.get("amount_requested") and d.get("total_project_cost") and d["amount_requested"] > d["total_project_cost"]:
            self.add_error("amount_requested", "The amount requested cannot exceed the total project cost.")
        return d


BudgetFormSet = inlineformset_factory(
    GrantApplication, BudgetItem, fields=["category", "description", "quantity", "unit_cost"],
    extra=1, can_delete=True, min_num=0,
)


class DocumentsForm(forms.Form):
    """One upload field per required compliance document, built from the call configuration."""

    def __init__(self, *args, doc_types=(), existing=None, **kwargs):
        super().__init__(*args, **kwargs)
        existing = existing or {}
        for dt in doc_types:
            self.fields[f"doc_{dt.id}"] = forms.FileField(
                label=dt.name, required=False, help_text=dt.description,
                widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"}),
            )
            self.fields[f"doc_{dt.id}"].existing = existing.get(dt.id)


class SubmitForm(forms.Form):
    declaration = forms.BooleanField(
        label="I declare that the information provided is true and correct, that I hold the rights to the work described, "
              "and I understand that false information will lead to disqualification and possible recovery of funds.")


class InfoResponseForm(forms.Form):
    response = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), label="Your response to NACB")


# ------------------------------------------------------------------ staff forms

class AssignForm(forms.Form):
    assigned_to = forms.ModelChoiceField(queryset=User.objects.none(), required=False, label="Assign to officer")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(role__in=User.STAFF_ROLES, is_active=True)


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["recommendation", "recommended_amount", "comments"]
        widgets = {"comments": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, criteria=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.criteria = list(criteria)
        existing = self.instance.scores if self.instance.pk else {}
        for c in self.criteria:
            self.fields[f"score_{c.id}"] = forms.IntegerField(
                label=f"{c.name} (0, {c.max_score})", min_value=0, max_value=c.max_score,
                help_text=c.description, initial=existing.get(str(c.id)))
        order = [f"score_{c.id}" for c in self.criteria] + ["recommendation", "recommended_amount", "comments"]
        self.order_fields(order)

    def save(self, commit=True):
        review = super().save(commit=False)
        review.scores = {str(c.id): self.cleaned_data[f"score_{c.id}"] for c in self.criteria}
        review.total = sum(review.scores.values())
        review.max_total = sum(c.max_score for c in self.criteria)
        if commit:
            review.save()
        return review


class DecisionForm(forms.Form):
    ACTIONS = [
        ("under_review", "Start / return to review"),
        ("info_required", "Request additional information"),
        ("recommended", "Recommend for approval (send to approver)"),
        ("approved", "Approve"),
        ("rejected", "Reject"),
    ]
    action = forms.ChoiceField(choices=ACTIONS)
    amount_awarded = forms.DecimalField(required=False, max_digits=12, decimal_places=2, label="Amount awarded (BWP)")
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False,
                           label="Message to applicant", help_text="Required when requesting information or rejecting.")

    def clean(self):
        d = super().clean()
        if d.get("action") in ("info_required", "rejected") and not d.get("note"):
            self.add_error("note", "Please explain to the applicant.")
        if d.get("action") == "approved" and not d.get("amount_awarded"):
            self.add_error("amount_awarded", "Enter the amount awarded.")
        return d


class CommentForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), label="Internal comment")
