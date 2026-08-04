import os
import uuid
from functools import wraps
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, jsonify
)
from werkzeug.utils import secure_filename

from config import (
    Config, EVENT_STATUS_CHOICES, EVENT_TYPE_CHOICES, STAFF_ROLE_CHOICES,
    PAY_TYPE_CHOICES, EXPENSE_TYPE_CHOICES, DISH_CATEGORY_CHOICES,
    INQUIRY_STATUS_CHOICES,
)
import airtable_client as db

app = Flask(__name__)
app.config.from_object(Config)
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def save_uploaded_files(file_list):
    """Save uploaded files to static/uploads and return public URLs usable
    as Airtable attachment sources (Airtable needs a fetchable https URL).
    In production this folder must be served over https for Airtable to
    fetch it when we attach by URL."""
    saved_urls = []
    for f in file_list:
        if f and f.filename and allowed_file(f.filename):
            ext = f.filename.rsplit(".", 1)[1].lower()
            unique_name = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(Config.UPLOAD_FOLDER, unique_name)
            f.save(path)
            saved_urls.append(url_for("static", filename=f"uploads/{unique_name}", _external=True))
    return saved_urls


def to_attachments(urls):
    return [{"url": u} for u in urls]


@app.template_filter("currency")
def currency_filter(value):
    if value is None:
        return "$0"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


@app.template_filter("first_photo")
def first_photo_filter(photos):
    if photos and isinstance(photos, list) and len(photos) > 0:
        for p in photos:
            url = p.get("url")
            if url and not is_video_url(url):
                return url
    return None


def is_video_url(url):
    if not url:
        return False
    ext = url.rsplit(".", 1)[-1].lower().split("?")[0]
    return ext in Config.VIDEO_EXTENSIONS


@app.template_filter("is_video")
def is_video_filter(url):
    return is_video_url(url)


# =======================================================================
# PUBLIC SITE
# =======================================================================

@app.route("/")
def public_home():
    events = db.get_public_events()
    featured = events[:6]
    return render_template("public/home.html", featured=featured)


@app.route("/gallery")
def public_gallery():
    events = db.get_public_events()
    event_type_filter = request.args.get("type")
    if event_type_filter:
        events = [e for e in events if e.get("type") == event_type_filter]
    return render_template(
        "public/gallery.html",
        events=events,
        event_types=EVENT_TYPE_CHOICES,
        active_filter=event_type_filter,
    )


@app.route("/events/<event_id>")
def public_event_detail(event_id):
    event = db.get_event_with_relations(event_id)
    if event is None or event.get("status") != "Completed":
        return render_template("public/404.html"), 404
    return render_template("public/event_detail.html", event=event)


@app.route("/inquire", methods=["GET", "POST"])
def public_inquire():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "event_type": request.form.get("event_type", "").strip(),
            "guests": int(request.form["guests"]) if request.form.get("guests") else None,
            "message": request.form.get("message", "").strip(),
            "status": "New",
            "received_at": date.today().isoformat(),
        }
        event_date = request.form.get("event_date")
        if event_date:
            data["event_date"] = event_date

        if not data["name"] or not data["email"]:
            flash("Please provide at least your name and email.", "error")
            return render_template("public/inquire.html", event_types=EVENT_TYPE_CHOICES, form=data)

        db.create_record_friendly("inquiries", data)
        flash("Thank you! We've received your inquiry and will be in touch soon.", "success")
        return redirect(url_for("public_inquire"))

    return render_template("public/inquire.html", event_types=EVENT_TYPE_CHOICES, form={})


@app.route("/about")
def public_about():
    return render_template("public/about.html")


# =======================================================================
# ADMIN AUTH
# =======================================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            session["is_admin"] = True
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        flash("Invalid credentials.", "error")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("public_home"))


# =======================================================================
# ADMIN DASHBOARD
# =======================================================================

