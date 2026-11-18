import calendar
import csv
from datetime import date, timezone as dt_tz

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import DISTRICTS
from core.permissions import district_scope, staff_required
from portal.services import audit, notify

from .models import Event, Registration


class RegistrationForm(forms.ModelForm):
    class Meta:
        model = Registration
        fields = ["entry_title", "entry_description", "group_size", "special_requirements"]
        widgets = {"entry_description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not (event and event.is_competition):
            del self.fields["entry_title"]
            del self.fields["entry_description"]
        else:
            self.fields["entry_title"].required = True


def event_list(request):
    qs = Event.objects.filter(status__in=["published", "cancelled"]).prefetch_related("disciplines")
    f = request.GET
    when = f.get("when", "upcoming")
    now = timezone.now()
    qs = qs.filter(ends_at__gte=now) if when == "upcoming" else qs.filter(ends_at__lt=now).order_by("-starts_at")
    if f.get("type"):
        qs = qs.filter(event_type=f["type"])
    if f.get("district"):
        qs = qs.filter(district=f["district"])
    if f.get("month"):
        try:
            y, m = map(int, f["month"].split("-"))
            qs = qs.filter(starts_at__year=y, starts_at__month=m)
        except ValueError:
            pass
    # Month calendar grid
    today = timezone.localdate()
    try:
        cy, cm = map(int, f.get("cal", f"{today.year}-{today.month}").split("-"))
        date(cy, cm, 1)
    except ValueError:
        cy, cm = today.year, today.month
    month_events = Event.objects.filter(status="published", starts_at__year=cy, starts_at__month=cm)
    by_day = {}
    for e in month_events:
        by_day.setdefault(timezone.localtime(e.starts_at).day, []).append(e)
    weeks = [[(d, by_day.get(d, [])) if d else (None, []) for d in week]
             for week in calendar.Calendar(firstweekday=0).monthdayscalendar(cy, cm)]
    prev_m = f"{cy - 1}-12" if cm == 1 else f"{cy}-{cm - 1}"
    next_m = f"{cy + 1}-1" if cm == 12 else f"{cy}-{cm + 1}"
    return render(request, "events/list.html", {
        "events": qs, "types": Event.TYPES, "districts": DISTRICTS, "f": f, "when": when,
        "weeks": weeks, "cal_label": date(cy, cm, 1).strftime("%B %Y"), "prev_m": prev_m, "next_m": next_m,
        "today": today if (today.year, today.month) == (cy, cm) else None,
    })


def event_detail(request, slug):
    event = get_object_or_404(Event.objects.exclude(status="draft"), slug=slug)
    reg = None
    if request.user.is_authenticated:
        reg = event.registrations.filter(user=request.user).first()
    form = RegistrationForm(event=event)
    return render(request, "events/detail.html", {"event": event, "reg": reg, "form": form,
                                                  "albums": event.albums.published(), "news": event.news.published()})


@login_required
@require_POST
def register(request, slug):
    event = get_object_or_404(Event, slug=slug, status="published")
    if not event.registration_open:
        messages.error(request, "Registration for this event is not open.")
        return redirect(event)
    if event.registered_only:
        profile = getattr(request.user, "profile", None)
        if not (profile and profile.is_verified):
            messages.error(request, "This programme is open to verified members of the National Artist Register only.")
            return redirect(event)
    form = RegistrationForm(request.POST, event=event)
    if not form.is_valid():
        return render(request, "events/detail.html", {"event": event, "form": form, "reg": None})
    reg, created = event.register(request.user, **form.cleaned_data)
    if reg is None:
        messages.error(request, "Sorry, this event is full.")
    elif not created:
        messages.info(request, "You are already registered for this event.")
    else:
        audit(request, f"event.{reg.status}", event)
        when = timezone.localtime(event.starts_at).strftime("%d %b %Y, %H:%M")
        if reg.status == Registration.CONFIRMED:
            notify(request.user, f"Registration confirmed: {event.title}", f"{when} at {event.venue}.", event.get_absolute_url(), sms=True)
            messages.success(request, "You are registered. A confirmation has been sent to you.")
        else:
            notify(request.user, f"Waitlisted: {event.title}", "The event is full. We will notify you if a place opens up.", event.get_absolute_url())
            messages.info(request, "The event is full, so you have been added to the waiting list.")
    return redirect(event)


@login_required
@require_POST
def cancel(request, slug):
    event = get_object_or_404(Event, slug=slug)
    reg = get_object_or_404(Registration, event=event, user=request.user)
    reg.status = Registration.CANCELLED
    reg.save(update_fields=["status"])
    audit(request, "event.cancelled_registration", event)
    for p in event.promote_waitlist():
        notify(p.user, f"A place is now available: {event.title}", "You have been moved from the waiting list to confirmed.",
               event.get_absolute_url(), sms=True)
    messages.info(request, "Your registration has been cancelled.")
    return redirect(event)


def ics(request, slug):
    event = get_object_or_404(Event, slug=slug, status="published")
    fmt = "%Y%m%dT%H%M%SZ"
    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//NACB//Events//EN", "BEGIN:VEVENT",
        f"UID:event-{event.pk}@nacb.org.bw", f"DTSTAMP:{timezone.now().astimezone(dt_tz.utc).strftime(fmt)}",
        f"DTSTART:{event.starts_at.astimezone(dt_tz.utc).strftime(fmt)}",
        f"DTEND:{event.ends_at.astimezone(dt_tz.utc).strftime(fmt)}",
        f"SUMMARY:{event.title}", f"LOCATION:{event.venue}, {event.get_district_display()}",
        f"DESCRIPTION:{event.summary}", "END:VEVENT", "END:VCALENDAR", ""])
    resp = HttpResponse(body, content_type="text/calendar")
    resp["Content-Disposition"] = f'attachment; filename="{event.slug}.ics"'
    return resp


