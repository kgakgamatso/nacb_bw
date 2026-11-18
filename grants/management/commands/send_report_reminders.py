"""Daily job (Windows Task Scheduler / cron): remind grantees of reports due within 7 days and flag overdue grants.
    python manage.py send_report_reminders"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from grants.models import GrantAgreement
from portal.services import notify


class Command(BaseCommand):
    help = "Send grant report reminders and mark overdue grants at risk"

    def handle(self, *args, **opts):
        today = timezone.localdate()
        active = GrantAgreement.objects.exclude(health="completed").select_related("application", "application__applicant", "officer")
        due_soon = overdue = 0
        for ag in active.filter(next_report_due__gte=today, next_report_due__lte=today + timedelta(days=7)):
            notify(ag.application.applicant, f"Grant report due {ag.next_report_due:%d %b %Y}",
                   f"Please submit your {ag.get_frequency_display().lower()} report for {ag.application.reference}.",
                   reverse("grants:my_grant", args=[ag.application.reference]), sms=True)
            due_soon += 1
        for ag in active.filter(next_report_due__lt=today):
            notify(ag.application.applicant, f"Overdue grant report: {ag.application.reference}",
                   "Your report is overdue. Continued funding depends on timely reporting.",
                   reverse("grants:my_grant", args=[ag.application.reference]), sms=True)
            if ag.health == "on_track":
                ag.health = "at_risk"
                ag.save(update_fields=["health"])
            if ag.officer:
                notify(ag.officer, f"Overdue grantee report: {ag.application.reference}", "",
                       reverse("grants:monitor_detail", args=[ag.application.reference]), email=False)
            overdue += 1
        self.stdout.write(self.style.SUCCESS(f"Reminders sent: {due_soon} due soon, {overdue} overdue."))
