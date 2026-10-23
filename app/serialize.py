"""API shapes for records, invoices, and the presentation layer."""

from datetime import date

from app.billing import (
    amount_due_cents,
    invoice_is_stale,
    invoice_totals,
    line_amount,
    lines_from_record,
    quantize_hours,
    quantize_qty,
)
from app.models import Aircraft, Customer, Invoice, MaintenanceRecord, Shop
from app.schedule import days_until
from app.schemas import (
    AircraftOut,
    AnnualBrief,
    CustomerOut,
    DashboardOut,
    InvoiceBrief,
    InvoiceLineOut,
    InvoiceOut,
    InvoiceRef,
    LaborOut,
    PartOut,
    PaymentOut,
    PresentAircraft,
    PresentInvoice,
    PresentRecord,
    RecordBrief,
    RecordOut,
    ShopOut,
)


def active_invoice(record: MaintenanceRecord) -> Invoice | None:
    open_invoices = [invoice for invoice in record.invoices if not invoice.voided]
    if not open_invoices:
        return None
    return max(open_invoices, key=lambda invoice: invoice.id)


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        city=customer.city,
        notes=customer.notes,
        aircraft_count=len(customer.aircraft),
    )


def _hours(value) -> float | None:
    if value is None:
        return None
    return float(quantize_hours(value))


def aircraft_out(aircraft: Aircraft, today: date) -> AircraftOut:
    balance = sum(amount_due_cents(invoice) for invoice in aircraft.invoices)
    open_count = sum(1 for record in aircraft.records if record.status != "complete")
    return AircraftOut(
        id=aircraft.id,
        customer_id=aircraft.customer_id,
        customer_name=aircraft.customer.name,
        registration=aircraft.registration,
        make=aircraft.make,
        model=aircraft.model,
        serial_number=aircraft.serial_number,
        year_manufactured=aircraft.year_manufactured,
        engine_model=aircraft.engine_model,
        tach_hours=_hours(aircraft.tach_hours),
        hobbs_hours=_hours(aircraft.hobbs_hours),
        total_time_hours=_hours(aircraft.total_time_hours),
        home_airport=aircraft.home_airport,
        annual_due=aircraft.annual_due,
        days_to_annual=days_until(aircraft.annual_due, today),
        notes=aircraft.notes,
        open_record_count=open_count,
        balance_cents=balance,
    )


def record_out(record: MaintenanceRecord, shop: Shop) -> RecordOut:
    rate = shop.default_travel_rate_cents
    specs = lines_from_record(record, rate)
    labor_cents = sum(spec.amount_cents for spec in specs if spec.kind == "labor")
    parts_cents = sum(spec.amount_cents for spec in specs if spec.kind == "part")
    travel_cents = sum(spec.amount_cents for spec in specs if spec.kind == "travel")
    invoice = active_invoice(record)
    invoice_ref = None
    if invoice is not None:
        invoice_ref = InvoiceRef(
            id=invoice.id,
            number=invoice.number,
            status=invoice.status,
            stale=invoice_is_stale(record, invoice, rate),
        )
    aircraft = record.aircraft
    return RecordOut(
        id=record.id,
        number=record.number,
        aircraft_id=aircraft.id,
        registration=aircraft.registration,
        aircraft_label=f"{aircraft.make} {aircraft.model}",
        customer_id=aircraft.customer_id,
        customer_name=aircraft.customer.name,
        kind=record.kind,
        status=record.status,
        title=record.title,
        discrepancy=record.discrepancy or "",
        corrective_action=record.corrective_action or "",
        location=record.location,
        opened_on=record.opened_on,
        closed_on=record.closed_on,
        tach_hours=_hours(record.tach_hours),
        hobbs_hours=_hours(record.hobbs_hours),
        rating=record.rating,
        signoff_name=record.signoff_name or "",
        certificate_ref=record.certificate_ref or "",
        travel_hours=float(quantize_hours(record.travel_hours or 0)),
        travel_rate_cents=rate,
        rts_statement=record.rts_statement or "",
        notes=record.notes,
        labor_lines=[
            LaborOut(
                id=line.id,
                description=line.description,
                hours=float(quantize_hours(line.hours)),
                rate_cents=line.rate_cents,
                amount_cents=line_amount(line.hours, line.rate_cents),
            )
            for line in sorted(record.labor_lines, key=lambda row: row.id)
        ],
        part_lines=[
            PartOut(
                id=line.id,
                part_number=line.part_number or "",
                description=line.description,
                quantity=float(quantize_qty(line.quantity)),
                unit_price_cents=line.unit_price_cents,
                amount_cents=line_amount(line.quantity, line.unit_price_cents),
            )
            for line in sorted(record.part_lines, key=lambda row: row.id)
        ],
        labor_cents=labor_cents,
        parts_cents=parts_cents,
        travel_cents=travel_cents,
        total_cents=labor_cents + parts_cents + travel_cents,
        has_billing=bool(record.invoices),
        invoice=invoice_ref,
    )