@app.route("/admin")
@login_required
def admin_dashboard():
    stats = db.get_dashboard_stats()
    recent_inquiries = sorted(
        db.list_records_friendly("inquiries"),
        key=lambda i: i.get("received_at") or "",
        reverse=True,
    )[:5]
    upcoming_events = [
        e for e in db.get_all_events_sorted() if e.get("status") == "Confirmed"
    ][:5]
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_inquiries=recent_inquiries,
        upcoming_events=upcoming_events,
    )


# ---------------------------------------------------------------------
# ADMIN: EVENTS
# ---------------------------------------------------------------------

@app.route("/admin/events")
@login_required
def admin_events_list():
    events = db.get_all_events_sorted()
    status_filter = request.args.get("status")
    if status_filter:
        events = [e for e in events if e.get("status") == status_filter]
    return render_template(
        "admin/events_list.html", events=events, statuses=EVENT_STATUS_CHOICES, active_filter=status_filter
    )


@app.route("/admin/events/new", methods=["GET", "POST"])
@login_required
def admin_event_new():
    clients = db.list_records_friendly("clients")
    if request.method == "POST":
        data = _parse_event_form(request.form)
        client_id = request.form.get("client_id")
        if client_id:
            data["client_link"] = [client_id]
        event = db.create_record_friendly("events", data)

        photos = request.files.getlist("photos")
        urls = save_uploaded_files(photos)
        if urls:
            db.update_record_friendly("events", event["id"], {"photos": to_attachments(urls)})

        flash("Event created.", "success")
        return redirect(url_for("admin_event_detail", event_id=event["id"]))

    return render_template(
        "admin/event_form.html",
        event=None,
        clients=clients,
        statuses=EVENT_STATUS_CHOICES,
        types=EVENT_TYPE_CHOICES,
    )


@app.route("/admin/events/<event_id>", methods=["GET"])
@login_required
def admin_event_detail(event_id):
    event = db.get_event_with_relations(event_id)
    if event is None:
        flash("Event not found.", "error")
        return redirect(url_for("admin_events_list"))
    all_dishes = db.list_records_friendly("dishes")
    all_staff = db.list_records_friendly("staff")
    return render_template(
        "admin/event_detail.html",
        event=event,
        all_dishes=all_dishes,
        all_staff=all_staff,
        pay_types=PAY_TYPE_CHOICES,
        expense_types=EXPENSE_TYPE_CHOICES,
    )


@app.route("/admin/events/<event_id>/edit", methods=["GET", "POST"])
@login_required
def admin_event_edit(event_id):
    event = db.get_record_friendly("events", event_id)
    if event is None:
        flash("Event not found.", "error")
        return redirect(url_for("admin_events_list"))
    clients = db.list_records_friendly("clients")

    if request.method == "POST":
        data = _parse_event_form(request.form)
        client_id = request.form.get("client_id")
        data["client_link"] = [client_id] if client_id else []
        db.update_record_friendly("events", event_id, data)

        photos = request.files.getlist("photos")
        urls = save_uploaded_files(photos)
        if urls:
            existing = event.get("photos") or []
            db.update_record_friendly(
                "events", event_id, {"photos": existing + to_attachments(urls)}
            )

        flash("Event updated.", "success")
        return redirect(url_for("admin_event_detail", event_id=event_id))

    current_client_ids = event.get("client_link") or []
    return render_template(
        "admin/event_form.html",
        event=event,
        clients=clients,
        current_client_id=current_client_ids[0] if current_client_ids else None,
        statuses=EVENT_STATUS_CHOICES,
        types=EVENT_TYPE_CHOICES,
    )


@app.route("/admin/events/<event_id>/delete", methods=["POST"])
@login_required
def admin_event_delete(event_id):
    db.delete_record_friendly("events", event_id)
    flash("Event deleted.", "success")
    return redirect(url_for("admin_events_list"))


def _parse_event_form(form):
    data = {
        "name": form.get("name", "").strip(),
        "type": form.get("type") or None,
        "theme": form.get("theme", "").strip(),
        "date": form.get("date") or None,
        "guests": int(form["guests"]) if form.get("guests") else None,
        "status": form.get("status") or "Planned",
        "charged": float(form["charged"]) if form.get("charged") else None,
        "notes": form.get("notes", "").strip(),
    }
    return {k: v for k, v in data.items() if v is not None and v != ""}


