"""Extra demo content: privacy/cookie pages, jobs, tenders and a CLOSED grant round with submitted applications
so the committee assessment -> decisions -> report -> publish -> monitoring flow can be demonstrated.

    python manage.py seed_demo_round        (run after seed_demo --demo-users; development only)
Demo accounts use the password from NACB_DEMO_PASSWORD (see portal/demo_credentials.py)."""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Discipline, Profile, User
from grants.models import BudgetItem, DocumentType, GrantApplication, GrantCall, ScoringCriterion
from portal.models import Page, Tender, Vacancy

from portal.demo_credentials import demo_password

PAGES = {
    "cookies": ("Cookie notice", "<p>This website uses <strong>only essential cookies</strong>. They are needed for the site to work and cannot be switched off:</p>"
                "<table><thead><tr><th>Cookie</th><th>Purpose</th><th>How long</th></tr></thead><tbody>"
                "<tr><td>sessionid</td><td>Keeps you signed in</td><td>Until you close your browser, or 8 hours</td></tr>"
                "<tr><td>csrftoken</td><td>Protects forms from forgery</td><td>1 year</td></tr>"
                "<tr><td>nacb_cookie_ack</td><td>Remembers that you have seen this notice</td><td>1 year</td></tr></tbody></table>"
                "<p>Your language choice is kept in your session. We do not use advertising, profiling or third-party tracking cookies. "
                "If NACB ever adds website statistics, we will ask for your consent first and update this notice.</p>"
                "<p>Embedded YouTube videos use the privacy-enhanced youtube-nocookie.com domain.</p>"),
    "data-protection": ("Data protection", "<p>NACB processes personal information in line with the <strong>Botswana Data Protection Act</strong>. "
                        "We collect only what we need to run the National Artist Register, grants, programmes and endorsements.</p>"
                        "<h2>How we protect your data</h2><ul><li>ID documents, bank letters and proposals are stored outside the public website and can only be opened by you and authorised staff. Every staff access is logged.</li>"
                        "<li>All traffic is encrypted (HTTPS). Staff accounts use two-step verification.</li>"
                        "<li>Staff only see what their role needs; district officers only see their own district.</li>"
                        "<li>Data is kept in Botswana or an approved data centre and backed up daily.</li></ul>"
                        "<h2>How long we keep it</h2><ul><li>Register records: while you are registered, then 2 years.</li>"
                        "<li>Grant applications and decisions: 7 years (public finance records).</li>"
                        "<li>Unsuccessful applications: 3 years. Contact messages: 2 years.</li></ul>"),
}


BIOS = [
    "Singer and guitarist reworking Setswana folk songs from the Central district for new audiences.",
    "Choreographer running youth dance residencies in Maun, mixing traditional and contemporary movement.",
    "Painter making large murals for clinics and schools, inspired by everyday village life.",
    "Basket weaver from the Etsha villages, working with natural dyes and ilala palm.",
]


