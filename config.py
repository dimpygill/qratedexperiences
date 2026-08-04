import os
from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-change-me")
    AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appneouQhllGKaILG")

    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

    MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300 MB upload limit (raised to allow video)
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    ALLOWED_EXTENSIONS = {
        "png", "jpg", "jpeg", "gif", "webp",
        "mp4", "mov", "webm", "avi", "mkv",
    }
    VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "avi", "mkv"}


# ---- Table IDs (from the live q-rated-experiences base) ----
TABLES = {
    "events": "tblSINTptYKGpkEtw",
    "dishes": "tblwWe3zfYOhfmNDm",
    "staff": "tblCnYogoqfoW958P",
    "inquiries": "tblmq9nwqSuE3i0IT",
    "clients": "tblYTDdfq66KeuVHk",
    "assignments": "tbl8jBws7FDtcPExQ",
    "expenses": "tblS7bo6mgc4lg99h",
}

# ---- Field NAME map (the Airtable REST API keys fields by name by default) ----
# friendly_key -> actual Airtable field name. Kept as a mapping (not a hardcoded
# literal) so a rename in Airtable only needs a one-line change here.
FIELDS = {
    "events": {
        "name": "name",
        "type": "Type",
        "theme": "Theme",
        "date": "Date",
        "guests": "Guests",
        "status": "Status",
        "charged": "charged",
        "notes": "notes",
        "photos": "photos",
        "client_link": "client_link",
        "dishes_link": "dishes_link",
        "staff_assignments_link": "staff_assignments_link",
        "expenses_link": "expenses_link",
        "manpower_cost_auto": "manpower_cost_auto",
        "expenses_total_auto": "expenses_total_auto",
        "total_cost": "total_cost",
        "profit": "profit",
    },
    "dishes": {
        "name": "name",
        "category": "category",
        "cost": "cost",
        "events_link": "Events",
        "photos": "photos",
        "ingredients": "ingredients",
    },
    "staff": {
        "name": "name",
        "role": "role",
        "phone": "phone",
        "pay_type": "pay_type",
        "rate": "rate",
        "notes": "notes",
        "assignments_link": "EventStaffAssignments",
    },
    "inquiries": {
        "name": "name",
        "email": "email",
        "phone": "phone",
        "event_date": "event_date",
        "event_type": "event_type",
        "guests": "guests",
        "message": "message",
        "status": "status",
        "received_at": "received_at",
    },
    "clients": {
        "name": "name",
        "phone": "phone",
        "email": "email",
        "notes": "notes",
        "events_link": "Events",
    },
    "assignments": {
        "label": "label",
        "role_on_event": "role_on_event",
        "pay_type_used": "pay_type_used",
        "amount_paid": "amount_paid",
        "notes": "notes",
        "event_link": "Events",
        "staff_link": "staff_member",
    },
    "expenses": {
        "item_name": "item_name",
        "type": "type",
        "cost": "cost",
        "photo": "photo",
        "notes": "notes",
        "event_link": "Events",
    },
}

# NOTE: these mirror the ACTUAL singleSelect options already saved in Airtable.
# Do not edit without also updating the field in Airtable (or vice versa).
EVENT_STATUS_CHOICES = ["Planned", "Confirmed", "Completed", "Cancelled"]
EVENT_TYPE_CHOICES = ["Wedding", "Corporate", "Birthday", "Private Gathering", "Other"]
STAFF_ROLE_CHOICES = ["Head Chef", "Chef", "Helper", "Server", "Coordinator"]
PAY_TYPE_CHOICES = ["Per Event", "Per Day", "Monthly Salary"]
EXPENSE_TYPE_CHOICES = ["Decor", "Grocery", "Other"]
DISH_CATEGORY_CHOICES = ["Starter", "Main", "Dessert", "Beverage"]
INQUIRY_STATUS_CHOICES = ["New", "Contacted", "Quoted", "Confirmed", "Closed"]

# Public-facing statuses that count as "published, showcase-worthy" on the public site
PUBLIC_EVENT_STATUSES = ["Completed"]