# ---------------------------------------------------------------------
# ADMIN: EVENT SUB-RESOURCES (dishes, staff assignments, expenses linking)
# ---------------------------------------------------------------------

@app.route("/admin/events/<event_id>/link-dish", methods=["POST"])
@login_required
def admin_event_link_dish(event_id):
    dish_id = request.form.get("dish_id")
    event = db.get_record_friendly("events", event_id)
    existing = event.get("dishes_link") or []
    if dish_id and dish_id not in existing:
        db.update_record_friendly("events", event_id, {"dishes_link": existing + [dish_id]})
        flash("Dish linked to event.", "success")
    return redirect(url_for("admin_event_detail", event_id=event_id))


@app.route("/admin/events/<event_id>/add-expense", methods=["POST"])
@login_required
def admin_event_add_expense(event_id):
    data = {
        "item_name": request.form.get("item_name", "").strip(),
        "type": request.form.get("type") or "Other",
        "cost": float(request.form["cost"]) if request.form.get("cost") else 0,
        "notes": request.form.get("notes", "").strip(),
        "event_link": [event_id],
    }
    expense = db.create_record_friendly("expenses", data)

    photo = request.files.get("photo")
    if photo and photo.filename:
        urls = save_uploaded_files([photo])
        if urls:
            db.update_record_friendly("expenses", expense["id"], {"photo": to_attachments(urls)})

    flash("Expense added.", "success")
    return redirect(url_for("admin_event_detail", event_id=event_id))


@app.route("/admin/events/<event_id>/assign-staff", methods=["POST"])
@login_required
def admin_event_assign_staff(event_id):
    staff_id = request.form.get("staff_id")
    role_on_event = request.form.get("role_on_event", "").strip()
    pay_type_used = request.form.get("pay_type_used") or ""
    amount_paid = float(request.form["amount_paid"]) if request.form.get("amount_paid") else 0

    staff = db.get_record_friendly("staff", staff_id) if staff_id else None
    label = f"{staff['name']} - {role_on_event}" if staff else role_on_event

    data = {
        "label": label,
        "role_on_event": role_on_event,
        "amount_paid": amount_paid,
        "event_link": [event_id],
        "staff_link": [staff_id] if staff_id else [],
    }
    if pay_type_used:
        data["pay_type_used"] = pay_type_used

    db.create_record_friendly("assignments", data)
    flash("Staff assigned to event.", "success")
    return redirect(url_for("admin_event_detail", event_id=event_id))


@app.route("/admin/expenses/<expense_id>/delete", methods=["POST"])
@login_required
def admin_expense_delete(expense_id):
    event_id = request.form.get("event_id")
    db.delete_record_friendly("expenses", expense_id)
    flash("Expense removed.", "success")
    return redirect(url_for("admin_event_detail", event_id=event_id))


@app.route("/admin/assignments/<assignment_id>/delete", methods=["POST"])
@login_required
def admin_assignment_delete(assignment_id):
    event_id = request.form.get("event_id")
    db.delete_record_friendly("assignments", assignment_id)
    flash("Staff assignment removed.", "success")
    return redirect(url_for("admin_event_detail", event_id=event_id))


# ---------------------------------------------------------------------
# ADMIN: DISHES
# ---------------------------------------------------------------------

@app.route("/admin/dishes")
@login_required
def admin_dishes_list():
    dishes = db.list_records_friendly("dishes")
    dishes.sort(key=lambda d: d.get("name") or "")
    return render_template("admin/dishes_list.html", dishes=dishes)


