"""Export and import the whole shop as one JSON file.

The file includes password hashes and is meant to stay private. Import
replaces the shop. The person who imports stays signed in: their existing
session is attached to the imported account, or they are put back as an
active administrator when the file does not contain their username.
"""

import hashlib
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CLOCK, normalize_display_name, normalize_username
from app.models import (
    Aircraft,
    AuthSession,
    Customer,
    Invoice,
    InvoiceLine,
    LaborLine,
    MaintenanceRecord,
    PartLine,
    Payment,
    ScheduleEntry,
    Shop,
    User,
)

FORMAT = "kinney-aviation-backup"
VERSION = 1
_NOTE = 100_000

_WIPE = (
    Payment,
    InvoiceLine,
    Invoice,
    LaborLine,
    PartLine,
    ScheduleEntry,
    MaintenanceRecord,
    Aircraft,
    Customer,
    AuthSession,
    User,
    Shop,
)


def build_backup(db: Session) -> dict:
    shop = db.scalar(select(Shop).order_by(Shop.id).limit(1))
    if shop is None:
        raise ValueError("Shop profile is missing.")
    records = list(db.scalars(select(MaintenanceRecord).order_by(MaintenanceRecord.id)))
    invoices = list(db.scalars(select(Invoice).order_by(Invoice.id)))
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_on": date.today().isoformat(),
        "shop": _shop_out(shop),
        "customers": [_customer_out(row) for row in db.scalars(select(Customer).order_by(Customer.id))],
        "aircraft": [_aircraft_out(row) for row in db.scalars(select(Aircraft).order_by(Aircraft.id))],
        "records": [_record_out(row) for row in records],
        "invoices": [_invoice_out(row) for row in invoices],
        "schedule": [_schedule_out(row) for row in db.scalars(select(ScheduleEntry).order_by(ScheduleEntry.id))],
        "users": [_user_out(row) for row in db.scalars(select(User).order_by(User.id))],
    }


def restore_backup(db: Session, payload: dict, *, token: str | None, user_id: int) -> dict:
    document = parse_backup(payload)
    preserved, token_hash, expires_at = _capture_session(db, token, user_id)
    try:
        _wipe(db)
        _load(db, document)
        role = _rebind_session(db, preserved, token_hash, expires_at)
        db.commit()
    except ValueError:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("That file does not match the shop records.") from exc
    except Exception:
        db.rollback()
        raise
    return {
        "message": "Shop data replaced.",
        "customers": len(document["customers"]),
        "aircraft": len(document["aircraft"]),
        "records": len(document["records"]),
        "invoices": len(document["invoices"]),
        "schedule": len(document["schedule"]),
        "accounts": int(db.scalar(select(func.count(User.id))) or 0),
        "role": role,
    }


