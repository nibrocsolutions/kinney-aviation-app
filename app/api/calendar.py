from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import require_user
from app.calendar_data import calendar_items
from app.database import get_db
from app.models import Aircraft, MaintenanceRecord, ScheduleEntry
from app.schemas import CalendarOut, ScheduleIn, ScheduleOut, ScheduleUpdate

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])


def schedule_out(entry: ScheduleEntry) -> ScheduleOut:
    registration = entry.aircraft.registration if entry.aircraft is not None else None
    return ScheduleOut(
        id=entry.id,
        scheduled_on=entry.scheduled_on,
        starts_at=entry.starts_at,
        kind=entry.kind,
        title=entry.title,
        notes=entry.notes or "",
        aircraft_id=entry.aircraft_id,
        record_id=entry.record_id,
        registration=registration,
    )


def _load_entry(db: Session, entry_id: int) -> ScheduleEntry:
    entry = db.scalar(
        select_entry().where(ScheduleEntry.id == entry_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Scheduled item not found.")
    return entry


def select_entry():
    return select(ScheduleEntry).options(selectinload(ScheduleEntry.aircraft))


def _bind(db: Session, entry: ScheduleEntry) -> None:
    if entry.record_id is not None:
        record = db.get(MaintenanceRecord, entry.record_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Work order not found.")
        if entry.aircraft_id is None:
            entry.aircraft_id = record.aircraft_id
        elif entry.aircraft_id != record.aircraft_id:
            raise HTTPException(status_code=400, detail="That work order is for a different aircraft.")
    if entry.aircraft_id is not None and db.get(Aircraft, entry.aircraft_id) is None:
        raise HTTPException(status_code=404, detail="Aircraft not found.")


@router.get("/calendar", response_model=CalendarOut)
def get_calendar(start: date, end: date, db: Session = Depends(get_db)) -> CalendarOut:
    if end < start or (end - start).days > 62:
        raise HTTPException(status_code=400, detail="Choose a span of 62 days or less.")
    return CalendarOut(start=start, end=end, items=calendar_items(db, start, end))


@router.post("/schedule", response_model=ScheduleOut, status_code=201)
def create_schedule(payload: ScheduleIn, db: Session = Depends(get_db)) -> ScheduleOut:
    entry = ScheduleEntry(
        scheduled_on=payload.scheduled_on,
        starts_at=payload.starts_at,
        kind=payload.kind,
        title=payload.title,
        notes=payload.notes,
        aircraft_id=payload.aircraft_id,
        record_id=payload.record_id,
    )
    _bind(db, entry)
    db.add(entry)
    db.commit()
    return schedule_out(_load_entry(db, entry.id))


@router.patch("/schedule/{entry_id}", response_model=ScheduleOut)
def update_schedule(entry_id: int, payload: ScheduleUpdate, db: Session = Depends(get_db)) -> ScheduleOut:
    entry = _load_entry(db, entry_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(entry, key, value)
    _bind(db, entry)
    db.commit()
    return schedule_out(_load_entry(db, entry.id))


@router.delete("/schedule/{entry_id}", status_code=204)
def delete_schedule(entry_id: int, db: Session = Depends(get_db)) -> None:
    entry = _load_entry(db, entry_id)
    db.delete(entry)
    db.commit()