class Command(BaseCommand):
    help = "Seed demo jobs, tenders, policy pages and a closed grant round"

    def handle(self, *args, **opts):
        now = timezone.now()
        for slug, (title, body) in PAGES.items():
            Page.objects.update_or_create(slug=slug, defaults={"title": title, "body": body, "status": "published",
                                                               "show_in_footer": False})
        priv = Page.objects.filter(slug="privacy").first()
        if priv and "Data protection officer" not in priv.body:
            priv.body += ("<h2>Data protection officer</h2><p>Contact dataprotection@nacb.org.bw. You can also use the "
                          "<a href='/data-protection/'>data protection page</a> to request a copy of your data, a correction or deletion.</p>")
            priv.save()

        for title, ref, dept, typ, days in [
            ("Grants Officer", "NACB/HR/2026/14", "Creative & Cultural Sector Development", "permanent", 21),
            ("Communications Intern", "NACB/HR/2026/15", "Communications", "internship", 14),
            ("ICT Systems Administrator", "NACB/HR/2026/16", "Corporate Services", "contract", 28)]:
            Vacancy.objects.get_or_create(slug=ref.lower().replace("/", "-"), defaults={
                "title": title, "reference": ref, "department": dept, "employment_type": typ, "status": "published",
                "summary": f"NACB is looking for a {title} to join the {dept} team.",
                "description": "<ul><li>Support the delivery of NACB programmes</li><li>Prepare reports and maintain records</li></ul>",
                "requirements": "<ul><li>Relevant degree or diploma</li><li>At least 2 years' experience (not required for internships)</li></ul>",
                "closing_date": now + timedelta(days=days)})
        for title, ref, cat, days in [
            ("Supply of sound and stage equipment for the National Arts Festival", "NACB/T/2026/07", "goods", 18),
            ("Event management services for district competitions", "NACB/T/2026/08", "services", 25),
            ("Consultancy: creative industry economic impact study", "NACB/T/2026/09", "consultancy", 30)]:
            Tender.objects.get_or_create(slug=ref.lower().replace("/", "-"), defaults={
                "title": title, "reference": ref, "category": cat, "status": "published",
                "summary": title + ".", "description": "<p>Bidders are invited to submit proposals in line with the tender document.</p>",
                "eligibility": "<ul><li>Registered with PPADB in the relevant code</li><li>Valid tax clearance certificate</li></ul>",
                "closing_date": now + timedelta(days=days), "briefing": "Compulsory briefing at NACB Head Office, 10:00"})

        u, created = User.objects.get_or_create(email="committee@nacb.test", defaults={
            "first_name": "Mpho", "last_name": "Kebonang", "role": User.COMMITTEE, "email_verified": True})
        if created:
            u.set_password(demo_password())
            u.save()

        call, made = GrantCall.objects.get_or_create(slug="arts-and-culture-grant-2026-round-1", defaults={
            "title": "Arts and Culture Grant 2026: Round 1", "reference": "ACG-2026-01", "instrument": "acg",
            "summary": "First 2026 funding round for projects in all art forms.", "description": "<p>Round 1 of 2026.</p>",
            "eligibility": "<ul><li>Verified register members</li></ul>", "min_amount": Decimal("5000"),
            "max_amount": Decimal("100000"), "total_budget": Decimal("250000"),
            "opens_at": now - timedelta(days=60), "closes_at": now - timedelta(days=5), "status": "closed"})
        if made:
            for i, (n, m) in enumerate([("Artistic merit", 30), ("Feasibility", 25), ("Budget", 20), ("Impact", 25)]):
                ScoringCriterion.objects.create(call=call, name=n, max_score=m, order=i)
            call.required_documents.set(DocumentType.objects.filter(code__in=["bank-letter", "quotations"]))
            people = [("Kabelo", "Tau", "music", "central", "Setswana folk recording", 45000),
                      ("Naledi", "Moremi", "dance", "north_west", "Maun youth dance residency", 60000),
                      ("Onalenna", "Pule", "painting", "south_east", "Murals for community clinics", 38000),
                      ("Tebogo", "Sechele", "basketry", "ngamiland", "Etsha basket weavers market access", 72000)]
            disc = list(Discipline.objects.all())
            for i, (fn, ln, dkey, district, title, amt) in enumerate(people):
                user, _ = User.objects.get_or_create(email=f"round1-{i}@nacb.test", defaults={
                    "first_name": fn, "last_name": ln, "role": User.ARTIST, "district": district if district != "ngamiland" else "north_west",
                    "email_verified": True})
                user.set_password(demo_password())
                user.save()
                p = user.profile
                d = next((x for x in disc if dkey in x.slug), disc[0])
                p.status, p.district, p.primary_discipline, p.citizenship = Profile.VERIFIED, user.district, d, "citizen"
                p.phone, p.town, p.gender = f"+2677100010{i}", "", "female" if i % 2 else "male"
                p.assign_registration_number()
                p.verified_at = now - timedelta(days=40)
                p.is_public, p.bio = True, BIOS[i]
                p.save()
                app = GrantApplication.objects.create(
                    call=call, applicant=user, profile=p, status=GrantApplication.SUBMITTED, project_title=title, category=d,
                    summary=title + ", a community-centred project.", description="Project description.", objectives="Objectives.",
                    district=user.district, start_date=now.date() + timedelta(days=30), end_date=now.date() + timedelta(days=200),
                    timeline="Q1 planning, Q2 delivery.", beneficiaries="Local artists and audiences.", expected_impact="Jobs and income.",
                    amount_requested=Decimal(amt), total_project_cost=Decimal(amt) * Decimal("1.3"), declaration=True,
                    submitted_at=now - timedelta(days=10 + i))
                BudgetItem.objects.create(application=app, category="production", description="Main costs", quantity=1, unit_cost=Decimal(amt))
        self.stdout.write(self.style.SUCCESS("Demo round, jobs, tenders and policy pages ready."))
