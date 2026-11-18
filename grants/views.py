import csv

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import DISTRICTS, Discipline, Profile
from accounts.views import _serve
from core.permissions import creative_required, district_scope, staff_required
from portal.services import audit, notify

from .forms import (AssignForm, BudgetForm, BudgetFormSet, CommentForm, DecisionForm, DocumentsForm, ImpactForm,
                    InfoResponseForm, ProjectForm, ReviewForm, SubmitForm)
from .models import ApplicationDocument, ApplicationEvent, GrantApplication as GA, GrantCall, Review
from .workflow import TransitionError, transition

STEPS = [(1, "Project"), (2, "Plan & impact"), (3, "Budget"), (4, "Documents"), (5, "Review & submit")]


# ------------------------------------------------------------------ public

def call_list(request):
    calls = GrantCall.objects.filter(status__in=["published", "closed"]).prefetch_related("disciplines")
    now = timezone.now()
    return render(request, "grants/call_list.html", {
        "open_calls": [c for c in calls if c.is_open],
        "upcoming": [c for c in calls if c.status == "published" and c.opens_at > now],
        "closed": [c for c in calls if not c.is_open and not (c.status == "published" and c.opens_at > now)][:10],
    })


def call_detail(request, slug):
    call = get_object_or_404(GrantCall.objects.exclude(status="draft"), slug=slug)
    existing = None
    if request.user.is_authenticated:
        existing = call.applications.filter(applicant=request.user).exclude(status=GA.WITHDRAWN).first()
    return render(request, "grants/call_detail.html", {"call": call, "existing": existing})


# ------------------------------------------------------------------ applicant

@creative_required
@require_POST
def apply(request, slug):
    call = get_object_or_404(GrantCall, slug=slug)
    existing = call.applications.filter(applicant=request.user).exclude(status=GA.WITHDRAWN).first()
    if existing:
        return redirect(existing.get_absolute_url() if not existing.is_editable else _step_url(existing, 1))
    if not call.is_open:
        messages.error(request, "This call is not open for applications.")
        return redirect(call)
    app = GA.objects.create(call=call, applicant=request.user, profile=request.user.profile,
                            district=request.user.profile.district)
    audit(request, "grant.draft_created", app)
    messages.info(request, f"Application {app.reference} started. Your progress is saved at every step, so you can come back later.")
    return redirect(_step_url(app, 1))


def _step_url(app, n):
    from django.urls import reverse
    return reverse("grants:step", args=[app.reference, n])


def _owned(request, ref):
    app = get_object_or_404(GA.objects.select_related("call", "profile"), reference=ref)
    if app.applicant_id != request.user.pk:
        raise PermissionDenied
    return app


