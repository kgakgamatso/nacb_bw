from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import DISTRICTS, Discipline, Profile
from events.models import Event, Registration
from grants.models import GrantAgreement, GrantApplication, GrantCall
from partnerships.models import Partner

from .models import (FAQ, ContactMessage, GalleryAlbum, LeadershipMember, NewsletterSubscriber, NewsPost,
                     Notification, Page, Resource)
from .services import audit, notify_staff


def home(request):
    import calendar
    from .models import Tender, Vacancy
    now = timezone.now()
    today = timezone.localdate()
    calls = [c for c in GrantCall.objects.filter(status="published", closes_at__gte=now) if c.is_open][:4]
    month_events = Event.objects.filter(status="published", starts_at__year=today.year, starts_at__month=today.month)
    by_day = {}
    for e in month_events:
        by_day.setdefault(timezone.localtime(e.starts_at).day, []).append(e)
    weeks = [[(d, by_day.get(d, [])) for d in w] for w in calendar.Calendar().monthdayscalendar(today.year, today.month)]
    from django.db.models import Count
    verified = Profile.objects.filter(status=Profile.VERIFIED)
    group_counts = dict(verified.exclude(primary_discipline=None).values_list("primary_discipline__group").annotate(c=Count("id")))
    mosaic = [(key, label, group_counts.get(key, 0)) for key, label in Discipline.GROUPS]
    spotlight = list(verified.filter(is_public=True).select_related("user", "primary_discipline").order_by("?")[:4])
    
    return render(request, "portal/home.html", {
        "ribbon": list(Discipline.objects.values_list("name", flat=True)),
        "mosaic": mosaic, "spotlight": spotlight,
        "partners": Partner.objects.filter(active=True, featured=True)[:6],
        "past_albums": GalleryAlbum.objects.published().select_related("event").prefetch_related("images")[:4],
        "news": NewsPost.objects.published()[:3],
        "events": Event.objects.filter(status="published", ends_at__gte=now)[:4],
        "calls": calls, "weeks": weeks, "today": today, "cal_label": today.strftime("%B %Y"),
        "vacancies": Vacancy.objects.published().filter(closing_date__gte=now)[:4],
        "tenders": Tender.objects.published().filter(closing_date__gte=now)[:4],
        "stats": {
            "artists": Profile.objects.filter(status=Profile.VERIFIED).count(),
            "disciplines": Discipline.objects.count(),
            "districts": len(DISTRICTS),
            "grants": GrantApplication.objects.filter(status=GrantApplication.APPROVED).count(),
        },
    })


def page(request, slug):
    pg = get_object_or_404(Page.objects.published(), slug=slug)
    return render(request, "portal/page.html", {"page": pg})


def about(request):
    return render(request, "portal/about.html", {
        "page": Page.objects.published().filter(slug="about").first(),
        "board": LeadershipMember.objects.filter(group="board"),
        "management": LeadershipMember.objects.filter(group="management"),
    })


def services(request):
    return render(request, "portal/services.html")


def news_list(request):
    qs = NewsPost.objects.published()
    cat = request.GET.get("category")
    if cat:
        qs = qs.filter(category=cat)
    page_obj = Paginator(qs, 9).get_page(request.GET.get("page"))
    return render(request, "portal/news_list.html", {"page": page_obj, "categories": NewsPost.CATEGORIES, "cat": cat,
                                                     "albums": GalleryAlbum.objects.published()[:4]})


def news_detail(request, slug):
    post = get_object_or_404(NewsPost.objects.published(), slug=slug)
    related = NewsPost.objects.published().filter(category=post.category).exclude(pk=post.pk)[:3]
    return render(request, "portal/news_detail.html", {"post": post, "related": related,
                                                       "share_url": request.build_absolute_uri()})


def gallery(request):
    return render(request, "portal/gallery.html", {"albums": GalleryAlbum.objects.published().prefetch_related("images")})


