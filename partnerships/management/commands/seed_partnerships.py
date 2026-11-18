"""Demo partnership content (development only): placeholder partners, sponsorship packages and CSR programmes.

    python manage.py seed_partnerships

Partner names are deliberately generic placeholders. NACB replaces them with real partners (and their approved
logos) in the CMS; never list an organisation as a partner without a signed agreement."""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Event
from partnerships.models import CSRProgramme, Partner, SponsorshipPackage

PARTNERS = [
    ("Corporate partner", "corporate", True), ("Development partner", "development", True),
    ("Media partner", "media", True), ("Government partner", "government", True),
    ("Education partner", "education", False), ("Community partner", "community", False),
]

GENERAL = [
    ("inkind", None, "Your venue, transport, equipment, printing or airtime\nRecognition in event programmes and on this website\nThank-you letter for your records"),
    ("prize", Decimal("10000"), "Named prize at a competition of your choice\nPresent the prize on stage\nPhotos with the winners for your channels"),
]

EVENT_PACKAGES = [
    ("headline", Decimal("150000"), 1, "Event named with your brand\nLogo on stage, banners and tickets\nSpeaking slot at the opening\nTwenty guest passes\nImpact report after the event"),
    ("gold", Decimal("75000"), 2, "Logo on stage screen and banners\nBrand activation space at the venue\nTen guest passes\nSocial media mentions"),
    ("silver", Decimal("30000"), 4, "Logo in the programme and on the website\nFive guest passes\nThank-you mention from the stage"),
]

PROGRAMMES = [
    ("Instruments for village schools", "schools", "central", Decimal("180000"), Decimal("62000"), 1200,
     "Put marimbas, drums and guitars into 20 primary schools in the Central district, with training for music teachers.",
     "P5,000: a set of hand drums for one school\nP15,000: marimbas for one school\nP25,000: teacher training for one cluster"),
    ("Youth arts academy holiday camps", "youth", "", Decimal("250000"), Decimal("140000"), 400,
     "School-holiday camps in dance, drama, visual art and digital media for young people aged 13 to 19 in five districts.",
     "P2,500: one young person for a full camp\nP20,000: tutors for one camp week\nP50,000: a camp in a new district"),
    ("Etsha weavers market access", "livelihoods", "north_west", Decimal("120000"), Decimal("18000"), 80,
     "Help basket weavers from the Etsha villages reach tourist and export markets with product photography, packaging and an online shop.",
     "P3,000: product photography for one weaver\nP12,000: packaging design and stock\nP30,000: an online shop and training"),
    ("Accessible arts for everyone", "inclusion", "", Decimal("90000"), Decimal("0"), 300,
     "Sign language interpreting, audio description and ramps at NACB festivals, so people with disabilities can take part fully.",
     "P4,000: sign language interpreting for one festival day\nP10,000: portable ramps for one venue"),
    ("Digital creators fund", "digital", "", Decimal("300000"), Decimal("95000"), 60,
     "Laptops, software and mentoring for young animators, game designers and digital artists building their first portfolios.",
     "P12,000: a laptop and software for one creator\nP6,000: six months of mentoring"),
]


class Command(BaseCommand):
    help = "Seed placeholder partners, sponsorship packages and CSR programmes"

    def handle(self, *args, **opts):
        for i, (name, typ, featured) in enumerate(PARTNERS):
            Partner.objects.get_or_create(name=name, defaults={
                "partner_type": typ, "featured": featured, "order": i,
                "description": "Placeholder. Replace with a real partner and its approved logo in the CMS."})
        for level, amount, benefits in GENERAL:
            SponsorshipPackage.objects.get_or_create(event=None, level=level, defaults={"amount": amount, "benefits": benefits, "slots": 10})
        upcoming = Event.objects.filter(status="published", ends_at__gte=timezone.now(), event_type__in=["festival", "competition", "exhibition"])
        for ev in upcoming:
            for level, amount, slots, benefits in EVENT_PACKAGES:
                if ev.event_type != "festival" and level == "headline":
                    continue
                SponsorshipPackage.objects.get_or_create(event=ev, level=level, defaults={
                    "amount": amount if ev.event_type == "festival" else amount / 3, "slots": slots, "benefits": benefits})
        for title, theme, district, target, raised, people, summary, items in PROGRAMMES:
            CSRProgramme.objects.get_or_create(slug=title.lower().replace(" ", "-"), defaults={
                "title": title, "theme": theme, "district": district, "target_amount": target, "raised_amount": raised,
                "beneficiaries": people, "summary": summary, "description": f"<p>{summary}</p><p>Partners receive quarterly "
                "progress updates, photos and a final impact report suitable for annual and sustainability reports.</p>",
                "what_funds_buy": items})
        self.stdout.write(self.style.SUCCESS("Partners, packages and CSR programmes ready."))
