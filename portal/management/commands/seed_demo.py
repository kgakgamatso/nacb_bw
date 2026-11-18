"""Load reference data and demo content: `python manage.py seed_demo`.

Reference data (disciplines, document types, letter templates, FAQs, pages) is safe for production.
Demo users are created only with --demo-users. Their password comes from NACB_DEMO_PASSWORD (or a random one saved
to demo-credentials.local.txt, which git ignores). No password is stored in the code.
(development / test use only, never enable demo users in production)."""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from accounts.models import Discipline, Profile, User
from endorsements.models import LetterTemplate
from events.models import Event
from grants.models import DocumentType, GrantCall, ScoringCriterion
from portal.demo_credentials import demo_password
from portal.models import FAQ, LeadershipMember, NewsPost, Page, Resource


DISCIPLINES = {
    "performing": ["Theatre & Drama", "Dance", "Comedy", "Poetry & Spoken Word", "Traditional Dance"],
    "music": ["Contemporary Music", "Traditional Music", "Gospel Music", "Music Production"],
    "visual": ["Painting & Drawing", "Sculpture", "Photography", "Mixed Media"],
    "literary": ["Creative Writing", "Publishing", "Storytelling"],
    "film": ["Film & Television", "Animation", "Digital Content Creation", "Game Design & Interactive Media",
             "Digital & New Media Art", "Creative Technology (AR, VR and AI)"],
    "craft": ["Basketry", "Pottery & Ceramics", "Fashion Design", "Jewellery & Beadwork"],
    "heritage": ["Cultural Heritage & Folklore", "Indigenous Knowledge"],
}

DOCS = [
    ("Certified copy of Omang / passport", "certified-id", "individual", "Certified within the last 3 months"),
    ("CV / artist profile", "cv", "individual", "Your creative CV including past projects"),
    ("Company / society registration certificate", "registration-certificate", "organisation", "CIPA or Registrar of Societies certificate"),
    ("Organisation profile", "org-profile", "organisation", "Overview of the organisation and its track record"),
    ("Bank confirmation letter", "bank-letter", "both", "Stamped letter from your bank confirming account details"),
    ("Quotations (at least two)", "quotations", "both", "Quotations supporting the main budget items, combined into one file"),
    ("Reference letter", "reference", "both", "From a recognised arts practitioner, organisation or community leader"),
]

PAGES = [
    ("about", "About the National Arts Council of Botswana", "Ka ga Lekgotla la Botsweletsi la Botswana",
     "<p>The National Arts Council of Botswana (NACB) is a parastatal established under the <strong>National Arts Council of Botswana Act, 2020 (Act No. 10 of 2020)</strong>. It falls under the Ministry responsible for Youth, Gender, Sport and Culture.</p>"
     "<h2>Our mandate</h2><p>NACB develops, promotes and protects Botswana's creative and cultural sector through policy and legislation, industry facilitation, grants, partnerships, programmes and initiatives, with a strong emphasis on the commercialisation of the arts.</p>"
     "<h2>Vision</h2><p>A vibrant, sustainable and globally competitive creative economy that celebrates Botswana's identity.</p>"
     "<h2>Mission</h2><p>To nurture talent, grow creative enterprises and widen access to the arts for every Motswana.</p>", False),
    ("privacy", "Privacy notice", "", "<p>NACB collects personal information to administer the National Artist Register, grants, programmes and endorsements. We collect only what is necessary, store it securely in line with the Botswana Data Protection Act, restrict access to authorised staff and log every access to sensitive documents.</p><p>You can choose what appears in the public Artist Directory and may request a copy or correction of your data by contacting info@nacb.org.bw.</p>", True),
    ("accessibility", "Accessibility statement", "", "<p>This website aims to meet WCAG 2.1 Level AA. It can be navigated with a keyboard, works with screen readers and resizes for mobile phones. If you have difficulty using any part of the site, contact us and we will help.</p>", True),
    ("terms", "Terms of use", "", "<p>By using this platform you agree to provide accurate information. False information in registrations or applications may lead to disqualification.</p>", True),
]

FAQS = [
    ("registration", "Who can register on the National Artist Register?", "Any citizen or permanent resident of Botswana practising in any art form, as well as arts organisations, companies, associations, trusts and groups."),
    ("registration", "Is registration free?", "Yes. Registration on the National Artist Register is free of charge."),
    ("registration", "How long does verification take?", "NACB aims to verify complete registrations within 10 working days. You will receive an email and SMS once verified."),
    ("registration", "I don't have internet access. Can I still register?", "Yes. Visit NACB headquarters or your district office, where an officer will capture your registration for you."),
    ("grants", "Do I need to be registered to apply for a grant?", "Yes. Most grant calls require a verified National Artist Register profile. Register early so that verification is complete before the deadline."),
    ("grants", "Can I save my application and finish later?", "Yes. Your application is saved each time you click Save, and you can continue at any time before the closing date."),
    ("grants", "What documents do I need?", "Usually a certified ID or registration certificate, CV or organisation profile, bank confirmation letter, quotations and a reference letter. Each call lists its exact requirements."),
    ("endorsements", "How long does an endorsement letter take?", "The target turnaround is 10 working days from submission."),
    ("account", "I forgot my password", "Use the 'Forgot your password?' link on the sign-in page. A reset link will be emailed to you."),
    ("general", "Where is NACB located?", "NACB head office is in Gaborone. Services are also available through district offices across Botswana."),
]


