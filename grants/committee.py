"""Assessment committee, results publication and grant monitoring.

Flow: call closes -> committee session sits -> members score each application -> a decision is recorded per
application -> session concluded with minutes -> summary report produced -> results published (winners and
unsuccessful applicants alerted by email/SMS/in-app) -> grant agreements created -> grantees report continuously
and officers monitor (reports, visits, health status, reminders)."""
import csv
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from core.permissions import role_required, staff_required
from portal.services import audit, notify

from .forms import ReviewForm
from .models import (CommitteeDecision, CommitteeSession, GrantAgreement, GrantApplication as GA, GrantCall,
                     GrantReport, MonitoringVisit, Review)
from .workflow import transition

MANAGERS = (User.OFFICER, User.APPROVER, User.SYSADMIN)


# ------------------------------------------------------------------ forms

class SessionForm(forms.ModelForm):
    class Meta:
        model = CommitteeSession
        fields = ["call", "title", "meeting_date", "venue", "chair", "secretary", "members", "budget_available"]
        widgets = {"meeting_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "members": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        people = User.objects.filter(is_active=True, role__in=User.STAFF_ROLES + (User.COMMITTEE,)).order_by("first_name")
        for f in ("chair", "secretary", "members"):
            self.fields[f].queryset = people
        self.fields["call"].queryset = GrantCall.objects.exclude(status="draft")
        self.fields["meeting_date"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        d = super().clean()
        call, when = d.get("call"), d.get("meeting_date")
        if call and when and when < call.closes_at:
            self.add_error("meeting_date", f"The committee can only sit after the call closes ({timezone.localtime(call.closes_at):%d %b %Y %H:%M}).")
        return d


class DecisionRowForm(forms.ModelForm):
    class Meta:
        model = CommitteeDecision
        fields = ["decision", "amount", "rank", "conditions", "reason"]
        widgets = {"conditions": forms.Textarea(attrs={"rows": 2}), "reason": forms.Textarea(attrs={"rows": 2})}

    def clean(self):
        d = super().clean()
        app = self.instance.application
        if d.get("decision") == CommitteeDecision.APPROVE:
            amt = d.get("amount")
            if not amt:
                self.add_error("amount", "Enter the amount approved.")
            elif amt > app.call.max_amount:
                self.add_error("amount", f"Exceeds the call maximum of P{app.call.max_amount:,.0f}.")
        if d.get("decision") in (CommitteeDecision.REJECT, CommitteeDecision.DEFER) and not d.get("reason"):
            self.add_error("reason", "Give the applicant a reason.")
        return d


class MinutesForm(forms.ModelForm):
    class Meta:
        model = CommitteeSession
        fields = ["minutes", "conflicts_declared"]
        widgets = {"minutes": forms.Textarea(attrs={"rows": 6}), "conflicts_declared": forms.Textarea(attrs={"rows": 3})}


class ReportForm(forms.ModelForm):
    class Meta:
        model = GrantReport
        fields = ["report_type", "period", "percent_complete", "progress", "challenges", "beneficiaries_reached",
                  "jobs_created", "spent_to_date", "attachment"]
        widgets = {"progress": forms.Textarea(attrs={"rows": 5}), "challenges": forms.Textarea(attrs={"rows": 3}),
                   "percent_complete": forms.NumberInput(attrs={"min": 0, "max": 100})}

    def clean_percent_complete(self):
        v = self.cleaned_data["percent_complete"]
        if not 0 <= v <= 100:
            raise forms.ValidationError("Enter a value between 0 and 100.")
        return v


class AgreementForm(forms.ModelForm):
    class Meta:
        model = GrantAgreement
        fields = ["health", "frequency", "next_report_due", "signed_at", "disbursed_amount", "officer", "conditions"]
        widgets = {"next_report_due": forms.DateInput(attrs={"type": "date"}), "signed_at": forms.DateInput(attrs={"type": "date"}),
                   "conditions": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["officer"].queryset = User.objects.filter(role__in=User.STAFF_ROLES, is_active=True)


class VisitForm(forms.ModelForm):
    class Meta:
        model = MonitoringVisit
        fields = ["visit_date", "health", "findings"]
        widgets = {"visit_date": forms.DateInput(attrs={"type": "date"}), "findings": forms.Textarea(attrs={"rows": 3})}


# ------------------------------------------------------------------ helpers

def _session_for(request, pk):
    s = get_object_or_404(CommitteeSession.objects.select_related("call", "chair"), pk=pk)
    u = request.user
    if not (u.is_authenticated and (s.is_member(u) or u.role in MANAGERS or u.is_superuser)):
        raise PermissionDenied
    return s


def _can_manage(user, session):
    return user.is_superuser or user.role in (User.APPROVER, User.SYSADMIN) or user.pk in (session.chair_id, session.secretary_id)


def _scores(session):
    member_ids = list(session.members.values_list("pk", flat=True)) + [session.chair_id]
    rows = {}
    for app in session.applications().select_related("profile", "category"):
        reviews = app.reviews.filter(reviewer_id__in=member_ids)
        pct = [r.percentage for r in reviews]
        rows[app.pk] = {"app": app, "count": len(pct), "avg": round(sum(pct) / len(pct), 1) if pct else None,
                        "reviews": list(reviews.select_related("reviewer"))}
    return rows


# ------------------------------------------------------------------ committee sessions

@login_required
def committee_list(request):
    u = request.user
    if u.role in MANAGERS or u.is_superuser:
        sessions = CommitteeSession.objects.select_related("call", "chair")
    else:
        sessions = CommitteeSession.objects.filter(Q(members=u) | Q(chair=u)).distinct()
        if not sessions.exists() and u.role != User.COMMITTEE:
            raise PermissionDenied
    awaiting = [c for c in GrantCall.objects.filter(status__in=["published", "closed"], closes_at__lte=timezone.now())
                if not c.committee_sessions.exists()]
    return render(request, "grants/committee_list.html", {"sessions": sessions, "awaiting": awaiting})


@role_required(*MANAGERS)
def committee_create(request):
    form = SessionForm(request.POST or None, initial={"call": request.GET.get("call"), "chair": request.user})
    if request.method == "POST" and form.is_valid():
        s = form.save()
        for app in s.applications():
            CommitteeDecision.objects.get_or_create(application=app, defaults={"session": s})
        audit(request, "committee.scheduled", s)
        for m in set(list(s.members.all()) + [s.chair]):
            notify(m, f"Committee sitting: {s.title}", f"{timezone.localtime(s.meeting_date):%d %b %Y %H:%M} at {s.venue}. "
                   f"{s.applications().count()} applications to assess.", s.get_absolute_url())
        messages.success(request, "Committee sitting scheduled and members notified.")
        return redirect(s)
    return render(request, "grants/committee_form.html", {"form": form})


@login_required
def committee_detail(request, pk):
    s = _session_for(request, pk)
    manage = _can_manage(request.user, s)
    for app in s.applications():  # late submissions/resubmissions are picked up
        CommitteeDecision.objects.get_or_create(application=app, defaults={"session": s})
    scores = _scores(s)
    decisions = list(s.decisions.select_related("application", "application__profile", "application__category"))
    rows = []
    for d in decisions:
        sc = scores.get(d.application_id, {})
        form = DecisionRowForm(instance=d, prefix=f"d{d.pk}") if manage else None
        mine = Review.objects.filter(application=d.application, reviewer=request.user).first()
        rows.append({"d": d, "score": sc, "form": form, "mine": mine})
    rows.sort(key=lambda r: (-(r["score"].get("avg") or -1)))
    return render(request, "grants/committee_detail.html", {
        "s": s, "rows": rows, "manage": manage, "totals": s.totals(), "minutes_form": MinutesForm(instance=s),
        "members": s.members.all(), "editable": s.status in (s.SCHEDULED, s.IN_PROGRESS)})


@login_required
@require_POST
def committee_start(request, pk):
    s = _session_for(request, pk)
    if not _can_manage(request.user, s):
        raise PermissionDenied
    if not s.call_closed:
        messages.error(request, "Assessment can only start after the call has closed.")
    else:
        s.status = s.IN_PROGRESS
        s.save(update_fields=["status"])
        audit(request, "committee.started", s)
        messages.success(request, "Assessment started. Members can now score applications.")
    return redirect(s)


@login_required
@require_POST
def committee_decisions(request, pk):
    s = _session_for(request, pk)
    if not _can_manage(request.user, s) or s.status not in (s.SCHEDULED, s.IN_PROGRESS):
        raise PermissionDenied
    errors = 0
    with transaction.atomic():
        for d in s.decisions.select_related("application", "application__call"):
            f = DecisionRowForm(request.POST, instance=d, prefix=f"d{d.pk}")
            if f.is_valid():
                obj = f.save(commit=False)
                obj.recorded_by = request.user
                obj.save()
            else:
                errors += 1
                messages.error(request, f"{d.application.reference}: " + "; ".join(e for es in f.errors.values() for e in es))
    audit(request, "committee.decisions_saved", s, errors=errors)
    if not errors:
        messages.success(request, "Decisions saved.")
    return redirect(s)


@login_required
@require_POST
def committee_conclude(request, pk):
    s = _session_for(request, pk)
    if not _can_manage(request.user, s):
        raise PermissionDenied
    form = MinutesForm(request.POST, instance=s)
    if form.is_valid():
        form.save()
    if "conclude" in request.POST:
        pending = s.decisions.filter(decision=CommitteeDecision.PENDING).count()
        if pending:
            messages.error(request, f"{pending} application(s) still have no decision.")
            return redirect(s)
        t = s.totals()
        if s.budget_available and t["amount"] > s.budget_available:
            messages.error(request, f"Approved total P{t['amount']:,.0f} exceeds the available budget P{s.budget_available:,.0f}.")
            return redirect(s)
        s.status, s.concluded_at = s.CONCLUDED, timezone.now()
        s.save()
        audit(request, "committee.concluded", s, **{k: str(v) for k, v in t.items()})
        messages.success(request, "Sitting concluded. Review the summary report, then publish results.")
    else:
        messages.success(request, "Minutes saved.")
    return redirect(s)


@login_required
def committee_report(request, pk):
    s = _session_for(request, pk)
    scores = _scores(s)
    decisions = s.decisions.select_related("application", "application__profile", "application__category")
    order = {CommitteeDecision.APPROVE: 0, CommitteeDecision.DEFER: 1, CommitteeDecision.REJECT: 2, CommitteeDecision.PENDING: 3}
    rows = sorted([(d, scores.get(d.application_id, {})) for d in decisions],
                  key=lambda r: (order[r[0].decision], r[0].rank or 999, -(r[1].get("avg") or 0)))
    by_district, by_form = {}, {}
    for d, _ in rows:
        if d.decision == CommitteeDecision.APPROVE:
            k = d.application.profile.get_district_display() or "Not stated"
            by_district[k] = by_district.get(k, Decimal("0")) + (d.amount or 0)
            f = str(d.application.category or "Other")
            by_form[f] = by_form.get(f, Decimal("0")) + (d.amount or 0)
    if request.GET.get("format") == "csv":
        audit(request, "committee.report_exported", s)
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="committee-summary-{s.call.reference}.csv"'
        resp.write("﻿")
        w = csv.writer(resp)
        w.writerow(["Rank", "Reference", "Applicant", "District", "Art form", "Project", "Requested", "Avg score %",
                    "Assessors", "Decision", "Amount approved", "Conditions / reason"])
        for d, sc in rows:
            a = d.application
            w.writerow([d.rank or "", a.reference, a.profile.display_name, a.profile.get_district_display(), a.category or "",
                        a.project_title, a.amount_requested, sc.get("avg") or "", sc.get("count", 0), d.get_decision_display(),
                        d.amount or "", d.conditions or d.reason])
        return resp
    return render(request, "grants/committee_report.html", {
        "s": s, "rows": rows, "totals": s.totals(), "members": s.members.all(),
        "by_district": sorted(by_district.items()), "by_form": sorted(by_form.items()), "now": timezone.now()})


@login_required
@require_POST
def committee_publish(request, pk):
    """Publish results: winners and unsuccessful applicants are alerted; agreements open for monitoring."""
    s = _session_for(request, pk)
    if not (request.user.is_superuser or request.user.role in (User.APPROVER, User.SYSADMIN) or request.user.pk == s.chair_id):
        raise PermissionDenied
    if s.status != s.CONCLUDED:
        messages.error(request, "Conclude the sitting before publishing results.")
        return redirect(s)
    counts = {"approved": 0, "rejected": 0, "deferred": 0}
    with transaction.atomic():
        for d in s.decisions.select_related("application", "application__call"):
            app = d.application
            if app.status in (GA.APPROVED, GA.REJECTED, GA.WITHDRAWN):
                continue
            if app.status in (GA.SUBMITTED, GA.INFO_REQUIRED) and d.decision != CommitteeDecision.DEFER:
                transition(app, GA.UNDER_REVIEW, request.user, request, note="Assessed by committee", internal=True)
            if d.decision == CommitteeDecision.APPROVE:
                app.amount_awarded, app.decision_note = d.amount, d.conditions
                app.save()
                transition(app, GA.APPROVED, request.user, request,
                           note=f"Approved by the {s.title}. Amount: P{d.amount:,.2f}." + (f" Conditions: {d.conditions}" if d.conditions else ""))
                ag, _ = GrantAgreement.objects.get_or_create(application=app, defaults={
                    "amount": d.amount, "conditions": d.conditions, "officer": app.assigned_to})
                if not ag.next_report_due:
                    ag.advance_due_date()
                    ag.save()
                counts["approved"] += 1
            elif d.decision == CommitteeDecision.REJECT:
                app.decision_note = d.reason
                app.save()
                transition(app, GA.REJECTED, request.user, request, note=d.reason)
                counts["rejected"] += 1
            elif d.decision == CommitteeDecision.DEFER:
                app.info_request = d.reason
                app.save()
                if app.status != GA.INFO_REQUIRED:
                    transition(app, GA.INFO_REQUIRED, request.user, request, note=d.reason)
                counts["deferred"] += 1
        s.status, s.published_at = s.PUBLISHED, timezone.now()
        s.save()
    audit(request, "committee.results_published", s, **counts)
    messages.success(request, f"Results published: {counts['approved']} funded, {counts['rejected']} not funded, "
                              f"{counts['deferred']} deferred. All applicants have been notified.")
    return redirect(s)


@login_required
def committee_assess(request, pk, ref):
    """A committee member scores one application."""
    s = _session_for(request, pk)
    if not s.is_member(request.user):
        raise PermissionDenied
    app = get_object_or_404(s.applications().select_related("profile", "category"), reference=ref)
    instance = app.reviews.filter(reviewer=request.user).first() or Review(application=app, reviewer=request.user)
    form = ReviewForm(request.POST or None, instance=instance, criteria=s.call.criteria.all())
    if request.method == "POST":
        if s.status != s.IN_PROGRESS:
            messages.error(request, "Scoring is open only while the assessment is in progress.")
        elif form.is_valid():
            form.save()
            audit(request, "committee.scored", app, session=s.pk)
            messages.success(request, f"Score saved for {app.reference}.")
            ids = [d.application.reference for d in s.decisions.select_related("application")]
            nxt = ids[ids.index(ref) + 1] if ref in ids and ids.index(ref) + 1 < len(ids) else None
            return redirect(reverse("grants:committee_assess", args=[pk, nxt]) if nxt and "next" in request.POST else s.get_absolute_url())
    return render(request, "grants/committee_assess.html", {
        "s": s, "app": app, "form": form, "checks": app.eligibility_checks(),
        "budget_items": app.budget_items.all(), "documents": app.documents.select_related("doc_type")})


# ------------------------------------------------------------------ grantee reporting

@login_required
def my_grant(request, ref):
    app = get_object_or_404(GA, reference=ref, applicant=request.user, status=GA.APPROVED)
    ag = getattr(app, "agreement", None)
    if ag is None:
        messages.info(request, "Your grant agreement is being prepared.")
        return redirect(app)
    form = ReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and ag.health != "completed" and form.is_valid():
        rep = form.save(commit=False)
        rep.agreement = ag
        rep.save()
        ag.advance_due_date()
        ag.save(update_fields=["next_report_due"])
        audit(request, "monitoring.report_submitted", app, period=rep.period)
        target = ag.officer or app.assigned_to
        if target:
            notify(target, f"Grant report received: {app.reference}", rep.period, reverse("grants:monitor_detail", args=[ref]), email=False)
        messages.success(request, f"Report submitted. Your next report is due by {ag.next_report_due:%d %B %Y}.")
        return redirect("grants:my_grant", ref=ref)
    return render(request, "grants/my_grant.html", {"app": app, "ag": ag, "form": form, "reports": ag.reports.all()})


# ------------------------------------------------------------------ staff monitoring

@staff_required
def monitor_list(request):
    qs = GrantAgreement.objects.select_related("application", "application__profile", "officer").annotate(
        n_reports=Count("reports"), avg_pct=Avg("reports__percent_complete"))
    f = request.GET
    if f.get("health"):
        qs = qs.filter(health=f["health"])
    if f.get("overdue"):
        qs = qs.filter(next_report_due__lt=timezone.localdate()).exclude(health="completed")
    pending_reports = GrantReport.objects.filter(status=GrantReport.SUBMITTED).count()
    return render(request, "grants/monitor_list.html", {"ags": qs.order_by("next_report_due"), "f": f,
                                                        "health": GrantAgreement.HEALTH, "pending_reports": pending_reports,
                                                        "today": timezone.localdate()})


@staff_required
def monitor_detail(request, ref):
    ag = get_object_or_404(GrantAgreement.objects.select_related("application", "application__profile"), application__reference=ref)
    form = AgreementForm(request.POST if "save_agreement" in request.POST else None, instance=ag)
    visit = VisitForm(request.POST if "add_visit" in request.POST else None, initial={"visit_date": timezone.localdate(), "health": ag.health})
    if form.is_bound and form.is_valid():
        form.save()
        if ag.health == "completed" and not ag.closed_at:
            ag.closed_at = timezone.localdate()
            ag.save(update_fields=["closed_at"])
        audit(request, "monitoring.agreement_updated", ag.application, fields=form.changed_data)
        messages.success(request, "Monitoring record updated.")
        return redirect("grants:monitor_detail", ref=ref)
    if visit.is_bound and visit.is_valid():
        v = visit.save(commit=False)
        v.agreement, v.officer = ag, request.user
        v.save()
        ag.health = v.health
        ag.save(update_fields=["health"])
        audit(request, "monitoring.visit_logged", ag.application)
        messages.success(request, "Monitoring visit recorded.")
        return redirect("grants:monitor_detail", ref=ref)
    return render(request, "grants/monitor_detail.html", {"ag": ag, "app": ag.application, "form": form, "visit": visit,
                                                          "reports": ag.reports.all(), "visits": ag.visits.select_related("officer")})


@staff_required
@require_POST
def monitor_review_report(request, pk):
    rep = get_object_or_404(GrantReport.objects.select_related("agreement__application"), pk=pk)
    action = request.POST.get("action")
    if action not in (GrantReport.ACCEPTED, GrantReport.REVISION):
        raise PermissionDenied
    rep.status, rep.feedback = action, request.POST.get("feedback", "").strip()
    rep.reviewed_by, rep.reviewed_at = request.user, timezone.now()
    rep.save()
    app = rep.agreement.application
    audit(request, f"monitoring.report_{action}", app, period=rep.period)
    notify(app.applicant, f"Your grant report ({rep.period}) was {'accepted' if action == 'accepted' else 'returned for revision'}",
           rep.feedback, reverse("grants:my_grant", args=[app.reference]), sms=action == GrantReport.REVISION)
    messages.success(request, "Report reviewed and grantee notified.")
    return redirect("grants:monitor_detail", ref=app.reference)


@login_required
def report_attachment(request, pk):
    from accounts.views import _serve
    rep = get_object_or_404(GrantReport.objects.select_related("agreement__application"), pk=pk)
    if not (request.user.is_nacb_staff or rep.agreement.application.applicant_id == request.user.pk):
        raise PermissionDenied
    return _serve(rep.attachment)
