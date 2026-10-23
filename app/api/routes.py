from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.billing import (
    amount_due_cents,
    apply_lines,
    lines_from_record,
    quantize_hours,
    quantize_qty,
    recompute_invoice,
)
from app.config import settings
from app.database import get_db
from app.models import (
    Aircraft,
    Customer,
    Invoice,
    LaborLine,
    MaintenanceRecord,
    PartLine,
    Payment,
    Shop,
)
from app.numbers import next_number
from app.schemas import (
    AircraftIn,
    AircraftOut,
    AircraftUpdate,
    CustomerIn,
    CustomerOut,
    CustomerUpdate,
    DashboardOut,
    InvoiceOut,
    InvoiceUpdate,
    LaborIn,
    LaborUpdate,
    PartIn,
    PartUpdate,
    PaymentIn,
    PresentAircraft,
    PresentInvoice,
    PresentRecord,
    RecordIn,
    RecordOut,
    RecordUpdate,
    ShopOut,
    ShopUpdate,
)
from app.seed import ensure_shop
from app.serialize import (
    active_invoice,
    aircraft_out,
    customer_out,
    dashboard_out,
    invoice_out,
    present_aircraft,
    present_invoice,
    present_record,
    record_out,
)

router = APIRouter(prefix="/api")


def _shop(db: Session) -> Shop:
    return ensure_shop(db)


def _one(db: Session, model, ident: int, label: str):
    obj = db.get(model, ident)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found.")
    return obj


def _ensure_unlocked(record: MaintenanceRecord) -> None:
    invoice = active_invoice(record)
    if invoice and invoice.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=(
                f"{invoice.number} is {invoice.status}. "
                "Void it before changing labor, parts, or travel."
            ),
        )


def _apply(obj, payload) -> dict:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(obj, key, value)
    return data


def _record_query():
    return select(MaintenanceRecord).options(
        selectinload(MaintenanceRecord.labor_lines),
        selectinload(MaintenanceRecord.part_lines),
        selectinload(MaintenanceRecord.invoices),
        selectinload(MaintenanceRecord.aircraft).selectinload(Aircraft.customer),
    )


def _invoice_query():
    return select(Invoice).options(
        selectinload(Invoice.lines),
        selectinload(Invoice.payments),
        selectinload(Invoice.customer),
        selectinload(Invoice.aircraft),
        selectinload(Invoice.record).selectinload(MaintenanceRecord.labor_lines),
        selectinload(Invoice.record).selectinload(MaintenanceRecord.part_lines),
    )


def _aircraft_query():
    return select(Aircraft).options(
        selectinload(Aircraft.customer),
        selectinload(Aircraft.records),
        selectinload(Aircraft.invoices).selectinload(Invoice.lines),
        selectinload(Aircraft.invoices).selectinload(Invoice.payments),
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@router.get("/shop", response_model=ShopOut)
def get_shop(db: Session = Depends(get_db)) -> Shop:
    return _shop(db)


@router.patch("/shop", response_model=ShopOut)
def update_shop(payload: ShopUpdate, db: Session = Depends(get_db)) -> Shop:
    shop = _shop(db)
    _apply(shop, payload)
    db.commit()
    db.refresh(shop)
    return shop


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)) -> DashboardOut:
    shop = _shop(db)
    today = date.today()
    customers = list(db.scalars(select(Customer).order_by(Customer.name)))
    aircraft = list(db.scalars(_aircraft_query().order_by(Aircraft.registration)))
    records = list(db.scalars(_record_query()))
    invoices = list(db.scalars(_invoice_query()))
    return dashboard_out(shop, customers, aircraft, records, invoices, today, settings.annual_window_days)


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)) -> list[CustomerOut]:
    customers = db.scalars(
        select(Customer).options(selectinload(Customer.aircraft)).order_by(Customer.name)
    )
    return [customer_out(customer) for customer in customers]


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(payload: CustomerIn, db: Session = Depends(get_db)) -> CustomerOut:
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer_out(customer)


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> CustomerOut:
    customer = _one(db, Customer, customer_id, "Owner")
    return customer_out(customer)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, payload: CustomerUpdate, db: Session = Depends(get_db)) -> CustomerOut:
    customer = _one(db, Customer, customer_id, "Owner")
    _apply(customer, payload)
    db.commit()
    db.refresh(customer)
    return customer_out(customer)


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)) -> Response:
    customer = _one(db, Customer, customer_id, "Owner")
    aircraft_count = db.scalar(
        select(func.count(Aircraft.id)).where(Aircraft.customer_id == customer.id)
    )
    if aircraft_count:
        raise HTTPException(
            status_code=409,
            detail="Remove this owner's aircraft before deleting the owner.",
        )
    db.delete(customer)
    db.commit()
    return Response(status_code=204)