def parse_backup(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("This file is not a Kinney Aviation shop file.")
    if payload.get("format") != FORMAT:
        raise ValueError("This file is not a Kinney Aviation shop file.")
    if payload.get("version") != VERSION:
        raise ValueError("This shop file version is not supported.")
    shop = _shop_in(_object(payload.get("shop"), "Shop profile"))
    customers, customer_ids = _rows(payload, "customers", _customer_in, "Owner")
    aircraft, aircraft_ids = _rows(payload, "aircraft", _aircraft_in, "Aircraft")
    for row in aircraft:
        if row["customer_id"] not in customer_ids:
            raise ValueError(f"Aircraft {row['registration']} does not match an owner.")
    records, record_ids = _rows(payload, "records", _record_in, "Work order")
    for row in records:
        if row["aircraft_id"] not in aircraft_ids:
            raise ValueError(f"Work order {row['number']} does not match an aircraft.")
    invoices, _invoice_ids = _rows(payload, "invoices", _invoice_in, "Invoice")
    for row in invoices:
        if row["customer_id"] not in customer_ids or row["aircraft_id"] not in aircraft_ids:
            raise ValueError(f"Invoice {row['number']} does not match an owner and aircraft.")
        if row["record_id"] not in record_ids:
            raise ValueError(f"Invoice {row['number']} does not match a work order.")
    schedule, _schedule_ids = _rows(payload, "schedule", _schedule_in, "Calendar entry")
    for row in schedule:
        if row["aircraft_id"] is not None and row["aircraft_id"] not in aircraft_ids:
            raise ValueError(f"Calendar entry {row['title']} does not match an aircraft.")
        if row["record_id"] is not None and row["record_id"] not in record_ids:
            raise ValueError(f"Calendar entry {row['title']} does not match a work order.")
    users, _user_ids = _rows(payload, "users", _user_in, "Account")
    _unique((row["registration"].upper() for row in aircraft), None, "N-number")
    _unique(records, "number", "work order number")
    _unique(invoices, "number", "invoice number")
    _unique(users, "username", "account")
    _unique_children(records, "labor_lines", "Labor line")
    _unique_children(records, "part_lines", "Part line")
    _unique_children(invoices, "lines", "Invoice line")
    _unique_children(invoices, "payments", "Payment")
    return {
        "shop": shop,
        "customers": customers,
        "aircraft": aircraft,
        "records": records,
        "invoices": invoices,
        "schedule": schedule,
        "users": users,
    }


def _capture_session(db: Session, token: str | None, user_id: int) -> tuple[dict | None, str | None, datetime | None]:
    user = db.get(User, user_id)
    if user is None or not token:
        return None, None, None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if row is None:
        return None, None, None
    preserved = {
        "username": user.username,
        "display_name": user.display_name,
        "password_hash": user.password_hash,
    }
    return preserved, token_hash, row.expires_at


def _wipe(db: Session) -> None:
    for model in _WIPE:
        db.execute(delete(model), execution_options={"synchronize_session": False})
    db.expunge_all()


def _load(db: Session, document: dict) -> None:
    db.add(Shop(**document["shop"]))
    db.flush()
    db.add_all(Customer(**row) for row in document["customers"])
    db.flush()
    db.add_all(Aircraft(**row) for row in document["aircraft"])
    db.flush()
    for row in document["records"]:
        labor = row["labor_lines"]
        parts = row["part_lines"]
        record = MaintenanceRecord(**{key: value for key, value in row.items() if key not in {"labor_lines", "part_lines"}})
        db.add(record)
        db.flush()
        db.add_all(LaborLine(record_id=record.id, **line) for line in labor)
        db.add_all(PartLine(record_id=record.id, **line) for line in parts)
    db.flush()
    for row in document["invoices"]:
        lines = row["lines"]
        payments = row["payments"]
        invoice = Invoice(**{key: value for key, value in row.items() if key not in {"lines", "payments"}})
        db.add(invoice)
        db.flush()
        db.add_all(InvoiceLine(invoice_id=invoice.id, **line) for line in lines)
        db.add_all(Payment(invoice_id=invoice.id, **payment) for payment in payments)
    db.flush()
    db.add_all(ScheduleEntry(**row) for row in document["schedule"])
    db.add_all(User(**row) for row in document["users"])
    db.flush()


def _rebind_session(
    db: Session,
    preserved: dict | None,
    token_hash: str | None,
    expires_at: datetime | None,
) -> str:
    if preserved is None or token_hash is None or expires_at is None:
        return "admin"
    user = db.scalar(select(User).where(User.username == preserved["username"]))
    if user is None:
        next_id = int(db.scalar(select(func.max(User.id))) or 0) + 1
        user = User(
            id=next_id,
            username=preserved["username"],
            display_name=preserved["display_name"],
            password_hash=preserved["password_hash"],
            role="admin",
            active=True,
        )
        db.add(user)
        db.flush()
    elif not user.active:
        user.active = True
    db.add(AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.flush()
    return user.role


def _shop_out(shop: Shop) -> dict:
    return {
        "id": shop.id,
        "business_name": shop.business_name,
        "mechanic_name": shop.mechanic_name,
        "certificate_label": shop.certificate_label,
        "phone": shop.phone,
        "email": shop.email,
        "base_city": shop.base_city,
        "default_labor_rate_cents": shop.default_labor_rate_cents,
        "default_travel_rate_cents": shop.default_travel_rate_cents,
        "payment_terms_days": shop.payment_terms_days,
        "demo_seeded": shop.demo_seeded,
    }


def _customer_out(row: Customer) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "email": row.email,
        "phone": row.phone,
        "city": row.city,
        "notes": row.notes,
    }


def _aircraft_out(row: Aircraft) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "registration": row.registration,
        "make": row.make,
        "model": row.model,
        "serial_number": row.serial_number,
        "year_manufactured": row.year_manufactured,
        "engine_model": row.engine_model,
        "tach_hours": _number(row.tach_hours, "0.1"),
        "hobbs_hours": _number(row.hobbs_hours, "0.1"),
        "total_time_hours": _number(row.total_time_hours, "0.1"),
        "home_airport": row.home_airport,
        "annual_due": _iso(row.annual_due),
        "notes": row.notes,
    }


