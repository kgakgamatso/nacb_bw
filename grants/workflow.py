"""Grant application state machine, notifications and audit trail (FR-4.4, FR-4.7)."""
from django.urls import reverse
from django.utils import timezone

from portal.services import audit, notify, notify_staff

from .models import ApplicationEvent, GrantApplication as GA

# Allowed transitions: from_status -> set of to_status
TRANSITIONS = {
    GA.DRAFT: {GA.SUBMITTED, GA.WITHDRAWN},
    GA.SUBMITTED: {GA.UNDER_REVIEW, GA.INFO_REQUIRED, GA.REJECTED, GA.WITHDRAWN},
    GA.UNDER_REVIEW: {GA.INFO_REQUIRED, GA.RECOMMENDED, GA.APPROVED, GA.REJECTED, GA.WITHDRAWN},
    GA.INFO_REQUIRED: {GA.SUBMITTED, GA.UNDER_REVIEW, GA.WITHDRAWN, GA.REJECTED},
    GA.RECOMMENDED: {GA.APPROVED, GA.REJECTED, GA.UNDER_REVIEW},
    GA.APPROVED: set(),
    GA.REJECTED: set(),
    GA.WITHDRAWN: set(),
}

APPLICANT_MESSAGES = {
    GA.SUBMITTED: "Your application has been received. You can track its progress on your dashboard.",
    GA.UNDER_REVIEW: "Your application is now being reviewed by an NACB officer.",
    GA.INFO_REQUIRED: "NACB needs more information before continuing the review. Please sign in to respond.",
    GA.APPROVED: "Congratulations! Your grant application has been approved.",
    GA.REJECTED: "Your grant application was not successful in this round. Sign in to view the feedback.",
    GA.WITHDRAWN: "Your application has been withdrawn.",
}


class TransitionError(Exception):
    pass


def transition(app, to_status, actor, request=None, note="", internal=False):
    if to_status not in TRANSITIONS.get(app.status, set()):
        raise TransitionError(f"Cannot move from {app.get_status_display()} to {dict(GA.STATUS)[to_status]}.")
    old = app.status
    app.status = to_status
    now = timezone.now()
    if to_status == GA.SUBMITTED and not app.submitted_at:
        app.submitted_at = now
    if to_status in (GA.APPROVED, GA.REJECTED):
        app.decided_at, app.decided_by = now, actor
    app.save()
    ApplicationEvent.objects.create(application=app, actor=actor, from_status=old, to_status=to_status,
                                    note=note, internal=internal)
    audit(request, f"grant.{to_status}", app, actor=actor, from_status=old, note=note[:200])

    link = reverse("grants:application_detail", args=[app.reference])
    if to_status in APPLICANT_MESSAGES:
        msg = APPLICANT_MESSAGES[to_status]
        if note and not internal and to_status in (GA.INFO_REQUIRED, GA.APPROVED, GA.REJECTED):
            msg += f"\n\nMessage from NACB: {note}"
        notify(app.applicant, f"{app.reference}: {dict(GA.STATUS)[to_status]}", msg, link,
               sms=to_status in (GA.SUBMITTED, GA.INFO_REQUIRED, GA.APPROVED, GA.REJECTED))

    staff_link = reverse("grants:manage_detail", args=[app.reference])
    if to_status == GA.SUBMITTED:
        if app.assigned_to:
            notify(app.assigned_to, f"{app.reference} resubmitted" if old == GA.INFO_REQUIRED else f"{app.reference} submitted",
                   app.project_title, staff_link, email=False)
        else:
            notify_staff("New grant application submitted", f"{app.reference} to {app.project_title}", staff_link)
    elif to_status == GA.RECOMMENDED:
        from accounts.models import User
        notify_staff("Grant recommendation awaiting your decision", f"{app.reference} to {app.project_title}",
                     staff_link, roles=[User.APPROVER])
    return app
