"""Lightweight English / Setswana interface strings for navigation and key public pages (NFR 2.5).
Long-form content is translated per page in the CMS (Page.body_tn)."""

STRINGS = {
    "home": ("Home", "Gae"),
    "about": ("About NACB", "Ka ga NACB"),
    "services": ("Services", "Ditirelo"),
    "grants": ("Grants & Funding", "Dithuso tsa Madi"),
    "events": ("Events & Programmes", "Ditiragalo le Mananeo"),
    "news": ("News & Media", "Dikgang"),
    "resources": ("Resources", "Ditlamelo"),
    "directory": ("Artist Directory", "Lenaane la Baitseanape"),
    "contact": ("Contact", "Ikgolaganye le rona"),
    "faqs": ("FAQs", "Dipotso"),
    "login": ("Sign in", "Tsena"),
    "signup": ("Register", "Ikwadise"),
    "dashboard": ("My dashboard", "Tsebe ya me"),
    "search": ("Search", "Batla"),
    "hero_title": ("Growing Botswana's creative economy", "Re godisa ikonomi ya botlhami mo Botswana"),
    "hero_lead": ("Botswana", "Botswana e"),
    "hero_verbs": ("sings,dances,paints,weaves,writes,performs,creates", "a opela,a bina,a penta,a loga,a kwala,a tshameka,a tlhama"),
    "hero_text": (
        "Register on the National Artist Register, apply for grants, join programmes and request support, all online.",
        "Ikwadise mo Lenaaneng la Bopegelo la Baitseanape, kopa dithuso, tsenela mananeo mme o kope tshegetso, tsotlhe mo inthaneteng.",
    ),
    "register_cta": ("Join the National Artist Register", "Ikwadise mo Lenaaneng la Baitseanape"),
    "grants_cta": ("View open grant calls", "Bona dikopo tsa dithuso tse di buletsweng"),
    "latest_news": ("Latest news", "Dikgang tsa bosheng"),
    "upcoming_events": ("Upcoming events", "Ditiragalo tse di tlang"),
    "open_calls": ("Open funding calls", "Dithuso tse di buletsweng"),
    "how_it_works": ("How it works", "Go dira jang"),
    "newsletter": ("Stay informed", "Nna o itse"),
    "subscribe": ("Subscribe", "Ikwadisetse"),
    "skip": ("Skip to main content", "Tlolela kwa diteng"),
    "language": ("Setswana", "English"),
}


def strings(lang):
    idx = 1 if lang == "tn" else 0
    return {k: v[idx] for k, v in STRINGS.items()}