def _record_out(row: MaintenanceRecord) -> dict:
    return {
        "id": row.id,
        "aircraft_id": row.aircraft_id,
        "number": row.number,
        "kind": row.kind,
        "status": row.status,
        "title": row.title,
        "discrepancy": row.discrepancy,
        "corrective_action": row.corrective_action,
        "location": row.location,
        "opened_on": row.opened_on.isoformat(),
        "closed_on": _iso(row.closed_on),
        "tach_hours": _number(row.tach_hours, "0.1"),
        "hobbs_hours": _number(row.hobbs_hours, "0.1"),
        "rating": row.rating,
        "signoff_name": row.signoff_name,
        "certificate_ref": row.certificate_ref,
        "travel_hours": _number(row.travel_hours, "0.1"),
        "rts_statement": row.rts_statement,
        "notes": row.notes,
        "labor_lines": [
            {
                "id": line.id,
                "description": line.description,
                "hours": _number(line.hours, "0.1"),
                "rate_cents": line.rate_cents,
            }
            for line in sorted(row.labor_lines, key=lambda line: line.id)
        ],
        "part_lines": [
            {
                "id": line.id,
                "part_number": line.part_number,
                "description": line.description,
                "quantity": _number(line.quantity, "0.01"),
                "unit_price_cents": line.unit_price_cents,
            }
            for line in sorted(row.part_lines, key=lambda line: line.id)
        ],
    }


def _invoice_out(row: Invoice) -> dict:
    return {
        "id": row.id,
        "number": row.number,
        "customer_id": row.customer_id,
        "aircraft_id": row.aircraft_id,
        "record_id": row.record_id,
        "status": row.status,
        "voided": row.voided,
        "issued_on": _iso(row.issued_on),
        "due_on": _iso(row.due_on),
        "tax_cents": row.tax_cents,
        "notes": row.notes,
        "lines": [
            {
                "id": line.id,
                "kind": line.kind,
                "description": line.description,
                "quantity": _number(line.quantity, "0.01"),
                "unit_cents": line.unit_cents,
                "amount_cents": line.amount_cents,
                "sort_order": line.sort_order,
            }
            for line in sorted(row.lines, key=lambda line: (line.sort_order, line.id))
        ],
        "payments": [
            {
                "id": payment.id,
                "paid_on": payment.paid_on.isoformat(),
                "amount_cents": payment.amount_cents,
                "method": payment.method,
                "reference": payment.reference,
            }
            for payment in sorted(row.payments, key=lambda payment: payment.id)
        ],
    }