def invoice_out(invoice: Invoice, shop: Shop) -> InvoiceOut:
    subtotal, total, paid = invoice_totals(invoice)
    balance = 0 if invoice.voided else max(total - paid, 0)
    record = invoice.record
    aircraft = invoice.aircraft
    return InvoiceOut(
        id=invoice.id,
        number=invoice.number,
        customer_id=invoice.customer_id,
        customer_name=invoice.customer.name,
        aircraft_id=aircraft.id,
        registration=aircraft.registration,
        aircraft_label=f"{aircraft.make} {aircraft.model}",
        record_id=record.id,
        record_number=record.number,
        record_title=record.title,
        status=invoice.status,
        issued_on=invoice.issued_on,
        due_on=invoice.due_on,
        tax_cents=invoice.tax_cents or 0,
        notes=invoice.notes or "",
        lines=[
            InvoiceLineOut(
                id=line.id,
                kind=line.kind,
                description=line.description,
                quantity=float(quantize_qty(line.quantity)),
                unit_cents=line.unit_cents,
                amount_cents=line.amount_cents,
            )
            for line in sorted(invoice.lines, key=lambda row: (row.sort_order, row.id))
        ],
        payments=[
            PaymentOut(
                id=payment.id,
                paid_on=payment.paid_on,
                amount_cents=payment.amount_cents,
                method=payment.method,
                reference=payment.reference or "",
            )
            for payment in sorted(invoice.payments, key=lambda row: (row.paid_on, row.id))
        ],
        subtotal_cents=subtotal,
        total_cents=total,
        paid_cents=paid,
        balance_cents=balance,
        amount_due_cents=amount_due_cents(invoice),
        stale=invoice_is_stale(record, invoice, shop.default_travel_rate_cents),
    )


def dashboard_out(
    shop: Shop,
    customers: list[Customer],
    aircraft: list[Aircraft],
    records: list[MaintenanceRecord],
    invoices: list[Invoice],
    today: date,
    window_days: int,
) -> DashboardOut:
    open_records = [record for record in records if record.status != "complete"]
    annuals: list[AnnualBrief] = []
    for item in aircraft:
        remaining = days_until(item.annual_due, today)
        if item.annual_due is None or remaining is None or remaining > window_days:
            continue
        annuals.append(
            AnnualBrief(
                aircraft_id=item.id,
                registration=item.registration,
                make=item.make,
                model=item.model,
                home_airport=item.home_airport,
                customer_name=item.customer.name,
                annual_due=item.annual_due,
                days_remaining=remaining,
            )
        )
    annuals.sort(key=lambda row: (row.days_remaining, row.registration))

    recent = sorted(records, key=lambda row: (row.opened_on, row.id), reverse=True)[:8]
    collectible = [
        invoice for invoice in invoices if invoice.status in {"issued", "partial"}
    ]
    collectible.sort(key=lambda row: (row.due_on or date.max, row.number))
    drafts = [invoice for invoice in invoices if invoice.status == "draft"]

    return DashboardOut(
        shop=ShopOut.model_validate(shop),
        open_work=len(open_records),
        awaiting_parts=sum(1 for record in records if record.status == "awaiting_parts"),
        fleet_count=len(aircraft),
        customer_count=len(customers),
        receivables_cents=sum(amount_due_cents(invoice) for invoice in collectible),
        draft_cents=sum(invoice_totals(invoice)[1] for invoice in drafts),
        unbilled_count=sum(1 for record in records if active_invoice(record) is None),
        annuals=annuals,
        recent_records=[_record_brief(record, shop) for record in recent],
        open_invoices=[_invoice_brief(invoice) for invoice in collectible],
    )


def _record_brief(record: MaintenanceRecord, shop: Shop) -> RecordBrief:
    full = record_out(record, shop)
    return RecordBrief(
        id=record.id,
        number=record.number,
        registration=record.aircraft.registration,
        title=record.title,
        kind=record.kind,
        status=record.status,
        opened_on=record.opened_on,
        total_cents=full.total_cents,
    )


def _invoice_brief(invoice: Invoice) -> InvoiceBrief:
    _subtotal, total, _paid = invoice_totals(invoice)
    return InvoiceBrief(
        id=invoice.id,
        number=invoice.number,
        registration=invoice.aircraft.registration,
        customer_name=invoice.customer.name,
        status=invoice.status,
        total_cents=total,
        amount_due_cents=amount_due_cents(invoice),
        due_on=invoice.due_on,
    )


def present_aircraft(
    shop: Shop, aircraft: Aircraft, today: date
) -> PresentAircraft:
    records = sorted(aircraft.records, key=lambda row: (row.opened_on, row.id), reverse=True)
    rendered = [record_out(record, shop) for record in records]
    invoices = sorted(aircraft.invoices, key=lambda row: row.id, reverse=True)
    invoice_rows = [invoice_out(invoice, shop) for invoice in invoices]
    return PresentAircraft(
        shop=ShopOut.model_validate(shop),
        generated_on=today,
        aircraft=aircraft_out(aircraft, today),
        open_items=[row for row in rendered if row.status != "complete"],
        logbook=rendered,
        invoices=invoice_rows,
        # Drafts are not receivables yet, but the owner sheet still shows that money.
        open_balance_cents=sum(row.balance_cents for row in invoice_rows),
    )


def present_record(shop: Shop, record: MaintenanceRecord, today: date) -> PresentRecord:
    return PresentRecord(
        shop=ShopOut.model_validate(shop),
        generated_on=today,
        record=record_out(record, shop),
    )


def present_invoice(shop: Shop, invoice: Invoice, today: date) -> PresentInvoice:
    return PresentInvoice(
        shop=ShopOut.model_validate(shop),
        generated_on=today,
        invoice=invoice_out(invoice, shop),
    )
