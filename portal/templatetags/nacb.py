from django import template
from django.utils.html import format_html

register = template.Library()

BADGE = {
    # registry
    "incomplete": "muted", "pending": "warn", "verified": "ok", "flagged": "bad", "suspended": "bad",
    # grants / endorsements
    "draft": "muted", "submitted": "info", "under_review": "info", "info_required": "warn", "recommended": "accent",
    "approved": "ok", "issued": "ok", "rejected": "bad", "withdrawn": "muted",
    # events
    "confirmed": "ok", "waitlisted": "warn", "cancelled": "muted", "attended": "ok", "no_show": "bad",
    "published": "ok", "closed": "muted",
    "on_track": "ok", "at_risk": "warn", "off_track": "bad", "completed": "muted",
    "scheduled": "info", "in_progress": "info", "concluded": "accent", "Open": "ok", "Opening soon": "info", "Closed": "muted",
}


@register.simple_tag
def badge(status, label=None):
    return format_html('<span class="badge badge-{}">{}</span>', BADGE.get(status, "info"), label or status)


@register.filter
def get_item(d, key):
    try:
        v = d.get(key)
        return d.get(str(key)) if v is None else v
    except AttributeError:
        return None


@register.filter
def money(value):
    if value in (None, ""):
        return "None"
    try:
        return f"P{float(value):,.2f}"
    except (TypeError, ValueError):
        return value


@register.filter
def pct(value, total):
    try:
        return int(float(value) * 100 / float(total)) if float(total) else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def initials(name):
    parts = [p for p in str(name).split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


@register.simple_tag(takes_context=True)
def active(context, prefix):
    path = context["request"].path
    if prefix == "/":
        return "page" if path == "/" else ""
    return "page" if path.startswith(prefix) else ""


@register.simple_tag(takes_context=True)
def nav_active(context, prefix):
    return "active" if context["request"].path.startswith(prefix) else ""


ICON_KEYS = [
    ("immersive", "vr"), ("game", "games"), ("stream", "broadcast"), ("technology", "pentool"), ("digital", "pentool"),
    ("schools", "music"), ("music", "music"), ("gospel", "music"), ("drum", "music"), ("instrument", "music"),
    ("dance", "dance"), ("youth", "dance"), ("theatre", "stage"), ("comedy", "stage"), ("poetry", "literary"),
    ("festival", "stage"), ("performance", "stage"), ("competition", "dance"), ("performing", "stage"),
    ("visual", "visual"), ("paint", "visual"), ("photo", "camera"), ("exhibition", "visual"), ("sculpt", "visual"), ("mural", "visual"),
    ("craft", "craft"), ("basket", "craft"), ("weav", "craft"), ("pottery", "craft"), ("fashion", "craft"), ("jewel", "craft"),
    ("livelihoods", "craft"), ("heritage", "heritage"), ("folklore", "heritage"), ("indigenous", "heritage"), ("traditional", "heritage"),
    ("film", "film"), ("animation", "film"), ("television", "film"), ("literary", "literary"), ("writ", "literary"),
    ("publish", "literary"), ("story", "literary"), ("inclusion", "access"), ("access", "access"),
    ("training", "programme"), ("workshop", "programme"), ("bootcamp", "pentool"), ("grant", "funding"), ("fund", "funding"),
]
TONES = 4


@register.filter
def icon_for(obj):
    """Icon name for content without its own photo, matched on theme, type, discipline or title."""
    if isinstance(obj, str):
        text = obj.lower()
    else:
        text = " ".join(str(getattr(obj, a, "") or "") for a in
                        ("theme", "event_type", "group", "category", "primary_discipline", "title", "name")).lower()
    for key, name in ICON_KEYS:
        if key in text:
            return name
    model = getattr(getattr(obj, "_meta", None), "model_name", "")
    return {"newspost": "news", "galleryalbum": "camera", "event": "programme", "profile": "creatives"}.get(model, "artforms")


@register.filter
def tone(obj):
    """Colour tone 0-3 so neighbouring placeholders differ."""
    return (getattr(obj, "pk", 0) or 0) % TONES


@register.filter
def first_word(csv_text):
    """First item of a comma-separated list (e.g. the first rotating hero verb)."""
    return str(csv_text).split(",")[0]


@register.filter
def nodash(value):
    """Display older stored labels (e.g. audit entries) without long dashes; the stored record is never changed."""
    import re
    text = str(value)
    text = re.sub(r"\s[–—]\s", ": ", text)
    return re.sub(r"[–—]", " to ", text)


@register.simple_tag
def icon(name, size=24, label=""):
    """Inline icon from templates/includes/icons.html. Decorative unless a label is given."""
    if label:
        return format_html('<svg class="icon" width="{}" height="{}" role="img" aria-label="{}"><use href="#i-{}"></use></svg>', size, size, label, name)
    return format_html('<svg class="icon" width="{}" height="{}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', size, size, name)
