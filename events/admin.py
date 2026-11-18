from django.contrib import admin

from .models import Event, Registration


class RegistrationInline(admin.TabularInline):
    model = Registration
    extra = 0
    raw_id_fields = ["user"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["title", "event_type", "district", "starts_at", "status", "capacity"]
    list_filter = ["status", "event_type", "district"]
    search_fields = ["title", "venue"]
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ["disciplines"]
    inlines = [RegistrationInline]
    date_hierarchy = "starts_at"
