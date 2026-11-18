from django.contrib import admin

from .models import CommitteeDecision, CommitteeSession, GrantAgreement, GrantReport, MonitoringVisit, ApplicationDocument, ApplicationEvent, BudgetItem, DocumentType, GrantApplication, GrantCall, Review, ScoringCriterion


class CriterionInline(admin.TabularInline):
    model = ScoringCriterion
    extra = 1


@admin.register(GrantCall)
class GrantCallAdmin(admin.ModelAdmin):
    """Grant calls are configuration-driven: eligibility, documents, scoring and approval levels (FR-4.1, 4.8, NFR 5.5)."""

    list_display = ["title", "reference", "instrument", "status", "opens_at", "closes_at", "max_amount"]
    list_filter = ["status", "instrument"]
    search_fields = ["title", "reference"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["disciplines", "required_documents"]
    inlines = [CriterionInline]
    fieldsets = (
        (None, {"fields": ("title", "slug", "reference", "instrument", "status", "summary", "description", "guidelines_file")}),
        ("Dates & funding", {"fields": ("opens_at", "closes_at", "min_amount", "max_amount", "total_budget")}),
        ("Eligibility", {"fields": ("eligibility", "applicant_types", "disciplines", "requires_verified_registration",
                                    "citizens_only", "min_age")}),
        ("Compliance & workflow", {"fields": ("required_documents", "approval_levels")}),
    )


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "applies_to"]
    prepopulated_fields = {"code": ("name",)}


class BudgetInline(admin.TabularInline):
    model = BudgetItem
    extra = 0


class DocInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0


class EventInline(admin.TabularInline):
    model = ApplicationEvent
    extra = 0
    readonly_fields = ["actor", "from_status", "to_status", "note", "internal", "created_at"]
    can_delete = False


@admin.register(GrantApplication)
class GrantApplicationAdmin(admin.ModelAdmin):
    list_display = ["reference", "project_title", "call", "applicant", "status", "amount_requested", "submitted_at"]
    list_filter = ["status", "call", "district"]
    search_fields = ["reference", "project_title", "applicant__email"]
    raw_id_fields = ["applicant", "profile", "assigned_to", "decided_by"]
    inlines = [BudgetInline, DocInline, EventInline]


admin.site.register(Review)


for _m in (CommitteeSession, CommitteeDecision, GrantAgreement, GrantReport, MonitoringVisit):
    admin.site.register(_m)
