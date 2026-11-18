from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Discipline, PortfolioItem, Profile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "district", "is_active", "mfa_enabled", "last_login"]
    list_filter = ["role", "district", "is_active", "mfa_enabled", "email_verified"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "district", "preferred_language", "sms_opt_in")}),
        ("Role & access", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Security", {"fields": ("email_verified", "mfa_enabled", "last_login", "date_joined")}),
    )
    readonly_fields = ["last_login", "date_joined", "mfa_enabled"]
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "district", "password1", "password2")}),)


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ["name", "group"]
    list_filter = ["group"]
    prepopulated_fields = {"slug": ("name",)}


class PortfolioInline(admin.TabularInline):
    model = PortfolioItem
    extra = 0


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["display_name", "registration_number", "account_type", "status", "district", "primary_discipline", "created_at"]
    list_filter = ["status", "account_type", "district", "primary_discipline", "gender"]
    search_fields = ["registration_number", "org_name", "user__email", "user__first_name", "user__last_name", "stage_name"]
    inlines = [PortfolioInline]
    raw_id_fields = ["user", "verified_by", "assisted_by"]
