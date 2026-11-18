"""Demo past events with (empty) photo galleries (development only).

    python manage.py seed_past_events

Each past event gets a published gallery album. The site shows an icon placeholder until NACB uploads real
event photography in the CMS (Gallery albums > images, and the Event image)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Event
from portal.models import GalleryAlbum

EVENTS = [
    ("National Arts Festival 2025: National Finals", "festival", "gaborone", "Gaborone International Convention Centre", 300,
     "Winners from every district competed in music, dance, drama and poetry at the national finals."),
    ("Contemporary Art Exhibition: New Voices", "exhibition", "gaborone", "National Museum and Art Gallery", 220,
     "Twenty emerging painters, sculptors and photographers showed new work, with sales open to the public."),
    ("Traditional Dance Competition: Central District", "competition", "central", "Serowe Kgotla", 160,
     "Ward winners from across the Central district competed in traditional dance."),
    ("Digital Creators Bootcamp", "training", "francistown", "Francistown Innovation Space", 75,
     "A week of animation, game design and digital marketing training for young creatives."),
]


class Command(BaseCommand):
    help = "Create demo past events with photo galleries ready for real pictures"

    def handle(self, *args, **opts):
        now = timezone.now()
        for title, typ, district, venue, days_ago, summary in EVENTS:
            slug = title.lower().replace(":", "").replace(" ", "-")[:50]
            start = (now - timedelta(days=days_ago)).replace(hour=10, minute=0, second=0, microsecond=0)
            ev, _ = Event.objects.get_or_create(slug=slug, defaults={
                "title": title, "event_type": typ, "district": district, "venue": venue, "summary": summary,
                "description": f"<p>{summary}</p>", "starts_at": start, "ends_at": start + timedelta(hours=8),
                "status": "published", "registration_required": False})
            GalleryAlbum.objects.get_or_create(slug=slug, defaults={
                "title": title, "description": summary, "event": ev, "status": "published", "publish_at": start + timedelta(days=2)})
        self.stdout.write(self.style.SUCCESS(f"{len(EVENTS)} past events with galleries ready for photos."))