@app.route("/admin/dishes/new", methods=["GET", "POST"])
@login_required
def admin_dish_new():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "category": request.form.get("category") or None,
            "ingredients": request.form.get("ingredients", "").strip(),
        }
        data = {k: v for k, v in data.items() if v}
        dish = db.create_record_friendly("dishes", data)

        photos = request.files.getlist("photos")
        urls = save_uploaded_files(photos)
        if urls:
            db.update_record_friendly("dishes", dish["id"], {"photos": to_attachments(urls)})

        flash("Dish added.", "success")
        return redirect(url_for("admin_dishes_list"))

    return render_template("admin/dish_form.html", dish=None, categories=DISH_CATEGORY_CHOICES)


@app.route("/admin/dishes/<dish_id>/edit", methods=["GET", "POST"])
@login_required
def admin_dish_edit(dish_id):
    dish = db.get_record_friendly("dishes", dish_id)
    if dish is None:
        flash("Dish not found.", "error")
        return redirect(url_for("admin_dishes_list"))

    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "category": request.form.get("category") or None,
            "ingredients": request.form.get("ingredients", "").strip(),
        }
        data = {k: v for k, v in data.items() if v is not None}
        db.update_record_friendly("dishes", dish_id, data)

        photos = request.files.getlist("photos")
        urls = save_uploaded_files(photos)
        if urls:
            existing = dish.get("photos") or []
            db.update_record_friendly("dishes", dish_id, {"photos": existing + to_attachments(urls)})

        flash("Dish updated.", "success")
        return redirect(url_for("admin_dishes_list"))

    return render_template("admin/dish_form.html", dish=dish, categories=DISH_CATEGORY_CHOICES)


@app.route("/admin/dishes/<dish_id>/delete", methods=["POST"])
@login_required
def admin_dish_delete(dish_id):
    db.delete_record_friendly("dishes", dish_id)
    flash("Dish deleted.", "success")
    return redirect(url_for("admin_dishes_list"))


# ---------------------------------------------------------------------
# ADMIN: STAFF
# ---------------------------------------------------------------------

@app.route("/admin/staff")
@login_required
def admin_staff_list():
    staff = db.list_records_friendly("staff")
    staff.sort(key=lambda s: s.get("name") or "")
    return render_template("admin/staff_list.html", staff=staff)


@app.route("/admin/staff/new", methods=["GET", "POST"])
@login_required
def admin_staff_new():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "role": request.form.get("role") or None,
            "phone": request.form.get("phone", "").strip(),
            "pay_type": request.form.get("pay_type") or None,
            "rate": float(request.form["rate"]) if request.form.get("rate") else None,
            "notes": request.form.get("notes", "").strip(),
        }
        data = {k: v for k, v in data.items() if v not in (None, "")}
        db.create_record_friendly("staff", data)
        flash("Staff member added.", "success")
        return redirect(url_for("admin_staff_list"))

    return render_template(
        "admin/staff_form.html", staff=None, roles=STAFF_ROLE_CHOICES, pay_types=PAY_TYPE_CHOICES
    )


@app.route("/admin/staff/<staff_id>/edit", methods=["GET", "POST"])
@login_required
def admin_staff_edit(staff_id):
    staff = db.get_record_friendly("staff", staff_id)
    if staff is None:
        flash("Staff member not found.", "error")
        return redirect(url_for("admin_staff_list"))

    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "role": request.form.get("role") or None,
            "phone": request.form.get("phone", "").strip(),
            "pay_type": request.form.get("pay_type") or None,
            "rate": float(request.form["rate"]) if request.form.get("rate") else None,
            "notes": request.form.get("notes", "").strip(),
        }
        data = {k: v for k, v in data.items() if v not in (None, "")}
        db.update_record_friendly("staff", staff_id, data)
        flash("Staff member updated.", "success")
        return redirect(url_for("admin_staff_list"))

    return render_template(
        "admin/staff_form.html", staff=staff, roles=STAFF_ROLE_CHOICES, pay_types=PAY_TYPE_CHOICES
    )


@app.route("/admin/staff/<staff_id>/delete", methods=["POST"])
@login_required
def admin_staff_delete(staff_id):
    db.delete_record_friendly("staff", staff_id)
    flash("Staff member removed.", "success")
    return redirect(url_for("admin_staff_list"))