def _schedule_out(row: ScheduleEntry) -> dict:
    return {
        "id": row.id,
        "scheduled_on": row.scheduled_on.isoformat(),
        "starts_at": row.starts_at,
        "kind": row.kind,
        "title": row.title,
        "notes": row.notes,
        "aircraft_id": row.aircraft_id,
        "record_id": row.record_id,
    }


def _user_out(row: User) -> dict:
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "password_hash": row.password_hash,
        "role": row.role,
        "active": row.active,
    }


def _rows(payload: dict, key: str, reader, label: str) -> tuple[list[dict], set[int]]:
    raw = payload.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list.")
    rows = []
    seen: set[int] = set()
    for item in raw:
        row = reader(_object(item, label))
        if row["id"] in seen:
            raise ValueError(f"Duplicate {label.lower()} id {row['id']}.")
        seen.add(row["id"])
        rows.append(row)
    return rows, seen


def _shop_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Shop id", minimum=1),
        "business_name": _text(row.get("business_name"), "Shop name", 160, required=True),
        "mechanic_name": _text(row.get("mechanic_name"), "Mechanic name", 160, required=True),
        "certificate_label": _text(row.get("certificate_label"), "Certificate", 160, required=True),
        "phone": _text(row.get("phone"), "Shop phone", 40),
        "email": _text(row.get("email"), "Shop email", 160),
        "base_city": _text(row.get("base_city"), "Base", 80),
        "default_labor_rate_cents": _int(row.get("default_labor_rate_cents"), "Labor rate", minimum=0),
        "default_travel_rate_cents": _int(row.get("default_travel_rate_cents"), "Travel rate", minimum=0),
        "payment_terms_days": _int(row.get("payment_terms_days"), "Payment terms", minimum=0),
        "demo_seeded": _bool(row.get("demo_seeded"), "Sample fleet flag"),
    }


def _customer_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Owner id", minimum=1),
        "name": _text(row.get("name"), "Owner name", 160, required=True),
        "email": _optional_text(row.get("email"), "Owner email", 160),
        "phone": _optional_text(row.get("phone"), "Owner phone", 40),
        "city": _optional_text(row.get("city"), "Owner city", 80),
        "notes": _optional_text(row.get("notes"), "Owner notes", _NOTE),
    }


def _aircraft_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Aircraft id", minimum=1),
        "customer_id": _int(row.get("customer_id"), "Aircraft owner", minimum=1),
        "registration": _text(row.get("registration"), "N-number", 8, required=True),
        "make": _text(row.get("make"), "Make", 80, required=True),
        "model": _text(row.get("model"), "Model", 80, required=True),
        "serial_number": _optional_text(row.get("serial_number"), "Serial", 40),
        "year_manufactured": _int(row.get("year_manufactured"), "Year", minimum=1900, maximum=2100, allow_none=True),
        "engine_model": _optional_text(row.get("engine_model"), "Engine", 80),
        "tach_hours": _quantity(row.get("tach_hours"), "Tach", allow_none=True),
        "hobbs_hours": _quantity(row.get("hobbs_hours"), "Hobbs", allow_none=True),
        "total_time_hours": _quantity(row.get("total_time_hours"), "Total time", allow_none=True),
        "home_airport": _optional_text(row.get("home_airport"), "Home airport", 4),
        "annual_due": _date(row.get("annual_due"), "Annual due", allow_none=True),
        "notes": _optional_text(row.get("notes"), "Aircraft notes", _NOTE),
    }


