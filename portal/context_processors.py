from django.conf import settings

from .i18n import strings
from .menus import account_menu
from .models import Page


def site_context(request):
    lang = request.session.get("lang", "en") if hasattr(request, "session") else "en"
    ctx = {
        "LANG": lang,
        "T": strings(lang),
        "SITE": {
            "name": "National Arts Council of Botswana",
            "short": "NACB",
            "phone": "+267 390 0000",
            "email": "info@nacb.org.bw",
            "address": "Plot 50369, Fairgrounds Office Park, Gaborone",
            "dpo": "dataprotection@nacb.org.bw",
            "hours": "Monday to Friday, 07:30 to 16:30",
            "facebook": "https://www.facebook.com/",
            "instagram": "https://www.instagram.com/",
            "x": "https://x.com/",
            "youtube": "https://www.youtube.com/",
        },
        "DEVELOPER": {"name": settings.DEVELOPER_NAME, "url": settings.DEVELOPER_URL},
        "footer_pages": Page.objects.published().filter(show_in_footer=True)[:6],
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_count"] = user.notifications.filter(is_read=False).count()
        ctx["account_menu"] = account_menu(user)
    return ctx