def album(request, slug):
    a = get_object_or_404(GalleryAlbum.objects.published(), slug=slug)
    return render(request, "portal/album.html", {"album": a})


def resources(request):
    qs = Resource.objects.published()
    cat = request.GET.get("category")
    if cat:
        qs = qs.filter(category=cat)
    grouped = {}
    for r in qs:
        grouped.setdefault(r.get_category_display(), []).append(r)
    return render(request, "portal/resources.html", {"grouped": grouped, "categories": Resource.CATEGORIES, "cat": cat})


def resource_download(request, pk):
    r = get_object_or_404(Resource.objects.published(), pk=pk)
    Resource.objects.filter(pk=pk).update(downloads=F("downloads") + 1)
    if r.file:
        return FileResponse(r.file.open("rb"), as_attachment=True, filename=r.file.name.rsplit("/", 1)[-1])
    if r.external_url:
        return HttpResponseRedirect(r.external_url)
    raise Http404


def faqs(request):
    grouped = {}
    for f in FAQ.objects.filter(published=True):
        grouped.setdefault(f.get_category_display(), []).append(f)
    return render(request, "portal/faqs.html", {"grouped": grouped})


class ContactForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "category", "subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}


def contact(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name(), "email": request.user.email, "phone": request.user.phone}
    initial["category"] = request.GET.get("category", "general")
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("website"):
            return redirect("portal:contact")
        msg = form.save(commit=False)
        if request.user.is_authenticated:
            msg.user = request.user
        msg.save()
        audit(request, "contact.submitted", msg)
        notify_staff("New contact message", f"{msg.get_category_display()}: {msg.subject}", f"/staff/messages/{msg.pk}/")
        messages.success(request, "Thank you. Your message has been sent. NACB will respond within 3 working days.")
        return redirect("portal:contact")
    return render(request, "portal/contact.html", {"form": form, "districts": DISTRICTS})


@require_POST
def subscribe(request):
    email = (request.POST.get("email") or "").strip().lower()
    nxt = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    try:
        forms.EmailField().clean(email)
    except forms.ValidationError:
        messages.error(request, "Please enter a valid email address.")
        return redirect(nxt)
    sub, created = NewsletterSubscriber.objects.get_or_create(email=email, defaults={"name": request.POST.get("name", "")})
    if not sub.active:
        sub.active = True
        sub.save(update_fields=["active"])
    messages.success(request, "You are subscribed to the NACB newsletter.")
    return redirect(nxt)


def unsubscribe(request, token):
    sub = get_object_or_404(NewsletterSubscriber, token=token)
    sub.active = False
    sub.save(update_fields=["active"])
    return render(request, "portal/message.html", {"title": "Unsubscribed", "text": "You will no longer receive the NACB newsletter."})


def search(request):
    q = (request.GET.get("q") or "").strip()
    results = []
    if len(q) >= 2:
        for n in NewsPost.objects.published().filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(body__icontains=q))[:10]:
            results.append(("News", n.title, n.summary, n.get_absolute_url()))
        for e in Event.objects.filter(status="published").filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(venue__icontains=q))[:10]:
            results.append(("Event", e.title, e.summary, e.get_absolute_url()))
        for c in GrantCall.objects.exclude(status="draft").filter(Q(title__icontains=q) | Q(summary__icontains=q))[:10]:
            results.append(("Grant call", c.title, c.summary, c.get_absolute_url()))
        for p in Page.objects.published().filter(Q(title__icontains=q) | Q(body__icontains=q))[:10]:
            results.append(("Page", p.title, p.summary, p.get_absolute_url()))
        for r in Resource.objects.published().filter(Q(title__icontains=q) | Q(description__icontains=q))[:10]:
            results.append(("Resource", r.title, r.description[:200], f"/resources/{r.pk}/download/"))
        for f in FAQ.objects.filter(published=True).filter(Q(question__icontains=q) | Q(answer__icontains=q))[:10]:
            results.append(("FAQ", f.question, f.answer[:200], "/faqs/#faq-%d" % f.pk))
        for p in _directory_qs().filter(Q(org_name__icontains=q) | Q(stage_name__icontains=q) | Q(user__first_name__icontains=q)
                                        | Q(user__last_name__icontains=q))[:10]:
            results.append(("Artist", p.display_name, str(p.primary_discipline or ""), p.get_absolute_url()))
    return render(request, "portal/search.html", {"q": q, "results": results})


