from django.contrib import admin

from .models import CSRProgramme, Partner, PartnershipEnquiry, SponsorshipPackage


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ["name", "partner_type", "since", "active", "featured", "order"]
    list_filter = ["partner_type", "active", "featured"]
    list_editable = ["active", "featured", "order"]
    search_fields = ["name"]


@admin.register(SponsorshipPackage)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["__str__", "amount", "slots", "slots_taken", "active"]
    list_filter = ["level", "active"]


@admin.register(CSRProgramme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = ["title", "theme", "target_amount", "raised_amount", "active"]
    list_filter = ["theme", "active"]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(PartnershipEnquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ["organisation", "interest", "status", "created_at", "handled_by"]
    list_filter = ["status", "interest"]
    search_fields = ["organisation", "email"]
