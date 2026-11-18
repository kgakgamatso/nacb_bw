from django.contrib import admin

from .models import EndorsementEvent, EndorsementRequest, LetterTemplate


@admin.register(LetterTemplate)
class LetterTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "purpose", "signatory_name", "active"]


class HistoryInline(admin.TabularInline):
    model = EndorsementEvent
    extra = 0
    readonly_fields = ["actor", "to_status", "note", "internal", "created_at"]


@admin.register(EndorsementRequest)
class EndorsementRequestAdmin(admin.ModelAdmin):
    list_display = ["reference", "profile", "purpose", "status", "due_date", "assigned_to"]
    list_filter = ["status", "purpose"]
    search_fields = ["reference", "event_name", "applicant__email"]
    raw_id_fields = ["applicant", "profile", "assigned_to", "decided_by"]
    inlines = [HistoryInline]