def _directory_qs():
    return Profile.objects.filter(status=Profile.VERIFIED, is_public=True).select_related("user", "primary_discipline")


def directory(request):
    qs = _directory_qs()
    f = request.GET
    if f.get("q"):
        q = f["q"]
        qs = qs.filter(Q(org_name__icontains=q) | Q(stage_name__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q))
    if f.get("discipline"):
        qs = qs.filter(disciplines__slug=f["discipline"]).distinct() | qs.filter(primary_discipline__slug=f["discipline"])
    if f.get("district"):
        qs = qs.filter(district=f["district"])
    if f.get("group"):
        qs = qs.filter(primary_discipline__group=f["group"])
    if f.get("type"):
        qs = qs.filter(account_type=f["type"])
    page_obj = Paginator(qs.distinct().order_by("user__last_name", "org_name"), 24).get_page(f.get("page"))
    return render(request, "portal/directory.html", {"page": page_obj, "disciplines": Discipline.objects.all(),
                                                     "districts": DISTRICTS, "f": f})


def artist_detail(request, pk):
    p = get_object_or_404(_directory_qs(), pk=pk)
    items = [i for i in p.portfolio.all() if i.publicly_visible()] if p.show_portfolio else []
    return render(request, "portal/artist_detail.html", {"p": p, "items": items})


@require_POST
def set_language(request):
    lang = request.POST.get("lang", "en")
    request.session["lang"] = "tn" if lang == "tn" else "en"
    if request.user.is_authenticated:
        request.user.preferred_language = request.session["lang"]
        request.user.save(update_fields=["preferred_language"])
    nxt = request.POST.get("next", "/")
    return redirect(nxt if url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}) else "/")


# ------------------------------------------------------------------ logged-in user

@login_required
def dashboard(request):
    user = request.user
    if user.is_nacb_staff:
        return redirect("backoffice:dashboard")
    if user.role == "committee":
        return redirect("grants:committee_list")
    profile = getattr(user, "profile", None)
    now = timezone.now()
    regs = user.event_registrations.filter(event__ends_at__gte=now).exclude(status=Registration.CANCELLED).select_related("event")
    apps = user.grant_applications.select_related("call").exclude(status=GrantApplication.WITHDRAWN)
    open_calls = [c for c in GrantCall.objects.filter(status="published", closes_at__gte=now) if c.is_open]
    return render(request, "portal/dashboard.html", {
        "profile": profile, "apps": apps[:6], "endorsements": user.endorsements.all()[:5],
        "regs": regs, "notifications": user.notifications.all()[:6], "open_calls": open_calls[:3],
        "events": Event.objects.filter(status="published", ends_at__gte=now)[:3],
        "agreements": GrantAgreement.objects.filter(application__applicant=user).exclude(health="completed").select_related("application"),
    })


@login_required
def notifications(request):
    qs = request.user.notifications.all()
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "portal/notifications.html", {"page": page_obj})


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.is_read = True
    n.save(update_fields=["is_read"])
    link = n.link if n.link and url_has_allowed_host_and_scheme(n.link, allowed_hosts={request.get_host()}) else None
    return redirect(link or "portal:notifications")


@login_required
@require_POST
def notifications_read_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("portal:notifications")


def error_404(request, exception):
    return render(request, "portal/message.html", {"title": "Page not found",
                                                   "text": "The page you are looking for does not exist or has moved."}, status=404)


def error_500(request):
    return render(request, "500.html", status=500)
