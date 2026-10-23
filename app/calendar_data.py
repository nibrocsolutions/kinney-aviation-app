"""Dates the shop can see on the calendar.

Planned visits are stored as schedule entries. Work orders, annual due dates,
and unpaid invoices are read from the records already in the shop.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Aircraft, Invoice, MaintenanceRecord, ScheduleEntry
from app.schemas import CalendarItem

RECORD_STATUS = {
    "open": "Open",
    "in_work": "In work",
    "awaiting_parts": "Awaiting parts",
    "complete": "Complete",
}

INVOICE_STATUS = {
    "issued": "Issued",
    "partial": "Partial",
}


def calendar_items(db: Session, start: date, end: date) -> list[CalendarItem]:
    items: list[CalendarItem] = []

    entries = db.scalars(
        select(ScheduleEntry)
        .options(selectinload(ScheduleEntry.aircraft))
        .where(ScheduleEntry.scheduled_on >= start, ScheduleEntry.scheduled_on <= end)
        .order_by(ScheduleEntry.scheduled_on, ScheduleEntry.id)
    )
    for entry in entries:
        registration = entry.aircraft.registration if entry.aircraft is not None else None
        detail = entry.notes or ""
        if registration and entry.notes:
            detail = f"{registration} · {entry.notes}"
        elif registration:
            detail = registration
        items.append(
            CalendarItem(
                key=f"entry-{entry.id}",
                source="entry",
                date=entry.scheduled_on,
                starts_at=entry.starts_at,
                kind=entry.kind,
                label=entry.title,
                title=entry.title,
                detail=detail,
                href=f"#fleet/{entry.aircraft_id}" if entry.aircraft_id else None,
                editable=True,
                entry_id=entry.id,
                registration=registration,
            )
        )

    records = db.scalars(
        select(MaintenanceRecord)
        .options(selectinload(MaintenanceRecord.aircraft))
        .where(MaintenanceRecord.opened_on >= start, MaintenanceRecord.opened_on <= end)
        .order_by(MaintenanceRecord.opened_on, MaintenanceRecord.number)
    )
    for record in records:
        registration = record.aircraft.registration
        status = RECORD_STATUS.get(record.status, record.status)
        items.append(
            CalendarItem(
                key=f"record-{record.id}",
                source="record",
                date=record.opened_on,
                kind="work",
                label=f"{registration} · {record.title}",
                title=f"{registration} · {record.title}",
                detail=f"{record.number} · {status}",
                href=f"#records/{record.id}",
                registration=registration,
            )
        )

    aircraft_rows = db.scalars(
        select(Aircraft)
        .where(
            Aircraft.annual_due.is_not(None),
            Aircraft.annual_due >= start,
            Aircraft.annual_due <= end,
        )
        .order_by(Aircraft.annual_due, Aircraft.registration)
    )
    for aircraft in aircraft_rows:
        if aircraft.annual_due is None:
            continue
        place = f" · {aircraft.home_airport}" if aircraft.home_airport else ""
        items.append(
            CalendarItem(
                key=f"annual-{aircraft.id}",
                source="annual",
                date=aircraft.annual_due,
                kind="annual",
                label=f"{aircraft.registration} annual due",
                title=f"{aircraft.registration} annual due",
                detail=f"{aircraft.make} {aircraft.model}{place}",
                href=f"#fleet/{aircraft.id}",
                registration=aircraft.registration,
            )
        )

    invoices = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.aircraft))
        .where(
            Invoice.due_on.is_not(None),
            Invoice.due_on >= start,
            Invoice.due_on <= end,
            Invoice.voided.is_(False),
            Invoice.status.in_(("issued", "partial")),
        )
        .order_by(Invoice.due_on, Invoice.number)
    )
    for invoice in invoices:
        if invoice.due_on is None:
            continue
        registration = invoice.aircraft.registration
        status = INVOICE_STATUS.get(invoice.status, invoice.status)
        items.append(
            CalendarItem(
                key=f"invoice-{invoice.id}",
                source="invoice",
                date=invoice.due_on,
                kind="due",
                label=f"{invoice.number} due",
                title=f"{invoice.number} due · {registration}",
                detail=status,
                href=f"#billing/{invoice.id}",
                registration=registration,
            )
        )

    items.sort(key=lambda item: (item.date, item.starts_at or "99:99", item.source != "entry", item.title))
    return items