@creative_required
def step(request, ref, n):
    app = _owned(request, ref)
    if not app.is_editable:
        messages.info(request, "This application can no longer be edited.")
        return redirect(app)
    if n not in dict(STEPS):
        return redirect(_step_url(app, 1))
    call = app.call
    ctx = {"app": app, "call": call, "steps": STEPS, "n": n, "completion": app.step_completion()}
    post, files = (request.POST, request.FILES) if request.method == "POST" else (None, None)
    nxt = n + 1 if "next" in (post or {}) else n

    if n == 1:
        form = ProjectForm(post, instance=app, call=call)
        if post and form.is_valid():
            form.save()
            return _saved(request, app, nxt)
        ctx["form"] = form
    elif n == 2:
        form = ImpactForm(post, instance=app)
        if post and form.is_valid():
            form.save()
            return _saved(request, app, nxt)
        ctx["form"] = form
    elif n == 3:
        form = BudgetForm(post, instance=app, call=call)
        formset = BudgetFormSet(post, instance=app, prefix="budget")
        if post and form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return _saved(request, app, nxt)
        ctx.update(form=form, formset=formset)
    elif n == 4:
        doc_types = app.required_documents()
        existing = {d.doc_type_id: d for d in app.documents.all()}
        form = DocumentsForm(post, files, doc_types=doc_types, existing=existing)
        if post and form.is_valid():
            from core.validators import validate_document
            from django.core.exceptions import ValidationError
            errors = False
            for dt in doc_types:
                f = form.cleaned_data.get(f"doc_{dt.id}")
                if not f:
                    continue
                try:
                    validate_document(f)
                except ValidationError as e:
                    form.add_error(f"doc_{dt.id}", e)
                    errors = True
                    continue
                doc = existing.get(dt.id) or ApplicationDocument(application=app, doc_type=dt)
                if doc.pk and doc.file:
                    doc.file.delete(save=False)
                doc.file, doc.verified = f, False
                doc.save()
                audit(request, "grant.document_uploaded", app, document=dt.name)
            if not errors:
                return _saved(request, app, nxt)
        ctx["form"] = form
        ctx["doc_rows"] = [(form[f"doc_{dt.id}"], existing.get(dt.id)) for dt in doc_types]
    else:
        form = SubmitForm(post)
        ctx.update(form=form, checks=app.eligibility_checks(), can_submit=app.can_submit())
        if post and form.is_valid():
            if not app.can_submit():
                messages.error(request, "Your application is not complete yet. See the checklist below.")
            else:
                app.declaration = True
                app.save(update_fields=["declaration"])
                resubmit = app.status == GA.INFO_REQUIRED
                try:
                    transition(app, GA.SUBMITTED, request.user, request,
                               note="Resubmitted with additional information" if resubmit else "")
                except TransitionError as e:
                    messages.error(request, str(e))
                    return redirect(app)
                messages.success(request, f"Application {app.reference} submitted. A confirmation has been sent to your email.")
                return redirect(app)
    return render(request, "grants/apply_step.html", ctx)


def _saved(request, app, n):
    app.save(update_fields=["updated_at"])
    messages.success(request, "Progress saved.")
    return redirect(_step_url(app, min(n, 5)))


def application_detail(request, ref):
    if not request.user.is_authenticated:
        return redirect(f"/accounts/login/?next={request.path}")
    app = get_object_or_404(GA.objects.select_related("call", "profile", "category"), reference=ref)
    if request.user.is_nacb_staff and app.applicant_id != request.user.pk:
        return redirect("grants:manage_detail", ref=ref)
    if app.applicant_id != request.user.pk:
        raise PermissionDenied
    form = InfoResponseForm(request.POST or None)
    if app.status == GA.INFO_REQUIRED and request.method == "POST" and form.is_valid():
        ApplicationEvent.objects.create(application=app, actor=request.user, note=form.cleaned_data["response"])
        audit(request, "grant.info_response", app)
        messages.success(request, "Response recorded. Update any sections or documents if needed, then resubmit from the final step.")
        return redirect(_step_url(app, 5))
    return render(request, "grants/application_detail.html", {
        "app": app, "history": app.history.filter(internal=False), "form": form,
        "steps": STEPS, "completion": app.step_completion()})


@creative_required
@require_POST
def withdraw(request, ref):
    app = _owned(request, ref)
    try:
        transition(app, GA.WITHDRAWN, request.user, request, note="Withdrawn by applicant")
        messages.info(request, "Application withdrawn.")
    except TransitionError as e:
        messages.error(request, str(e))
    return redirect("grants:my_applications")


@creative_required
def my_applications(request):
    apps = request.user.grant_applications.select_related("call").order_by("-updated_at")
    return render(request, "grants/my_applications.html", {"apps": apps})


def document(request, pk):
    doc = get_object_or_404(ApplicationDocument.objects.select_related("application"), pk=pk)
    user = request.user
    if not user.is_authenticated or not (user.is_nacb_staff or doc.application.applicant_id == user.pk):
        raise PermissionDenied
    if user.is_nacb_staff:
        audit(request, "grant.document_viewed", doc.application, document=doc.doc_type.name)
    return _serve(doc.file)


# ------------------------------------------------------------------ staff workflow