class Command(BaseCommand):
    help = "Seed reference data and demo content"

    def add_arguments(self, parser):
        parser.add_argument("--demo-users", action="store_true", help="Create demo staff and artist accounts")

    def handle(self, *args, **opts):
        now = timezone.now()
        for group, names in DISCIPLINES.items():
            for n in names:
                Discipline.objects.get_or_create(slug=slugify(n), defaults={"name": n, "group": group})
        for name, code, applies, desc in DOCS:
            DocumentType.objects.get_or_create(code=code, defaults={"name": name, "applies_to": applies, "description": desc})
        for slug, title, title_tn, body, footer in PAGES:
            Page.objects.get_or_create(slug=slug, defaults={"title": title, "title_tn": title_tn, "body": body,
                                                            "status": "published", "show_in_footer": footer})
        for i, (cat, q, a) in enumerate(FAQS):
            FAQ.objects.get_or_create(question=q, defaults={"answer": a, "category": cat, "order": i})
        LetterTemplate.objects.get_or_create(name="General letter of support", defaults={
            "signatory_name": "Chief Executive Officer", "signatory_title": "Chief Executive Officer",
            "body": "Dear Sir/Madam,\n\nRE: LETTER OF SUPPORT: {name}\n\n"
                    "The National Arts Council of Botswana (NACB) confirms that {name} is registered on the National Artist "
                    "Register under registration number {registration_number}, practising in {discipline}.\n\n"
                    "NACB supports {name}'s participation in {event}{event_date_text} as this opportunity will contribute to "
                    "the development of their practice and to the promotion of Botswana's creative sector.\n\n"
                    "We kindly request that you extend every assistance to the applicant.\n\nPurpose: {purpose}".replace(
                        "{event_date_text}", " ({event_date}, {destination})"),
        })
        for i, (name, pos, grp) in enumerate([
            ("Board Chairperson", "Chairperson", "board"), ("Deputy Chairperson", "Deputy Chairperson", "board"),
            ("Chief Executive Officer", "Chief Executive Officer", "management"),
            ("Director, Creative & Cultural Sector Development", "Director", "management"),
            ("Director, Corporate Services", "Director", "management")]):
            LeadershipMember.objects.get_or_create(name=name, defaults={"position": pos, "group": grp, "order": i})

        call, _ = GrantCall.objects.get_or_create(slug="arts-and-culture-grant-2026-27", defaults={
            "title": "Arts and Culture Grant 2026/27", "reference": "ACG-2026-02", "instrument": "acg",
            "summary": "Funding for projects that create, produce, showcase or commercialise Botswana art across all disciplines.",
            "description": "<p>The Arts and Culture Grant supports individual artists and arts organisations to develop high-quality projects with clear audience, economic and community impact.</p><p>Priority is given to projects that create jobs, reach audiences outside Gaborone, and involve youth, women and people with disabilities.</p>",
            "eligibility": "<ul><li>Verified member of the National Artist Register</li><li>Individuals must be citizens of Botswana aged 18 or older</li><li>Organisations must be registered in Botswana</li><li>Projects must be completed within 12 months</li><li>Previous NACB grant recipients must have submitted their final reports</li></ul>",
            "min_amount": Decimal("5000"), "max_amount": Decimal("150000"), "total_budget": Decimal("5000000"),
            "opens_at": now - timedelta(days=10), "closes_at": now + timedelta(days=35), "status": "published",
        })
        if not call.required_documents.exists():
            call.required_documents.set(DocumentType.objects.all())
            for i, (n, d, m) in enumerate([
                ("Artistic merit & originality", "Quality, creativity and originality of the work", 25),
                ("Feasibility & planning", "Realistic plan, timeline and capacity to deliver", 20),
                ("Budget & value for money", "Clear, justified budget with co-funding where possible", 20),
                ("Impact & commercial potential", "Audience reach, jobs, income and sector development", 25),
                ("Inclusion", "Youth, women, people with disabilities and rural reach", 10)]):
                ScoringCriterion.objects.create(call=call, name=n, description=d, max_score=m, order=i)
        GrantCall.objects.get_or_create(slug="creative-arts-fund-pilot", defaults={
            "title": "Botswana Creative Arts Fund: Pilot Window", "reference": "BCAF-2027-01", "instrument": "bcaf",
            "summary": "Growth funding for creative enterprises ready to scale production, distribution and exports.",
            "description": "<p>The pilot window of the Botswana Creative Arts Fund will support established creative businesses.</p>",
            "eligibility": "<ul><li>Registered organisations with at least 2 years' trading</li></ul>",
            "applicant_types": "organisation", "min_amount": Decimal("100000"), "max_amount": Decimal("500000"),
            "opens_at": now + timedelta(days=60), "closes_at": now + timedelta(days=120), "status": "published",
        })

        events = [
            ("National Arts Festival: Kweneng District Round", "festival", "kweneng", "Molepolole Kgotla Grounds", 20, 150, True),
            ("Grant Writing Workshop for Creatives", "workshop", "gaborone", "NACB Boardroom, Fairgrounds", 7, 30, False),
            ("Music Business & Copyright Masterclass", "training", "francistown", "Francistown Civic Centre", 14, 60, False),
            ("Contemporary Visual Art Exhibition", "exhibition", "gaborone", "National Museum & Art Gallery", 28, None, False),
            ("Ward Traditional Dance Competition: Central", "competition", "central", "Serowe Community Hall", 40, 25, True),
        ]
        for title, typ, district, venue, days, cap, comp in events:
            start = (now + timedelta(days=days)).replace(hour=9, minute=0, second=0, microsecond=0)
            Event.objects.get_or_create(slug=slugify(title), defaults={
                "title": title, "event_type": typ, "district": district, "venue": venue,
                "summary": f"{title}. Open to creatives across Botswana.",
                "description": "<p>Join fellow creatives for this NACB programme. Bring your ideas, questions and portfolio.</p>",
                "starts_at": start, "ends_at": start + timedelta(hours=7), "status": "published", "capacity": cap,
                "is_competition": comp, "registration_closes": start - timedelta(days=1),
                "related_call": call if typ == "workshop" else None,
            })

        posts = [
            ("Arts and Culture Grant 2026/27 now open", "opportunity", True, call),
            ("National Artist Register goes online", "announcement", False, None),
            ("Botswana creatives shine at regional festival", "feature", False, None),
        ]
        for i, (title, cat, feat, rc) in enumerate(posts):
            NewsPost.objects.get_or_create(slug=slugify(title), defaults={
                "title": title, "category": cat, "featured": feat, "related_call": rc, "status": "published",
                "publish_at": now - timedelta(days=i * 6),
                "summary": f"{title}. Read more about what this means for Botswana's creative sector.",
                "body": "<p>The National Arts Council of Botswana continues to bring its services online so that creatives in every district can access registration, funding and programmes from their phones.</p>",
            })
        Resource.objects.get_or_create(title="National Arts Council of Botswana Act, 2020", defaults={
            "category": "policy", "external_url": "https://www.gov.bw", "year": 2020, "status": "published",
            "description": "The Act establishing the National Arts Council of Botswana."})
        Resource.objects.get_or_create(title="Arts and Culture Grant guidelines 2026/27", defaults={
            "category": "guidelines", "external_url": "https://www.gov.bw", "year": 2026, "status": "published"})

        if opts["demo_users"]:
            self._demo_users()
        self.stdout.write(self.style.SUCCESS("Seed complete."))

    def _user(self, email, first, last, role, district="", **extra):
        u, created = User.objects.get_or_create(email=email, defaults={
            "first_name": first, "last_name": last, "role": role, "district": district, "email_verified": True, **extra})
        if created:
            u.set_password(demo_password())
            u.save()
        return u

    def _demo_users(self):
        self._user("admin@nacb.test", "System", "Administrator", User.SYSADMIN, is_staff=True, is_superuser=True)
        self._user("officer@nacb.test", "Kagiso", "Molefe", User.OFFICER)
        self._user("approver@nacb.test", "Neo", "Seretse", User.APPROVER)
        self._user("district@nacb.test", "Tumelo", "Kgosi", User.DISTRICT_OFFICER, "kweneng")
        music = Discipline.objects.get(slug=slugify("Contemporary Music"))
        art = self._user("artist@nacb.test", "Lesego", "Mothibi", User.ARTIST, "kweneng", phone="+26771000001")
        p = art.profile
        if not p.registration_number:
            p.id_type, p.national_id, p.gender, p.citizenship = "omang", "123456789", "female", "citizen"
            p.date_of_birth = timezone.now().date().replace(year=1996)
            p.district, p.town, p.phone, p.primary_discipline = "kweneng", "Molepolole", "+26771000001", music
            p.experience_level, p.years_experience = "developing", 6
            p.bio = "Afro-soul singer-songwriter blending Setswana folk melodies with contemporary sound."
            p.status, p.is_public, p.consent_data_processing = Profile.VERIFIED, True, True
            p.id_document.name = "registry/demo/omang.pdf"
            p.assign_registration_number()
            p.verified_at = timezone.now()
            p.save()
            p.disciplines.add(music)
        self._user("newartist@nacb.test", "Thato", "Ramotswa", User.ARTIST, "gaborone")
        org = self._user("org@nacb.test", "Boitumelo", "Dikgang", User.ORGANISATION, "gaborone")
        org.profile.org_name, org.profile.account_type = "Kgalagadi Arts Collective", Profile.ORGANISATION
        org.profile.save()
        self.stdout.write("Demo users created (see seed_demo.py for the demo password).")
