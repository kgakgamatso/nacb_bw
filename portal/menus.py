"""Signed-in menus: built per role, listed alphabetically and numbered in the templates."""
from django.urls import reverse

from accounts.models import User


def account_menu(user):
    """Return [(label, url)] sorted A to Z for the signed-in user."""
    if not user.is_authenticated:
        return []
    items = []
    if user.is_creative:
        items = [
            ("Account and security", reverse("accounts:settings")),
            ("Dashboard", reverse("portal:dashboard")),
            ("Endorsement requests", reverse("endorsements:mine")),
            ("Events", reverse("events:list")),
            ("Grant applications", reverse("grants:my_applications")),
            ("Grant calls", reverse("grants:call_list")),
            ("My data and privacy", reverse("portal:data_protection")),
            ("Notifications", reverse("portal:notifications")),
            ("Portfolio", reverse("accounts:portfolio")),
            ("Public listing settings", reverse("accounts:privacy")),
            ("Register profile", reverse("accounts:profile_edit")),
        ]
        approved = user.grant_applications.filter(status="approved").first()
        if approved:
            items.append(("Grant reporting", reverse("grants:my_grant", args=[approved.reference])))
    elif user.role == User.COMMITTEE:
        items = [
            ("Account and security", reverse("accounts:settings")),
            ("Committee sittings", reverse("grants:committee_list")),
            ("Notifications", reverse("portal:notifications")),
        ]
    elif user.is_nacb_staff:
        items = [
            ("Account and security", reverse("accounts:settings")),
            ("Artist register", reverse("backoffice:registry")),
            ("Committee sittings", reverse("grants:committee_list")),
            ("Dashboard", reverse("backoffice:dashboard")),
            ("Data quality", reverse("backoffice:data_quality")),
            ("Endorsements", reverse("endorsements:manage_list")),
            ("Events and attendance", reverse("events:manage_list")),
            ("Grant applications", reverse("grants:manage_list")),
            ("Grant monitoring", reverse("grants:monitor_list")),
            ("Reports and exports", reverse("backoffice:reports")),
            ("Support inbox", reverse("backoffice:messages")),
            ("Partnership enquiries", reverse("partnerships:manage_list")),
        ]
        if user.role != User.APPROVER:
            items.append(("Walk-in registration", reverse("backoffice:assisted_registration")))
        if user.role in (User.OFFICER, User.SYSADMIN) or user.is_superuser:
            items.append(("Bulk import", reverse("backoffice:registry_import")))
        if user.role != User.DISTRICT_OFFICER:
            items.append(("Communications", reverse("backoffice:communications")))
        if user.can_approve:
            items.append(("Audit log", reverse("backoffice:audit")))
        if user.role == User.SYSADMIN or user.is_superuser:
            items.append(("User management", reverse("backoffice:user_list")))
        if user.is_staff:
            items.append(("Website content (CMS)", "/admin/"))
    return sorted(items, key=lambda i: i[0].lower())
