# NACB Digital Platform

Website and online services for the National Arts Council of Botswana, built from SRS v1.0 (November 2026).
Stack: Python 3.13, Django 5.2, server-rendered HTML with a small JavaScript file and no CDN dependencies. Development uses SQLite; production should use PostgreSQL.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createcachetable
.venv\Scripts\python manage.py seed_demo --demo-users
.venv\Scripts\python manage.py seed_demo_round
.venv\Scripts\python manage.py seed_past_events
.venv\Scripts\python manage.py seed_partnerships
.venv\Scripts\python manage.py runserver
```

Open http://127.0.0.1:8000. Emails and SMS are printed to the console in development.

Demo accounts (development only). No password is stored in the code: set `NACB_DEMO_PASSWORD`, or the first seed run generates one and saves it to `demo-credentials.local.txt` (ignored by git):

| Email | Role |
|---|---|
| admin@nacb.test | System administrator (also /admin CMS) |
| officer@nacb.test | NACB officer |
| approver@nacb.test | Approver / manager |
| district@nacb.test | District officer (Kweneng) |
| artist@nacb.test | Verified individual artist |
| newartist@nacb.test | New artist (incomplete registration) |
| org@nacb.test | Organisation |
| committee@nacb.test | Assessment committee member |

## SRS coverage

| SRS | Where |
|---|---|
| FR-1 Public site, CMS, media, documents, search, newsletter, sharing | `portal/`, Django admin at `/admin/` (pages, news, resources, galleries, FAQs, leadership; draft, scheduled publishing, archive) |
| FR-2 Accounts, strong passwords, MFA (TOTP), recovery, RBAC | `accounts/` (login lockout, email verification, `core/permissions.py`) |
| FR-3 Register, portfolio, search/filter/export, bulk import, data quality, public directory with privacy controls | `accounts/`, `backoffice/` (`/staff/registry/…`), `/directory/` |
| FR-4 Grant calls, 5-step application with drafts, documents, eligibility checks, status tracking, assignment, scoring, two-level approval, notifications, audit trail, multiple instruments | `grants/` (calls are configured in admin: criteria, documents, approval levels) |
| FR-5 Events calendar, registration, capacity, waitlist, attendance, `.ics` export, links to news and grants | `events/` |
| FR-6 Endorsement requests (verified members only), 10-working-day target, letter templates, printable letters with a public verification code | `endorsements/` |
| FR-7 Artist dashboard and staff dashboard with district/discipline filters | `portal/views.dashboard`, `backoffice/views.dashboard` |
| FR-8 Email and SMS notifications, contact form and support inbox, targeted communications | `portal/services.py`, `/staff/messages/`, `/staff/communications/` |
| FR-9 Admin, CSV reports and exports, immutable audit log, roles | `/staff/reports/`, `/staff/audit/`, `/staff/users/` |
| NFR security | Private documents stored outside the web root and served only after a permission check (staff access is logged); upload type, size and file-signature checks; CSP and HSTS; secure cookies; CSRF protection; district-scoped data for district officers |
| NFR usability and accessibility | Mobile-first CSS, skip link, labelled fields, visible focus, progress indicators, draft autosave on the device, English/Setswana switch |

## Added after review (Nov 2026)

| Request | What was built |
|---|---|
| Committee assessment after a call closes | `grants/committee.py`. A sitting can only be held after the closing date. Members score each application, and the chair or secretary records a decision per application (fund / do not fund / defer, with amount and conditions). The sitting is concluded with minutes. |
| Summary report | Printable report with signature lines, plus a CSV, at `/grants/committee/<id>/report/` |
| Winners informed | "Publish results" notifies every applicant by email, SMS and in-app message, and opens a grant agreement for each winner |
| Follow-up and monitoring | Grantees report continuously (`/grants/my-grant/<ref>/`). Officers review reports, record monitoring visits and set each grant's health. The daily `send_report_reminders` job reminds grantees and flags overdue grants as at risk. |
| Jobs and tenders | `/jobs/` and `/tenders/`, managed in the CMS |
| Privacy, cookies, data protection | Cookie notice (essential cookies only), cookie and privacy pages, `/data-protection/` with a rights-request form (30-day reply) and a personal data download |
| Admin user management | `/staff/users/`: every account, search and filters, create, edit role and district, deactivate (ends all sessions), password-reset link, MFA reset, lockout release, sign-in history, bulk actions, CSV |
| Uploads | 5 MB hard limit. `.exe`, scripts and double extensions are blocked, and file content is checked so renamed programs are caught. |
| 1,000+ sign-ins | Shared cache and sessions, server configs and a load test. See `docs/CAPACITY.md`. |
| Design | Flat, calm design: no accent lines, no shadows or animation, serif headings, one heading per section, numbered A–Z menu when signed in (collapses on phones), original illustrations. Checked at phone (375 px), tablet (768 px) and desktop widths. |

**Partnerships, sponsorship and CSR** (`partnerships/`, page `/partner/`): ways to partner, sponsorship packages per event (with a "Sponsor this event" box on event pages), CSR programmes with funding progress, an enquiry form that alerts staff, and a staff screen to track leads (`/partner/manage/`). Partners, packages and programmes are edited in the CMS. Demo partner names are placeholders; list only organisations with a signed agreement.

Where no real photo has been uploaded yet (news, artists, events, galleries, CSR programmes), the site shows an icon from the NACB icon set. Upload real photography in the CMS and it replaces the icon automatically.

Schedule `python manage.py send_report_reminders` to run daily (Windows Task Scheduler or cron).

## Production checklist

- Set the environment variables listed in `.env.example`, with `NACB_DEBUG=false` and `NACB_REQUIRE_STAFF_MFA=true`.
- Set `NACB_REDIS_URL` (or run `createcachetable`) and use PostgreSQL with encryption at rest and nightly backups of both the database and `PRIVATE_MEDIA_ROOT`.
- Run `collectstatic` and serve `/static/` and `/media/` from the web server. Never serve `private_media`.
- Put the site behind TLS with a reverse proxy (nginx), and run gunicorn or waitress.
- Run `seed_demo` **without** `--demo-users` to load reference data only.
- Still to do: an SMS gateway contract, Botswana public holidays in the working-day calculation, Setswana translations for CMS pages, Omang verification once a national API is available, and a payment gateway (in the SRS roadmap).