# ------------------------------------------------------------------ staff

@staff_required
def manage_list(request):
    events = district_scope(Event.objects.all(), request.user).order_by("-starts_at")
    return render(request, "events/manage_list.html", {"events": events})


@staff_required
def manage_detail(request, slug):
    event = get_object_or_404(district_scope(Event.objects.all(), request.user), slug=slug)
    regs = event.registrations.select_related("user", "user__profile").order_by("status", "created_at")
    if request.GET.get("export") == "csv":
        audit(request, "event.export", event)
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="{event.slug}-registrations.csv"'
        resp.write("﻿")
        w = csv.writer(resp)
        w.writerow(["Name", "Email", "Phone", "Registration no.", "District", "Status", "Group size", "Entry", "Requirements", "Registered"])
        for r in regs:
            p = getattr(r.user, "profile", None)
            w.writerow([r.user.display_name, r.user.email, r.user.phone, p and p.registration_number, p and p.get_district_display(),
                        r.get_status_display(), r.group_size, r.entry_title, r.special_requirements,
                        timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M")])
        return resp
    return render(request, "events/manage_detail.html", {"event": event, "regs": regs, "statuses": Registration.STATUS})


@staff_required
@require_POST
def manage_attendance(request, slug):
    event = get_object_or_404(district_scope(Event.objects.all(), request.user), slug=slug)
    changed = 0
    for reg in event.registrations.all():
        new = request.POST.get(f"status_{reg.pk}")
        if new and new != reg.status and new in dict(Registration.STATUS):
            reg.status = new
            reg.save(update_fields=["status"])
            changed += 1
    promoted = event.promote_waitlist()
    for p in promoted:
        notify(p.user, f"A place is now available: {event.title}", "You have been moved from the waiting list to confirmed.",
               event.get_absolute_url(), sms=True)
    audit(request, "event.attendance_updated", event, changed=changed, promoted=len(promoted))
    messages.success(request, f"Updated {changed} registration(s). {len(promoted)} promoted from waitlist.")
    return redirect("events:manage_detail", slug=slug)