def _record_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Work order id", minimum=1),
        "aircraft_id": _int(row.get("aircraft_id"), "Work order aircraft", minimum=1),
        "number": _text(row.get("number"), "Work order number", 20, required=True),
        "kind": _text(row.get("kind"), "Work order kind", 32, required=True),
        "status": _text(row.get("status"), "Work order status", 32, required=True),
        "title": _text(row.get("title"), "Work order title", 200, required=True),
        "discrepancy": _text(row.get("discrepancy"), "Discrepancy", _NOTE),
        "corrective_action": _text(row.get("corrective_action"), "Corrective action", _NOTE),
        "location": _optional_text(row.get("location"), "Location", 4),
        "opened_on": _date(row.get("opened_on"), "Opened on"),
        "closed_on": _date(row.get("closed_on"), "Closed on", allow_none=True),
        "tach_hours": _quantity(row.get("tach_hours"), "Tach", allow_none=True),
        "hobbs_hours": _quantity(row.get("hobbs_hours"), "Hobbs", allow_none=True),
        "rating": _text(row.get("rating") or "AP", "Rating", 2, required=True),
        "signoff_name": _text(row.get("signoff_name"), "Sign-off", 160),
        "certificate_ref": _text(row.get("certificate_ref"), "Certificate reference", 160),
        "travel_hours": _quantity(row.get("travel_hours") if row.get("travel_hours") is not None else 0, "Travel hours"),
        "rts_statement": _text(row.get("rts_statement"), "Return to service", _NOTE),
        "notes": _optional_text(row.get("notes"), "Work order notes", _NOTE),
        "labor_lines": _children(row.get("labor_lines", []), _labor_in, "Labor line"),
        "part_lines": _children(row.get("part_lines", []), _part_in, "Part line"),
    }


def _labor_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Labor line id", minimum=1),
        "description": _text(row.get("description"), "Labor description", 200, required=True),
        "hours": _quantity(row.get("hours"), "Labor hours"),
        "rate_cents": _int(row.get("rate_cents"), "Labor rate", minimum=0),
    }


def _part_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Part line id", minimum=1),
        "part_number": _text(row.get("part_number"), "Part number", 40),
        "description": _text(row.get("description"), "Part description", 200, required=True),
        "quantity": _quantity(row.get("quantity"), "Part quantity"),
        "unit_price_cents": _int(row.get("unit_price_cents"), "Part price", minimum=0),
    }


def _invoice_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Invoice id", minimum=1),
        "number": _text(row.get("number"), "Invoice number", 20, required=True),
        "customer_id": _int(row.get("customer_id"), "Invoice owner", minimum=1),
        "aircraft_id": _int(row.get("aircraft_id"), "Invoice aircraft", minimum=1),
        "record_id": _int(row.get("record_id"), "Invoice work order", minimum=1),
        "status": _text(row.get("status") or "draft", "Invoice status", 16, required=True),
        "voided": _bool(row.get("voided"), "Voided"),
        "issued_on": _date(row.get("issued_on"), "Issued on", allow_none=True),
        "due_on": _date(row.get("due_on"), "Due on", allow_none=True),
        "tax_cents": _int(row.get("tax_cents") if row.get("tax_cents") is not None else 0, "Tax", minimum=0),
        "notes": _text(row.get("notes"), "Invoice notes", _NOTE),
        "lines": _children(row.get("lines", []), _line_in, "Invoice line"),
        "payments": _children(row.get("payments", []), _payment_in, "Payment"),
    }


def _line_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Invoice line id", minimum=1),
        "kind": _text(row.get("kind"), "Invoice line kind", 16, required=True),
        "description": _text(row.get("description"), "Invoice line", 240, required=True),
        "quantity": _quantity(row.get("quantity"), "Invoice quantity"),
        "unit_cents": _int(row.get("unit_cents"), "Unit price", minimum=0),
        "amount_cents": _int(row.get("amount_cents"), "Line amount", minimum=0),
        "sort_order": _int(row.get("sort_order") if row.get("sort_order") is not None else 0, "Sort order", minimum=0),
    }


def _payment_in(row: dict) -> dict:
    return {
        "id": _int(row.get("id"), "Payment id", minimum=1),
        "paid_on": _date(row.get("paid_on"), "Paid on"),
        "amount_cents": _int(row.get("amount_cents"), "Payment amount", minimum=1),
        "method": _text(row.get("method") or "check", "Payment method", 16, required=True),
        "reference": _text(row.get("reference"), "Payment reference", 80),
    }


