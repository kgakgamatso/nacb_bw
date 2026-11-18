import os, re, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS.append("testserver")
from django.test import Client
from accounts.models import User
from grants.models import GrantApplication, CommitteeSession
from events.models import Event
from portal.models import Page, NewsPost, GalleryAlbum, Vacancy, Tender

pub = ["/", "/about/", "/services/", "/news/", "/gallery/", "/resources/", "/faqs/", "/contact/", "/search/?q=art",
       "/directory/", "/grants/", "/events/", "/events/?when=past", "/endorsements/", "/endorsements/verify/", "/jobs/",
       "/tenders/", "/data-protection/", "/accounts/signup/", "/accounts/login/"]
pub += [p.get_absolute_url() for p in Page.objects.published()] + [n.get_absolute_url() for n in NewsPost.objects.published()]
pub += [e.get_absolute_url() for e in Event.objects.exclude(status="draft")] + [a.get_absolute_url() for a in GalleryAlbum.objects.published()]
pub += [v.get_absolute_url() for v in Vacancy.objects.published()] + [t.get_absolute_url() for t in Tender.objects.published()]
pub += ["/grants/" + s + "/" for s in ["arts-and-culture-grant-2026-27", "arts-and-culture-grant-2026-round-1"]]
staff = ["/staff/", "/staff/registry/", "/staff/reports/", "/staff/users/", "/staff/audit/", "/grants/manage/?all=1",
         "/grants/committee/", "/grants/monitoring/", "/endorsements/manage/", "/events/manage/", "/staff/registry/data-quality/"]
staff += [f"/grants/manage/{a.reference}/" for a in GrantApplication.objects.exclude(status="draft")[:5]]
staff += [s.get_absolute_url() for s in CommitteeSession.objects.all()[:2]] + [s.get_absolute_url() + "report/" for s in CommitteeSession.objects.all()[:2]]
art = ["/dashboard/", "/accounts/profile/", "/accounts/settings/", "/grants/my-applications/", "/endorsements/mine/", "/notifications/"]

DASH = re.compile(r"[–—]|&ndash;|&mdash;|&#8211;|&#8212;")
hits, checked, errors = [], 0, []
def scan(c, urls, who):
    global checked
    for u in urls:
        r = c.get(u)
        checked += 1
        if r.status_code >= 500:
            errors.append((who, u, r.status_code))
            continue
        body = r.content.decode("utf-8", "ignore")
        body = re.sub(r"<(script|style)[\s\S]*?</\1>", "", body)
        for m in DASH.finditer(body):
            hits.append((who, u, body[max(0, m.start() - 50):m.end() + 30].replace("\n", " ")))
scan(Client(), pub, "public")
for email, urls in [("admin@nacb.test", staff), ("approver@nacb.test", staff[:8]), ("artist@nacb.test", art), ("round1-1@nacb.test", art)]:
    c = Client(); c.force_login(User.objects.get(email=email)); scan(c, urls, email.split("@")[0])
print("pages checked:", checked, "| server errors:", errors or "none", "| dash hits:", len(hits))
from collections import Counter
print(Counter((w,u) for w,u,_ in hits))
for h in [h for h in hits if "audit" not in h[1]][:10]:
    print(" ", h)