def _staff_qs(request):
    qs = GA.objects.exclude(status=GA.DRAFT).select_related("call", "profile", "applicant", "category", "assigned_to")
    return district_scope(qs, request.user, "profile__district")


@staff_required
def manage_list(request):
    qs = _staff_qs(request)
    f = request.GET
    if f.get("status"):
        qs = qs.filter(status=f["status"])
    elif not f.get("all"):
        qs = qs.filter(status__in=GA.OPEN_STAFF)
    if f.get("call"):
        qs = qs.filter(call_id=f["call"])
    if f.get("district"):
        qs = qs.filter(profile__district=f["district"])
    if f.get("category"):
        qs = qs.filter(category_id=f["category"])
    if f.get("mine"):
        qs = qs.filter(assigned_to=request.user)
    if f.get("q"):
        q = f["q"]
        qs = qs.filter(Q(reference__icontains=q) | Q(project_title__icontains=q) | Q(profile__org_name__icontains=q)
                       | Q(applicant__first_name__icontains=q) | Q(applicant__last_name__icontains=q))
    qs = qs.order_by("submitted_at")
    if f.get("export") == "csv":
        return export_applications(request, qs)
    page = Paginator(qs, 25).get_page(f.get("page"))
    return render(request, "grants/manage_list.html", {
        "page": page, "calls": GrantCall.objects.all(), "statuses": GA.STATUS, "districts": DISTRICTS,
        "disciplines": Discipline.objects.all(), "f": f,
        "counts": dict(_staff_qs(request).values_list("status").annotate(c=Count("id"))),
    })


def export_applications(request, qs):
    audit(request, "grant.export", None, count=qs.count())
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="grant-applications-{timezone.now():%Y%m%d}.csv"'
    resp.write("﻿")
    w = csv.writer(resp)
    w.writerow(["Reference", "Call", "Applicant", "Registration no.", "Type", "District", "Category", "Project title",
                "Amount requested", "Total cost", "Status", "Avg score %", "Amount awarded", "Submitted", "Decided", "Assigned to"])
    for a in qs:
        w.writerow([a.reference, a.call.reference, a.profile.display_name, a.profile.registration_number,
                    a.profile.get_account_type_display(), a.profile.get_district_display(), a.category or "",
                    a.project_title, a.amount_requested, a.total_project_cost, a.get_status_display(),
                    a.average_score or "", a.amount_awarded or "",
                    a.submitted_at and timezone.localtime(a.submitted_at).strftime("%Y-%m-%d"),
                    a.decided_at and timezone.localtime(a.decided_at).strftime("%Y-%m-%d"), a.assigned_to or ""])
    return resp


def _manage_get(request, ref):
    return get_object_or_404(_staff_qs(request), reference=ref)


@staff_required
def manage_detail(request, ref):
    app = _manage_get(request, ref)
    my_review = app.reviews.filter(reviewer=request.user).first()
    criteria = app.call.criteria.all()
    decision_actions = _allowed_actions(request.user, app)
    decision_form = DecisionForm(initial={"amount_awarded": app.amount_awarded or app.amount_requested})
    decision_form.fields["action"].choices = [c for c in DecisionForm.ACTIONS if c[0] in decision_actions]
    audit(request, "grant.viewed", app)
    return render(request, "grants/manage_detail.html", {
        "app": app, "checks": app.eligibility_checks(), "history": app.history.select_related("actor"),
        "reviews": app.reviews.select_related("reviewer"), "criteria": criteria,
        "assign_form": AssignForm(initial={"assigned_to": app.assigned_to}),
        "review_form": ReviewForm(instance=my_review, criteria=criteria),
        "decision_form": decision_form, "comment_form": CommentForm(),
        "budget_items": app.budget_items.all(), "documents": app.documents.select_related("doc_type", "verified_by"),
        "doc_status": app.document_status(),
    })