def _schedule_in(row: dict) -> dict:
    starts = row.get("starts_at")
    if starts in (None, ""):
        starts_at = None
    elif isinstance(starts, str) and CLOCK.fullmatch(starts):
        starts_at = starts
    else:
        raise ValueError("Calendar time must look like 08:00.")
    return {
        "id": _int(row.get("id"), "Calendar entry id", minimum=1),
        "scheduled_on": _date(row.get("scheduled_on"), "Calendar date"),
        "starts_at": starts_at,
        "kind": _text(row.get("kind") or "visit", "Calendar kind", 24, required=True),
        "title": _text(row.get("title"), "Calendar title", 160, required=True),
        "notes": _text(row.get("notes"), "Calendar notes", 2000),
        "aircraft_id": _int(row.get("aircraft_id"), "Calendar aircraft", minimum=1, allow_none=True),
        "record_id": _int(row.get("record_id"), "Calendar work order", minimum=1, allow_none=True),
    }


def _user_in(row: dict) -> dict:
    try:
        username = normalize_username(str(row.get("username") or ""))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    try:
        display_name = normalize_display_name(str(row.get("display_name") or ""))
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    password_hash = row.get("password_hash")
    if not isinstance(password_hash, str) or not password_hash.startswith("scrypt$") or password_hash.count("$") != 5:
        raise ValueError(f"Account {username} is missing its password hash.")
    if len(password_hash) > 200:
        raise ValueError(f"Account {username} has a password hash that is too long.")
    role = row.get("role")
    if role not in {"admin", "shop"}:
        raise ValueError(f"Account {username} needs an admin or shop role.")
    return {
        "id": _int(row.get("id"), "Account id", minimum=1),
        "username": username,
        "display_name": display_name,
        "password_hash": password_hash,
        "role": role,
        "active": _bool(row.get("active"), "Account active", default=True),
    }


def _children(raw: object, reader, label: str) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError(f"{label}s must be a list.")
    return [reader(_object(item, label)) for item in raw]


def _unique_children(rows: list[dict], key: str, label: str) -> None:
    seen: set[int] = set()
    for row in rows:
        for child in row[key]:
            if child["id"] in seen:
                raise ValueError(f"Duplicate {label.lower()} id {child['id']}.")
            seen.add(child["id"])


def _unique(rows, key: str | None, label: str) -> None:
    seen = set()
    values = rows if key is None else (row[key] for row in rows)
    for value in values:
        if value in seen:
            raise ValueError(f"Duplicate {label} {value}.")
        seen.add(value)


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _text(value: object, label: str, limit: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    text = value.strip() if required else value
    if required and not text:
        raise ValueError(f"{label} is required.")
    if len(text) > limit:
        raise ValueError(f"{label} is too long.")
    return text


def _optional_text(value: object, label: str, limit: int) -> str | None:
    if value is None:
        return None
    text = _text(value, label, limit)
    return text or None


def _int(value: object, label: str, *, minimum: int | None = None, maximum: int | None = None, allow_none: bool = False) -> int | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"{label} is required.")
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number.")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{label} must be a whole number.")
        value = int(value)
    if not isinstance(value, int):
        raise ValueError(f"{label} must be a whole number.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} is out of range.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} is out of range.")
    return value


def _bool(value: object, label: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be true or false.")
    return value


def _quantity(value: object, label: str, *, allow_none: bool = False) -> float | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"{label} is required.")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if isinstance(value, float) and value != value:
        raise ValueError(f"{label} must be a number.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return float(value)


def _date(value: object, label: str, *, allow_none: bool = False) -> date | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"{label} is required.")
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a date like 2026-10-23.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a date like 2026-10-23.") from exc


def _iso(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _number(value: Decimal | float | int | None, places: str) -> float | None:
    if value is None:
        return None
    return float(Decimal(value).quantize(Decimal(places)))
