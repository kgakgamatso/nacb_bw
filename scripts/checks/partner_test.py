import os, re, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS.append("testserver")
from django.test import Client
from accounts.models import User
from events.models import Event
from partnerships.models import CSRProgramme, PartnershipEnquiry, SponsorshipPackage
from portal.models import Notification

fails = []
def check(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)
DASH = re.compile(r"[–—]")

pub = Client()
pk = SponsorshipPackage.objects.filter(event__isnull=False, level="gold").select_related("event").first()
prog = CSRProgramme.objects.first()
for u in ["/partner/", prog.get_absolute_url(), pk.event.get_absolute_url(), "/"]:
    r = pub.get(u); body = r.content.decode()
    check(r.status_code == 200, f"GET {u}")
    check(not DASH.search(re.sub(r"<(script|style)[\s\S]*?</\1>", "", body)), f"no long dashes on {u}")
check("Sponsor this event" in pub.get(pk.event.get_absolute_url()).content.decode(), "event page shows sponsor box")
check("Partners and sponsors" in pub.get("/").content.decode(), "home shows partners strip")
check(b"CSR programmes looking for funding" in pub.get("/partner/").content, "partner page lists CSR programmes")

before_notes = Notification.objects.filter(title="New partnership enquiry").count()
taken = pk.slots_taken
r = pub.post("/partner/", {"organisation": "Test Sponsor Ltd", "contact_name": "Test Person", "email": "sponsor@example.test",
                           "interest": "event", "event": pk.event.pk, "package": pk.pk, "budget": "25-100", "message": "We would like Gold."})
enq = PartnershipEnquiry.objects.filter(organisation="Test Sponsor Ltd").first()
check(r.status_code == 302 and enq is not None, "enquiry submitted")
check(Notification.objects.filter(title="New partnership enquiry").count() > before_notes, "staff notified of enquiry")
r = pub.post("/partner/", {"organisation": "", "contact_name": "", "email": "bad", "interest": ""})
check(r.status_code == 200 and b"errorlist" in r.content, "invalid enquiry shows errors")
r = pub.post("/partner/", {"organisation": "Bot", "contact_name": "Bot", "email": "b@b.test", "interest": "other", "website": "spam"})
check(not PartnershipEnquiry.objects.filter(organisation="Bot").exists(), "spam trap blocks bots")

off = Client(); off.force_login(User.objects.get(email="officer@nacb.test"))
check(off.get("/partner/manage/").status_code == 200, "staff enquiry list")
check(off.get(f"/partner/manage/{enq.pk}/").status_code == 200, "staff enquiry detail")
off.post(f"/partner/manage/{enq.pk}/update/", {"status": "agreed", "note": "Signed Gold agreement"})
enq.refresh_from_db(); pk.refresh_from_db()
check(enq.status == "agreed" and "Signed Gold agreement" in enq.notes and enq.handled_by is not None, "officer records agreement and note")
check(pk.slots_taken == taken + 1, "agreed sponsorship reserves a package place")
art = Client(); art.force_login(User.objects.get(email="artist@nacb.test"))
check(art.get("/partner/manage/").status_code == 403, "artists cannot see enquiries")
check(pub.get("/partner/manage/").status_code in (302, 403), "public cannot see enquiries")

# clean up test data
pk.slots_taken = taken; pk.save(); enq.delete()
print("\nFAILED:", fails or "none")