def _allowed_actions(user, app):
    from .workflow import TRANSITIONS
    allowed = set(TRANSITIONS.get(app.status, set())) - {GA.SUBMITTED, GA.WITHDRAWN}
    two_level = app.call.approval_levels == 2
    if two_level and not user.can_approve:
        allowed.discard(GA.APPROVED)
        if app.status == GA.RECOMMENDED:
            allowed.discard(GA.REJECTED)
            allowed.discard(GA.UNDER_REVIEW)
    if not two_level:
        allowed.discard(GA.RECOMMENDED)
    return allowed


@staff_required
@require_POST
def manage_assign(request, ref):
    app = _manage_get(request, ref)
    form = AssignForm(request.POST)
    if form.is_valid():
        app.assigned_to = form.cleaned_data["assigned_to"]
        app.save(update_fields=["assigned_to", "updated_at"])
        ApplicationEvent.objects.create(application=app, actor=request.user, internal=True,
                                        note=f"Assigned to {app.assigned_to or 'nobody'}")
        audit(request, "grant.assigned", app, assigned_to=str(app.assigned_to))
        if app.assigned_to and app.assigned_to != request.user:
            notify(app.assigned_to, f"Grant application assigned to you: {app.reference}", app.project_title,
                   f"/grants/manage/{app.reference}/", email=True)
        if app.status == GA.SUBMITTED:
            transition(app, GA.UNDER_REVIEW, request.user, request, note="Review started")
        messages.success(request, "Assignment updated.")
    return redirect("grants:manage_detail", ref=ref)


@staff_required
@require_POST
def manage_review(request, ref):
    app = _manage_get(request, ref)
    instance = app.reviews.filter(reviewer=request.user).first() or Review(application=app, reviewer=request.user)
    form = ReviewForm(request.POST, instance=instance, criteria=app.call.criteria.all())
    if form.is_valid():
        review = form.save()
        ApplicationEvent.objects.create(application=app, actor=request.user, internal=True,
                                        note=f"Evaluation recorded: {review.total}/{review.max_total} to {review.get_recommendation_display()}")
        audit(request, "grant.reviewed", app, total=review.total, recommendation=review.recommendation)
        if app.status == GA.SUBMITTED:
            transition(app, GA.UNDER_REVIEW, request.user, request)
        messages.success(request, "Evaluation saved.")
    else:
        messages.error(request, "Please correct the evaluation form: " + "; ".join(
            f"{k}: {v[0]}" for k, v in form.errors.items()))
    return redirect("grants:manage_detail", ref=ref)


@staff_required
@require_POST
def manage_decide(request, ref):
    app = _manage_get(request, ref)
    form = DecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect("grants:manage_detail", ref=ref)
    action = form.cleaned_data["action"]
    if action not in _allowed_actions(request.user, app):
        raise PermissionDenied
    note = form.cleaned_data["note"]
    if action == GA.INFO_REQUIRED:
        app.info_request = note
    if action == GA.APPROVED:
        app.amount_awarded = form.cleaned_data["amount_awarded"]
    if action in (GA.APPROVED, GA.REJECTED):
        app.decision_note = note
    app.save()
    try:
        transition(app, action, request.user, request, note=note)
        messages.success(request, f"Application moved to: {app.get_status_display()}.")
    except TransitionError as e:
        messages.error(request, str(e))
    return redirect("grants:manage_detail", ref=ref)


@staff_required
@require_POST
def manage_comment(request, ref):
    app = _manage_get(request, ref)
    form = CommentForm(request.POST)
    if form.is_valid():
        ApplicationEvent.objects.create(application=app, actor=request.user, note=form.cleaned_data["note"], internal=True)
        audit(request, "grant.comment", app)
    return redirect("grants:manage_detail", ref=ref)


@staff_required
@require_POST
def manage_verify_doc(request, ref, pk):
    app = _manage_get(request, ref)
    doc = get_object_or_404(app.documents, pk=pk)
    doc.verified = not doc.verified
    doc.verified_by = request.user if doc.verified else None
    doc.save(update_fields=["verified", "verified_by"])
    audit(request, "grant.document_verified" if doc.verified else "grant.document_unverified", app, document=doc.doc_type.name)
    return redirect("grants:manage_detail", ref=ref)