# ---------------------------------------------------------------------
# ADMIN: CLIENTS
# ---------------------------------------------------------------------

@app.route("/admin/clients")
@login_required
def admin_clients_list():
    clients = db.list_records_friendly("clients")
    clients.sort(key=lambda c: c.get("name") or "")
    return render_template("admin/clients_list.html", clients=clients)


@app.route("/admin/clients/new", methods=["GET", "POST"])
@login_required
def admin_client_new():
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "notes": request.form.get("notes", "").strip(),
        }
        data = {k: v for k, v in data.items() if v}
        db.create_record_friendly("clients", data)
        flash("Client added.", "success")
        return redirect(url_for("admin_clients_list"))
    return render_template("admin/client_form.html", client=None)


@app.route("/admin/clients/<client_id>")
@login_required
def admin_client_detail(client_id):
    client = db.get_record_friendly("clients", client_id)
    if client is None:
        flash("Client not found.", "error")
        return redirect(url_for("admin_clients_list"))
    event_ids = client.get("events_link") or []
    events = [db.get_record_friendly("events", eid) for eid in event_ids]
    return render_template("admin/client_detail.html", client=client, events=events)


@app.route("/admin/clients/<client_id>/edit", methods=["GET", "POST"])
@login_required
def admin_client_edit(client_id):
    client = db.get_record_friendly("clients", client_id)
    if client is None:
        flash("Client not found.", "error")
        return redirect(url_for("admin_clients_list"))

    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "notes": request.form.get("notes", "").strip(),
        }
        data = {k: v for k, v in data.items() if v}
        db.update_record_friendly("clients", client_id, data)
        flash("Client updated.", "success")
        return redirect(url_for("admin_clients_list"))

    return render_template("admin/client_form.html", client=client)


# ---------------------------------------------------------------------
# ADMIN: INQUIRIES
# ---------------------------------------------------------------------

@app.route("/admin/inquiries")
@login_required
def admin_inquiries_list():
    inquiries = db.list_records_friendly("inquiries")
    inquiries.sort(key=lambda i: i.get("received_at") or "", reverse=True)
    status_filter = request.args.get("status")
    if status_filter:
        inquiries = [i for i in inquiries if i.get("status") == status_filter]
    return render_template(
        "admin/inquiries_list.html",
        inquiries=inquiries,
        statuses=INQUIRY_STATUS_CHOICES,
        active_filter=status_filter,
    )


@app.route("/admin/inquiries/<inquiry_id>/status", methods=["POST"])
@login_required
def admin_inquiry_update_status(inquiry_id):
    new_status = request.form.get("status")
    if new_status:
        db.update_record_friendly("inquiries", inquiry_id, {"status": new_status})
        flash("Inquiry status updated.", "success")
    return redirect(url_for("admin_inquiries_list"))


@app.route("/admin/inquiries/<inquiry_id>/convert", methods=["POST"])
@login_required
def admin_inquiry_convert(inquiry_id):
    """Create a new Event pre-filled from an inquiry, and mark inquiry Converted-ish (Confirmed)."""
    inquiry = db.get_record_friendly("inquiries", inquiry_id)
    if inquiry is None:
        flash("Inquiry not found.", "error")
        return redirect(url_for("admin_inquiries_list"))

    event_data = {
        "name": f"{inquiry.get('name', 'New Client')} - {inquiry.get('event_type', 'Event')}",
        "type": inquiry.get("event_type") if inquiry.get("event_type") in EVENT_TYPE_CHOICES else "Other",
        "status": "Planned",
    }
    if inquiry.get("event_date"):
        event_data["date"] = inquiry["event_date"]
    if inquiry.get("guests"):
        event_data["guests"] = inquiry["guests"]

    event = db.create_record_friendly("events", event_data)
    db.update_record_friendly("inquiries", inquiry_id, {"status": "Confirmed"})

    flash("Inquiry converted to a new event. Please complete the event details.", "success")
    return redirect(url_for("admin_event_edit", event_id=event["id"]))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
