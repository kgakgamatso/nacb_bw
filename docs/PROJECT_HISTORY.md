# NACB Digital Platform: project history and handover

This file records what was asked for, what was built and decided, and how to continue, so the work can carry on
without the original chat. Started November 2026; this record was written on 18 November 2026.

No passwords, tokens or personal email addresses are kept in this file or anywhere in the repository (see "Secrets").

## Links

| What | Where |
|---|---|
| Live test site | https://nacb-platform.vercel.app |
| Code (public) | https://github.com/kgakgamatso/nacb_bw (branch `main`) |
| Hosting | Vercel project `nacb-platform` (team `kgakgamatso`) |
| Database | Neon Postgres, connected through Vercel (env var `DATABASE_URL`) |
| Developer credit (footer) | Cyberjaya Investments (Pty) Ltd, https://www.cyberjayainvest.com/ |

## What was asked for, in order

1. Build the National Arts Council of Botswana platform from the SRS v1.0 (Django). See README.md for the SRS coverage table.
2. Design feedback, applied throughout:
   - Be unique and natural, not "default AI CSS". No coloured accent lines on boxes. No eyebrow-plus-heading duplicates
     (e.g. "News & media" over "Latest news"). No long dashes anywhere in the site text.
   - Remove the "Dumela" welcome. Never animate the logo.
   - Add news, jobs, tenders, a calendar of events, a dashboard, and an A to Z numbered menu when signed in.
   - Privacy, cookies and data protection pages (cookie notice, rights requests, personal data download).
   - Close empty space and avoid long scrolling. Check mobile and tablet.
   - Add pictures of past events (shown only when real photos are uploaded in the CMS).
   - Use icons for the figures line (creatives, art forms, districts, grants). Illustrations and icon placeholders were rejected.
   - "Developed by Cyberjaya Investments (Pty) Ltd" in the footer, linked to their website.
   - Benchmark cyberjayainvest.com but never copy it; the NACB site must not look like a duplicate.
   - Be creative and futuristic, not only traditional arts.
   - Nav links must stay visible (not hidden under a "Menu" button), and different parts of the site should have different designs.
3. Grants process: after the closing date a committee sits, assesses and decides per application; a summary report is produced;
   winners are notified; grantees report continuously and are monitored.
4. Uploads: 5 MB maximum, executables blocked.
5. Capacity: 1,000+ simultaneous sign-ins (see docs/CAPACITY.md; a laptop test reached 650 of 1,000, production config documented).
6. Proper admin user management for all users (`/staff/users/`).
7. Partnerships, event sponsorship and CSR (`/partner/`).
8. Deploy to GitHub and Vercel with a test link.
9. Never push passwords to the repository.

## Current design ("Kalahari night", November 2026)

- Fonts: Syne (headings) and Manrope (text) from Google Fonts. CSP in `portal/middleware.py` allows them.
- Stylesheets: `static/css/nacb.css` (base) then `static/css/night.css` (theme, loaded after it). Bump the `?v=` numbers in
  `templates/base.html` whenever these change so browsers fetch the new file.
- Home page (`templates/portal/home.html`): night-sky hero with a generative basket-weave canvas (`static/js/loom.js`) that turns
  slowly and follows the mouse; live bar (grant closing soonest, next event, figures that count up); bento services grid;
  tabbed News / Events / Grants / Jobs / Tenders; patterned art-form cards; "Creativity of tomorrow" band; partners.
- Glowing cursor on desktop with a mouse only. Everything is still for visitors who prefer reduced motion.
- Navigation: below 1,180 px the links become a swipeable row of tabs (no Menu button).
- Each section has its own page-header design, chosen from the URL by the `section_theme` filter in
  `portal/templatetags/nacb.py`: grants sunset, events sky, news editorial, artists weave, jobs/tenders/resources blueprint grid,
  partner gold, endorsements green seal, gallery violet, data protection mint, everything else night sky.

## Secrets (never commit these)

- Demo account password: set `NACB_DEMO_PASSWORD` (Vercel, marked sensitive). Locally the first seed run writes one to
  `demo-credentials.local.txt`, which git ignores. The live demo accounts (`*@nacb.test`) use the Vercel value.
- `NACB_SECRET_KEY` is required on Vercel. `DATABASE_URL` comes from the Neon integration.
- One-time setup endpoint `/ops/setup/` is switched off. To use it again: set `NACB_OPS_TOKEN` (32+ characters) in Vercel,
  redeploy, POST with header `X-Ops-Token`, steps `migrate`, `cache`, `seed`, `check`, `rotate_demo`; then delete the variable and redeploy.
- Git history was rebuilt once to remove an earlier hard-coded password; commits use the GitHub noreply author.
- Before every push, check the staged diff contains no password, token or personal email.

## Continue working

```powershell
cd NACB
.venv\Scripts\python manage.py runserver
```

Checks (run from the NACB folder, all should end with "FAILED: none" / "server errors: none"):

```powershell
.venv\Scripts\python scripts\checks\e2e.py
```
```powershell
.venv\Scripts\python scripts\checks\partner_test.py
```
```powershell
.venv\Scripts\python scripts\checks\dashscan.py
```

Publish:

```powershell
git push origin main
```
```powershell
npx.cmd vercel deploy --prod --yes
```

## Open items

- SMS gateway contract, Botswana public holidays in working-day counts, Setswana translations of CMS pages,
  Omang verification API, payment gateway (SRS roadmap).
- Replace demo partner names with signed partners only; upload real event and artist photography in the CMS.
- Production hosting for 1,000+ sign-ins should use the documented server setup (docs/CAPACITY.md) rather than the free test tier.
