"""
Thin wrapper around pyairtable that centralizes all reads/writes to the
q-rated-experiences Airtable base, using field IDs from config.py so the
app is not brittle to field renames done inside Airtable's UI.
"""
from pyairtable import Api
from config import Config, TABLES, FIELDS


_api = None


def get_api():
    global _api
    if _api is None:
        _api = Api(Config.AIRTABLE_API_KEY)
    return _api


def _table(table_key):
    return get_api().table(Config.AIRTABLE_BASE_ID, TABLES[table_key])


# ---------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------

def list_records(table_key, formula=None, sort=None):
    t = _table(table_key)
    kwargs = {}
    if formula:
        kwargs["formula"] = formula
    if sort:
        kwargs["sort"] = sort
    return t.all(**kwargs)


def get_record(table_key, record_id):
    t = _table(table_key)
    try:
        return t.get(record_id)
    except Exception:
        return None


def create_record(table_key, fields_by_id):
    t = _table(table_key)
    return t.create(fields_by_id)


def update_record(table_key, record_id, fields_by_id):
    t = _table(table_key)
    return t.update(record_id, fields_by_id)


def delete_record(table_key, record_id):
    t = _table(table_key)
    return t.delete(record_id)


# ---------------------------------------------------------------------
# Field-name convenience layer: lets callers use readable keys
# (e.g. "name", "status") instead of raw Airtable field IDs.
# ---------------------------------------------------------------------

def to_field_ids(table_key, data):
    """Convert {friendly_key: value} -> {fldXXXX: value} for writes."""
    mapping = FIELDS[table_key]
    out = {}
    for k, v in data.items():
        if k not in mapping:
            raise KeyError(f"Unknown field '{k}' for table '{table_key}'")
        out[mapping[k]] = v
    return out


def from_record(table_key, record):
    """Convert an Airtable record ({id, fields: {Field Name: v}}) into a
    friendly dict {id, name/status/etc: v}. The Airtable REST API returns
    fields keyed by field NAME by default, so we invert our name-map to
    translate back to our internal friendly keys.
    """
    mapping = FIELDS[table_key]
    inverse = {v: k for k, v in mapping.items()}
    fields = record.get("fields", {})
    out = {"id": record["id"], "created_time": record.get("createdTime")}
    for k, v in fields.items():
        friendly = inverse.get(k, k)
        out[friendly] = v
    return out


def list_records_friendly(table_key, formula=None, sort=None):
    raw = list_records(table_key, formula=formula, sort=sort)
    return [from_record(table_key, r) for r in raw]


def get_record_friendly(table_key, record_id):
    raw = get_record(table_key, record_id)
    if raw is None:
        return None
    return from_record(table_key, raw)


def create_record_friendly(table_key, data):
    payload = to_field_ids(table_key, data)
    raw = create_record(table_key, payload)
    return from_record(table_key, raw)


def update_record_friendly(table_key, record_id, data):
    payload = to_field_ids(table_key, data)
    raw = update_record(table_key, record_id, payload)
    return from_record(table_key, raw)


def delete_record_friendly(table_key, record_id):
    return delete_record(table_key, record_id)


# ---------------------------------------------------------------------
# Business-level helpers
# ---------------------------------------------------------------------

def get_public_events(status_filter="Completed"):
    """Events safe to show on the public site: only Completed, sorted newest first."""
    formula = f"{{Status}} = '{status_filter}'"
    events = list_records_friendly("events", formula=formula)
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return events


def get_all_events_sorted():
    events = list_records_friendly("events")
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return events


def get_event_with_relations(event_id):
    """Fetch an event plus its linked dishes, expenses, and staff assignments (with staff names)."""
    event = get_record_friendly("events", event_id)
    if event is None:
        return None

    dish_ids = event.get("dishes_link") or []
    expense_ids = event.get("expenses_link") or []
    assignment_ids = event.get("staff_assignments_link") or []
    client_ids = event.get("client_link") or []

    event["dishes"] = [get_record_friendly("dishes", d) for d in dish_ids]
    event["expenses"] = [get_record_friendly("expenses", e) for e in expense_ids]

    assignments = [get_record_friendly("assignments", a) for a in assignment_ids]
    for a in assignments:
        staff_ids = a.get("staff_link") or []
        a["staff"] = [get_record_friendly("staff", s) for s in staff_ids]
    event["assignments"] = assignments

    clients = [get_record_friendly("clients", c) for c in client_ids]
    event["client"] = clients[0] if clients else None

    return event


def get_dashboard_stats():
    events = list_records_friendly("events")
    inquiries = list_records_friendly("inquiries")

    total_revenue = sum(e.get("charged") or 0 for e in events if e.get("status") == "Completed")
    total_profit = sum(e.get("profit") or 0 for e in events if e.get("status") == "Completed")
    completed_count = sum(1 for e in events if e.get("status") == "Completed")
    upcoming_count = sum(1 for e in events if e.get("status") == "Confirmed")
    new_inquiries = sum(1 for i in inquiries if i.get("status") == "New")

    return {
        "total_events": len(events),
        "completed_count": completed_count,
        "upcoming_count": upcoming_count,
        "new_inquiries": new_inquiries,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
    }
