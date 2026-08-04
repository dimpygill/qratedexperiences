# Q-Rated Experiences — Website & Admin System

Full-stack site for a bespoke catering business: a public portfolio/inquiry site
plus a password-protected admin panel for running the business day-to-day.
Data lives entirely in your Airtable base (`qratedexperiences`).

## Stack
- **Backend:** Python 3 + Flask
- **Data:** Airtable (via `pyairtable`)
- **Frontend:** Server-rendered HTML/CSS/JS (Jinja2 templates, no build step)

## 1. Setup

```bash
cd curated-experiences
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

```
FLASK_SECRET_KEY=<any long random string>
AIRTABLE_API_KEY=<your Airtable Personal Access Token>
AIRTABLE_BASE_ID=appneouQhllGKaILG
ADMIN_USERNAME=<pick a username>
ADMIN_PASSWORD=<pick a strong password>
```

### Getting an Airtable API key
Airtable Personal Access Tokens are created at https://airtable.com/create/tokens.
Grant it `data.records:read`, `data.records:write`, and scope it to the
`qratedexperiences` base.

## 2. Run locally

```bash
python app.py
```

Visit `http://localhost:5000` for the public site, `http://localhost:5000/admin`
for the admin panel (log in with the credentials from your `.env`).

## 3. Data model (Airtable)

| Table | Purpose |
|---|---|
| **Events** | One row per event. Links to Clients, Dishes, EventStaffAssignments, Expenses. Cost/profit fields are auto-calculated (rollups + formula). |
| **Clients** | Contact info + booking history (linked Events). |
| **Dishes** | Reusable dish library — name, category, optional ingredients, photos. Link to any Event. |
| **Staff** | Team roster — role, phone, default pay type/rate. |
| **EventStaffAssignments** | Join table: who worked which event, their role there, and what they were actually paid (supports the shift from event/day pay to future salaried pay). |
| **Expenses** | Per-event cost line items (Decor / Grocery / Other), each with a cost and photo — this is how decor purchases are tracked, not as a standing inventory. |
| **Inquiries** | Leads from the public "Request a Quote" form. Convert to an Event in one click from the admin. |

Status pipeline on Events: **Planned → Confirmed → Completed** (also **Cancelled**).
Only **Completed** events appear on the public site, and public event pages never
show cost, profit, staff pay, or client contact info — only what you'd want a
prospective client to see.

## 4. Photo uploads

Photos are uploaded through the admin UI (event, dish, and expense forms) and
saved to `static/uploads/`, then attached to the corresponding Airtable record
by URL. **For this to work outside of local development, the app must be
deployed somewhere with a real public HTTPS URL** (Airtable fetches the file
from that URL to store it) — this won't work over `localhost`.

## 5. Deployment notes

- Set `debug=False` in `app.py` before deploying.
- Use a real WSGI server (e.g. `gunicorn app:app`) behind a reverse proxy.
- Make sure `static/uploads/` is on persistent storage (or swap in S3/Cloudinary
  later — the `save_uploaded_files()` function in `app.py` is the one place to change).
- Rotate `ADMIN_PASSWORD` and `FLASK_SECRET_KEY` from the example values.

## 6. Logo files

`static/img/` contains the logo, generated from the original mark you supplied:
- `logo-on-light.png` — used in the public nav and the admin login card (light backgrounds)
- `logo-on-dark.png` — used in the public footer and admin sidebar (dark backgrounds)
- `favicon-16.png` / `favicon-32.png` / `apple-touch-icon.png` — browser tab icon, cropped to just the "Q" mark
- `logo.png` / `logo-transparent.png` — originals, kept for reference if you want to regenerate any of the above

## 7. Project structure

```
app.py                 Routes (public + admin)
config.py               Airtable table/field name maps, choice lists
airtable_client.py       All Airtable reads/writes go through here
templates/public/        Public site pages
templates/admin/         Admin panel pages
static/css/main.css      Public site design system
static/css/admin.css     Admin panel styles
static/uploads/          Uploaded photos (served locally, attached to Airtable by URL)
```