@router.get("/aircraft", response_model=list[AircraftOut])
def list_aircraft(db: Session = Depends(get_db)) -> list[AircraftOut]:
    today = date.today()
    rows = db.scalars(_aircraft_query().order_by(Aircraft.registration))
    return [aircraft_out(aircraft, today) for aircraft in rows]


@router.post("/aircraft", response_model=AircraftOut, status_code=201)
def create_aircraft(payload: AircraftIn, db: Session = Depends(get_db)) -> AircraftOut:
    _one(db, Customer, payload.customer_id, "Owner")
    _reject_duplicate_registration(db, payload.registration)
    data = payload.model_dump()
    for key in ("tach_hours", "hobbs_hours", "total_time_hours"):
        if data[key] is not None:
            data[key] = quantize_hours(data[key])
    aircraft = Aircraft(**data)
    db.add(aircraft)
    db.commit()
    aircraft = db.scalar(_aircraft_query().where(Aircraft.id == aircraft.id))
    return aircraft_out(aircraft, date.today())


@router.get("/aircraft/{aircraft_id}", response_model=AircraftOut)
def get_aircraft(aircraft_id: int, db: Session = Depends(get_db)) -> AircraftOut:
    aircraft = db.scalar(_aircraft_query().where(Aircraft.id == aircraft_id))
    if aircraft is None:
        raise HTTPException(status_code=404, detail="Aircraft not found.")
    return aircraft_out(aircraft, date.today())


@router.patch("/aircraft/{aircraft_id}", response_model=AircraftOut)
def update_aircraft(
    aircraft_id: int, payload: AircraftUpdate, db: Session = Depends(get_db)
) -> AircraftOut:
    aircraft = _one(db, Aircraft, aircraft_id, "Aircraft")
    data = payload.model_dump(exclude_unset=True)
    if "customer_id" in data:
        _one(db, Customer, data["customer_id"], "Owner")
    if "registration" in data:
        _reject_duplicate_registration(db, data["registration"], aircraft.id)
    for key in ("tach_hours", "hobbs_hours", "total_time_hours"):
        if key in data and data[key] is not None:
            data[key] = quantize_hours(data[key])
    for key, value in data.items():
        setattr(aircraft, key, value)
    db.commit()
    aircraft = db.scalar(_aircraft_query().where(Aircraft.id == aircraft_id))
    return aircraft_out(aircraft, date.today())


@router.delete("/aircraft/{aircraft_id}", status_code=204)
def delete_aircraft(aircraft_id: int, db: Session = Depends(get_db)) -> Response:
    aircraft = _one(db, Aircraft, aircraft_id, "Aircraft")
    record_count = db.scalar(
        select(func.count(MaintenanceRecord.id)).where(MaintenanceRecord.aircraft_id == aircraft.id)
    )
    if record_count:
        raise HTTPException(
            status_code=409,
            detail="This aircraft has maintenance records and stays in the fleet.",
        )
    db.delete(aircraft)
    db.commit()
    return Response(status_code=204)


