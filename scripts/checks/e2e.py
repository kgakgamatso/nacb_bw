import os, sys, io
sys.path.insert(0, os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS.append("testserver")
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from accounts.models import User
from grants.models import GrantCall, CommitteeSession, GrantAgreement, GrantApplication
from core.validators import validate_document

fails = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

def login(email):
    c = Client(); c.force_login(User.objects.get(email=email)); return c

# --- uploads
for name, data, ok in [("cv.exe", b"MZ\x90\x00", False), ("cv.pdf.exe", b"%PDF", False), ("fake.pdf", b"MZ\x90\x00rest", False),
                       ("doc.pdf", b"%PDF-1.4", True), ("big.pdf", b"%PDF" + b"0" * (6 * 1024 * 1024), False), ("x.bat", b"echo", False)]:
    try: validate_document(SimpleUploadedFile(name, data)); res = True
    except ValidationError: res = False
    check(res == ok, f"upload {name} {'accepted' if ok else 'rejected'}")

# --- reset demo round
from grants.models import Review, ApplicationEvent
_call = GrantCall.objects.get(reference="ACG-2026-01")
CommitteeSession.objects.filter(call=_call).delete()
GrantAgreement.objects.filter(application__call=_call).delete()
Review.objects.filter(application__call=_call).delete()
ApplicationEvent.objects.filter(application__call=_call).delete()
GrantApplication.objects.filter(call=_call).update(status="submitted", amount_awarded=None, decision_note="", info_request="")
User.objects.filter(email="panel2@nacb.test").delete()

# --- public pages
c = Client()
for u in ["/", "/jobs/", "/tenders/", "/data-protection/", "/p/cookies/", "/p/privacy/", "/events/", "/news/",
          "/jobs/nacb-hr-2026-14/", "/tenders/nacb-t-2026-07/"]:
    r = c.get(u); check(r.status_code == 200, f"GET {u} {r.status_code}")
r = c.post("/data-protection/", {"name": "A B", "email": "a@b.test", "request_type": "access", "details": "copy please"})
check(r.status_code == 302, "data request submitted")

# --- committee flow
off = login("officer@nacb.test"); appr = login("approver@nacb.test"); com = login("committee@nacb.test")
call = GrantCall.objects.get(reference="ACG-2026-01")
officer = User.objects.get(email="officer@nacb.test"); approver = User.objects.get(email="approver@nacb.test")
member = User.objects.get(email="committee@nacb.test")
# meeting before close must be rejected
r = off.post("/grants/committee/new/", {"call": call.pk, "title": "Bad", "meeting_date": (call.closes_at - timezone.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
             "chair": approver.pk, "members": [member.pk, officer.pk]})
check(r.status_code == 200 and not CommitteeSession.objects.filter(title="Bad").exists(), "sitting before close date rejected")
r = off.post("/grants/committee/new/", {"call": call.pk, "title": "Round 1 Assessment Committee", "venue": "NACB Boardroom",
             "meeting_date": timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M"), "chair": approver.pk,
             "members": [member.pk, officer.pk], "budget_available": "250000"})
s = CommitteeSession.objects.get(title="Round 1 Assessment Committee")
check(r.status_code == 302 and s.decisions.count() == 4, "sitting scheduled with 4 applications")
check(com.get(s.get_absolute_url()).status_code == 200, "committee member can open sitting")
check(login("artist@nacb.test").get(s.get_absolute_url()).status_code == 403, "artist blocked from sitting")
r = appr.post(f"/grants/committee/{s.pk}/start/"); s.refresh_from_db(); check(s.status == "in_progress", "assessment started")
crit = list(call.criteria.all())
for who in (com, off):
    for d in s.decisions.all():
        data = {f"score_{c.pk}": c.max_score - 3 for c in crit}; data.update(recommendation="approve", comments="Good")
        r = who.post(f"/grants/committee/{s.pk}/assess/{d.application.reference}/", data)
        check(r.status_code == 302, f"scored {d.application.reference}")
r = com.get(f"/grants/committee/{s.pk}/"); check(b"%" in r.content, "scores shown on sitting page")
post = {}
ds = list(s.decisions.select_related("application"))
for i, d in enumerate(ds):
    pre = f"d{d.pk}-"
    if i < 2: post.update({pre+"decision": "approve", pre+"amount": str(int(d.application.amount_requested)), pre+"rank": i+1, pre+"conditions": "Submit quarterly reports", pre+"reason": ""})
    elif i == 2: post.update({pre+"decision": "reject", pre+"amount": "", pre+"rank": "", pre+"conditions": "", pre+"reason": "Budget not justified"})
    else: post.update({pre+"decision": "defer", pre+"amount": "", pre+"rank": "", pre+"conditions": "", pre+"reason": "Send venue confirmation"})
r = com.post(f"/grants/committee/{s.pk}/decisions/", post); check(r.status_code == 403, "plain member cannot record decisions")
r = appr.post(f"/grants/committee/{s.pk}/decisions/", post)
check(s.decisions.filter(decision="pending").count() == 0, "decisions recorded by chair")
r = appr.post(f"/grants/committee/{s.pk}/conclude/", {"minutes": "Quorum present. Resolved as recorded.", "conflicts_declared": "None", "conclude": "1"})
s.refresh_from_db(); check(s.status == "concluded", "sitting concluded")
r = appr.get(f"/grants/committee/{s.pk}/report/"); check(r.status_code == 200 and b"summary report" in r.content, "summary report renders")
r = appr.get(f"/grants/committee/{s.pk}/report/?format=csv"); check(r.status_code == 200 and b"Reference" in r.content, "summary CSV")
r = appr.post(f"/grants/committee/{s.pk}/publish/"); s.refresh_from_db()
check(s.status == "published", "results published")
st = sorted(GrantApplication.objects.filter(call=call).values_list("status", flat=True))
check(st == ["approved", "approved", "info_required", "rejected"], f"application outcomes {st}")
win = GrantApplication.objects.filter(call=call, status="approved").first()
check(win.applicant.notifications.filter(title__icontains="Approved").exists(), "winner alerted")
check(GrantAgreement.objects.filter(application=win).exists(), "grant agreement opened for monitoring")
# grantee reporting
g = login(win.applicant.email)
check(g.get("/dashboard/").status_code == 200, "grantee dashboard")
r = g.post(f"/grants/my-grant/{win.reference}/", {"report_type": "progress", "period": "Q1", "percent_complete": 25,
           "progress": "Recorded 3 songs", "spent_to_date": "10000",
           "attachment": SimpleUploadedFile("receipts.pdf", b"%PDF-1.4 receipts", content_type="application/pdf")})
check(r.status_code == 302 and win.agreement.reports.count() == 1, "grantee report submitted")
r = g.post(f"/grants/my-grant/{win.reference}/", {"report_type": "progress", "period": "Q2", "percent_complete": 30, "progress": "x",
           "attachment": SimpleUploadedFile("virus.exe", b"MZ...", content_type="application/octet-stream")})
check(win.agreement.reports.count() == 1, "exe evidence rejected")
check(off.get("/grants/monitoring/").status_code == 200, "monitoring list")
check(off.get(f"/grants/monitoring/{win.reference}/").status_code == 200, "monitoring detail")
rep = win.agreement.reports.first()
off.post(f"/grants/monitoring/report/{rep.pk}/review/", {"action": "accepted", "feedback": "Thank you"})
rep.refresh_from_db(); check(rep.status == "accepted", "report accepted by officer")
ag = win.agreement; ag.next_report_due = timezone.localdate() - timezone.timedelta(days=3); ag.save()
call_command("send_report_reminders"); ag.refresh_from_db(); check(ag.health == "at_risk", "overdue grant flagged at risk")

# --- user management
adm = login("admin@nacb.test")
check(adm.get("/staff/users/").status_code == 200, "user list")
check(off.get("/staff/users/").status_code == 403, "officer blocked from user management")
r = adm.post("/staff/users/new/", {"email": "panel2@nacb.test", "first_name": "Panel", "last_name": "Two", "role": "committee", "is_active": "on"})
nu = User.objects.get(email="panel2@nacb.test"); check(r.status_code == 302 and not nu.has_usable_password(), "user created, set-password link")
r = adm.post(f"/staff/users/{nu.pk}/", {"email": nu.email, "first_name": "Panel", "last_name": "Two", "role": "district_officer", "district": ""})
check(r.status_code == 200, "district officer without district rejected")
victim = Client(); victim.force_login(nu)
adm.post(f"/staff/users/{nu.pk}/action/", {"action": "deactivate"}); nu.refresh_from_db()
check(not nu.is_active and victim.get("/dashboard/").status_code == 302, "deactivated user signed out")
adm.post(f"/staff/users/{nu.pk}/action/", {"action": "activate"}); nu.refresh_from_db(); check(nu.is_active, "reactivated")
r = adm.post("/staff/users/bulk/", {"ids": [nu.pk], "bulk": "deactivate"}); nu.refresh_from_db(); check(not nu.is_active, "bulk deactivate")
check(adm.get("/staff/users/?export=csv").status_code == 200, "user CSV export")
me = User.objects.get(email="admin@nacb.test")
adm.post(f"/staff/users/{me.pk}/action/", {"action": "deactivate"}); me.refresh_from_db(); check(me.is_active, "admin cannot deactivate self")
# my data export
r = login("artist@nacb.test").get("/data-protection/my-data.json"); check(r.status_code == 200 and b"register_profile" in r.content, "personal data export")
# menus A-Z
r = login("artist@nacb.test").get("/dashboard/"); check(b"az-menu" in r.content and b"Dumela" not in r.content, "A-Z menu, no greeting")
from portal.menus import account_menu
for e in ["artist@nacb.test", "officer@nacb.test", "admin@nacb.test", "committee@nacb.test"]:
    labels = [l for l, _ in account_menu(User.objects.get(email=e))]
    check(labels == sorted(labels, key=str.lower), f"menu sorted for {e} ({len(labels)} items)")
print("\nFAILED:", fails if fails else "none")