def _reject_duplicate_registration(db: Session, registration: str, current_id: int | None = None) -> None:
    existing = db.scalar(select(Aircraft).where(Aircraft.registration == registration))
    if existing and existing.id != current_id:
        raise HTTPException(status_code=409, detail="That N-number is already in the fleet.")


@router.get("/records", response_model=list[RecordOut])
def list_records(
    status: str | None = None,
    kind: str | None = None,
    aircraft_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[RecordOut]:
    shop = _shop(db)
    stmt = _record_query().order_by(MaintenanceRecord.opened_on.desc(), MaintenanceRecord.id.desc())
    if status:
        stmt = stmt.where(MaintenanceRecord.status == status)
    if kind:
        stmt = stmt.where(MaintenanceRecord.kind == kind)
    if aircraft_id:
        stmt = stmt.where(MaintenanceRecord.aircraft_id == aircraft_id)
    return [record_out(record, shop) for record in db.scalars(stmt)]


@router.post("/records", response_model=RecordOut, status_code=201)
def create_record(payload: RecordIn, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    aircraft = db.scalar(_aircraft_query().where(Aircraft.id == payload.aircraft_id))
    if aircraft is None:
        raise HTTPException(status_code=404, detail="Aircraft not found.")
    opened = payload.opened_on or date.today()
    record = MaintenanceRecord(
        aircraft_id=aircraft.id,
        number=next_number(db, MaintenanceRecord.number, "WO", opened),
        kind=payload.kind,
        status=payload.status,
        title=payload.title,
        discrepancy=payload.discrepancy,
        corrective_action=payload.corrective_action,
        location=payload.location or aircraft.home_airport,
        opened_on=opened,
        closed_on=date.today() if payload.status == "complete" else None,
        tach_hours=quantize_hours(payload.tach_hours) if payload.tach_hours is not None else aircraft.tach_hours,
        hobbs_hours=quantize_hours(payload.hobbs_hours) if payload.hobbs_hours is not None else aircraft.hobbs_hours,
        rating=payload.rating,
        signoff_name=shop.mechanic_name,
        certificate_ref="A&P",
        travel_hours=quantize_hours(payload.travel_hours),
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record.id))
    return record_out(record, shop)


@router.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: int, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Work order not found.")
    return record_out(record, shop)


@router.patch("/records/{record_id}", response_model=RecordOut)
def update_record(record_id: int, payload: RecordUpdate, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Work order not found.")
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and not data["title"]:
        raise HTTPException(status_code=422, detail="Title is required.")
    if "travel_hours" in data:
        updated_travel = quantize_hours(data["travel_hours"])
        if updated_travel != quantize_hours(record.travel_hours or 0):
            _ensure_unlocked(record)
        data["travel_hours"] = updated_travel
    for key in ("tach_hours", "hobbs_hours"):
        if key in data and data[key] is not None:
            data[key] = quantize_hours(data[key])
    if data.get("status") == "complete" and "closed_on" not in data and record.closed_on is None:
        data["closed_on"] = date.today()
    for key, value in data.items():
        setattr(record, key, value)
    db.commit()
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    return record_out(record, shop)


@router.delete("/records/{record_id}", status_code=204)
def delete_record(record_id: int, db: Session = Depends(get_db)) -> Response:
    record = _one(db, MaintenanceRecord, record_id, "Work order")
    if record.invoices:
        raise HTTPException(
            status_code=409,
            detail="This work order has billing history and stays on file.",
        )
    db.delete(record)
    db.commit()
    return Response(status_code=204)


@router.post("/records/{record_id}/labor", response_model=RecordOut, status_code=201)
def add_labor(record_id: int, payload: LaborIn, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    record = _one(db, MaintenanceRecord, record_id, "Work order")
    _ensure_unlocked(record)
    db.add(
        LaborLine(
            record_id=record.id,
            description=payload.description,
            hours=quantize_hours(payload.hours),
            rate_cents=payload.rate_cents,
        )
    )
    db.commit()
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    return record_out(record, shop)


@router.patch("/labor/{labor_id}", response_model=RecordOut)
def update_labor(labor_id: int, payload: LaborUpdate, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    line = _one(db, LaborLine, labor_id, "Labor line")
    _ensure_unlocked(line.record)
    data = payload.model_dump(exclude_unset=True)
    if "hours" in data:
        data["hours"] = quantize_hours(data["hours"])
    for key, value in data.items():
        setattr(line, key, value)
    record_id = line.record_id
    db.commit()
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    return record_out(record, shop)


@router.delete("/labor/{labor_id}", status_code=204)
def delete_labor(labor_id: int, db: Session = Depends(get_db)) -> Response:
    line = _one(db, LaborLine, labor_id, "Labor line")
    _ensure_unlocked(line.record)
    db.delete(line)
    db.commit()
    return Response(status_code=204)


@router.post("/records/{record_id}/parts", response_model=RecordOut, status_code=201)
def add_part(record_id: int, payload: PartIn, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    record = _one(db, MaintenanceRecord, record_id, "Work order")
    _ensure_unlocked(record)
    db.add(
        PartLine(
            record_id=record.id,
            part_number=payload.part_number or "",
            description=payload.description,
            quantity=quantize_qty(payload.quantity),
            unit_price_cents=payload.unit_price_cents,
        )
    )
    db.commit()
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    return record_out(record, shop)


@router.patch("/parts/{part_id}", response_model=RecordOut)
def update_part(part_id: int, payload: PartUpdate, db: Session = Depends(get_db)) -> RecordOut:
    shop = _shop(db)
    line = _one(db, PartLine, part_id, "Part line")
    _ensure_unlocked(line.record)
    data = payload.model_dump(exclude_unset=True)
    if "quantity" in data:
        data["quantity"] = quantize_qty(data["quantity"])
    for key, value in data.items():
        setattr(line, key, value)
    record_id = line.record_id
    db.commit()
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    return record_out(record, shop)


@router.delete("/parts/{part_id}", status_code=204)
def delete_part(part_id: int, db: Session = Depends(get_db)) -> Response:
    line = _one(db, PartLine, part_id, "Part line")
    _ensure_unlocked(line.record)
    db.delete(line)
    db.commit()
    return Response(status_code=204)


@router.post("/records/{record_id}/invoice", response_model=InvoiceOut, status_code=201)
def invoice_from_record(record_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Work order not found.")
    existing = active_invoice(record)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This work order already has {existing.number}. Void it before creating another.",
        )
    specs = lines_from_record(record, shop.default_travel_rate_cents)
    if not specs:
        raise HTTPException(
            status_code=400,
            detail="Add labor, parts, or travel before billing this work order.",
        )
    invoice = Invoice(
        number=next_number(db, Invoice.number, "INV"),
        customer_id=record.aircraft.customer_id,
        aircraft_id=record.aircraft_id,
        record_id=record.id,
        status="draft",
        voided=False,
        tax_cents=0,
        notes="",
    )
    db.add(invoice)
    db.flush()
    apply_lines(invoice, specs)
    recompute_invoice(invoice)
    db.commit()
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice.id))
    return invoice_out(invoice, shop)


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(status: str | None = None, db: Session = Depends(get_db)) -> list[InvoiceOut]:
    shop = _shop(db)
    stmt = _invoice_query().order_by(Invoice.id.desc())
    if status:
        stmt = stmt.where(Invoice.status == status)
    return [invoice_out(invoice, shop) for invoice in db.scalars(stmt)]


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return invoice_out(invoice, shop)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.voided:
        raise HTTPException(status_code=409, detail="Voided invoices stay as written.")
    data = payload.model_dump(exclude_unset=True)
    if "tax_cents" in data and invoice.issued_on is not None:
        raise HTTPException(status_code=409, detail="Tax is locked once the invoice is issued.")
    for key, value in data.items():
        setattr(invoice, key, value)
    recompute_invoice(invoice)
    db.commit()
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    return invoice_out(invoice, shop)


@router.post("/invoices/{invoice_id}/refresh", response_model=InvoiceOut)
def refresh_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.voided or invoice.issued_on is not None:
        raise HTTPException(
            status_code=409,
            detail="Issued invoices stay as written. Void the invoice if it should not stand.",
        )
    apply_lines(invoice, lines_from_record(invoice.record, shop.default_travel_rate_cents))
    recompute_invoice(invoice)
    db.commit()
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    return invoice_out(invoice, shop)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceOut)
def issue_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.voided:
        raise HTTPException(status_code=409, detail="Voided invoices cannot be issued.")
    if invoice.issued_on is not None:
        raise HTTPException(status_code=409, detail="This invoice is already issued.")
    if not invoice.lines:
        raise HTTPException(
            status_code=400,
            detail="Add labor, parts, or travel on the work order before issuing.",
        )
    invoice.issued_on = date.today()
    if invoice.due_on is None:
        invoice.due_on = invoice.issued_on + timedelta(days=shop.payment_terms_days)
    recompute_invoice(invoice)
    db.commit()
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    return invoice_out(invoice, shop)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceOut)
def void_invoice(invoice_id: int, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if not invoice.voided and invoice.payments:
        raise HTTPException(
            status_code=409,
            detail="Remove the payments on this invoice before voiding it.",
        )
    invoice.voided = True
    recompute_invoice(invoice)
    db.commit()
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    return invoice_out(invoice, shop)


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceOut, status_code=201)
def add_payment(invoice_id: int, payload: PaymentIn, db: Session = Depends(get_db)) -> InvoiceOut:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status == "draft":
        raise HTTPException(status_code=409, detail="Issue the invoice before recording a payment.")
    if invoice.voided or invoice.status in {"paid", "void"}:
        raise HTTPException(status_code=409, detail="This invoice is not open for payment.")
    due = amount_due_cents(invoice)
    if payload.amount_cents > due:
        raise HTTPException(status_code=400, detail="That payment is more than the balance due.")
    db.add(
        Payment(
            invoice_id=invoice.id,
            paid_on=payload.paid_on or date.today(),
            amount_cents=payload.amount_cents,
            method=payload.method,
            reference=payload.reference,
        )
    )
    db.flush()
    db.refresh(invoice)
    recompute_invoice(invoice)
    db.commit()
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    return invoice_out(invoice, shop)


@router.delete("/payments/{payment_id}", status_code=204)
def delete_payment(payment_id: int, db: Session = Depends(get_db)) -> Response:
    payment = _one(db, Payment, payment_id, "Payment")
    invoice = payment.invoice
    if invoice.voided:
        raise HTTPException(status_code=409, detail="Voided invoices stay as written.")
    db.delete(payment)
    db.flush()
    db.refresh(invoice)
    recompute_invoice(invoice)
    db.commit()
    return Response(status_code=204)


@router.get("/present/aircraft/{aircraft_id}", response_model=PresentAircraft)
def present_aircraft_view(aircraft_id: int, db: Session = Depends(get_db)) -> PresentAircraft:
    shop = _shop(db)
    aircraft = db.scalar(_aircraft_query().where(Aircraft.id == aircraft_id))
    if aircraft is None:
        raise HTTPException(status_code=404, detail="Aircraft not found.")
    return present_aircraft(shop, aircraft, date.today())


@router.get("/present/records/{record_id}", response_model=PresentRecord)
def present_record_view(record_id: int, db: Session = Depends(get_db)) -> PresentRecord:
    shop = _shop(db)
    record = db.scalar(_record_query().where(MaintenanceRecord.id == record_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Work order not found.")
    return present_record(shop, record, date.today())


@router.get("/present/invoices/{invoice_id}", response_model=PresentInvoice)
def present_invoice_view(invoice_id: int, db: Session = Depends(get_db)) -> PresentInvoice:
    shop = _shop(db)
    invoice = db.scalar(_invoice_query().where(Invoice.id == invoice_id))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return present_invoice(shop, invoice, date.today())
