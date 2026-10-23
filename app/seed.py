"""First-run shop profile and a demonstration Arizona fleet."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing import invoice_totals, lines_from_record, recompute_invoice
from app.config import settings
from app.models import (
    Aircraft,
    Customer,
    Invoice,
    InvoiceLine,
    LaborLine,
    MaintenanceRecord,
    PartLine,
    Payment,
    Shop,
)
from app.numbers import next_number


def ensure_shop(db: Session) -> Shop:
    shop = db.scalar(select(Shop).limit(1))
    if shop:
        return shop
    shop = Shop(
        business_name="Kinney Aviation",
        mechanic_name="Ron Kinney",
        certificate_label="FAA Airframe & Powerplant",
        phone="(480) 555-0140",
        email="contact@kinneyaviation.example",
        base_city="Arizona",
        default_labor_rate_cents=12500,
        default_travel_rate_cents=9500,
        payment_terms_days=15,
        demo_seeded=False,
    )
    db.add(shop)
    db.flush()
    return shop


def seed_database(db: Session) -> None:
    shop = ensure_shop(db)
    if settings.seed_demo and db.scalar(select(func.count(Customer.id))) == 0:
        _load_demo(db, shop)
        shop.demo_seeded = True
    db.commit()


def _invoice_from(db: Session, shop: Shop, record: MaintenanceRecord, **fields) -> Invoice:
    aircraft = record.aircraft
    invoice = Invoice(
        number=next_number(db, Invoice.number, "INV", record.closed_on or record.opened_on),
        customer_id=aircraft.customer_id,
        aircraft_id=aircraft.id,
        record_id=record.id,
        tax_cents=0,
        voided=False,
        notes=fields.pop("notes", ""),
        **fields,
    )
    db.add(invoice)
    db.flush()
    for index, spec in enumerate(lines_from_record(record, shop.default_travel_rate_cents)):
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                kind=spec.kind,
                description=spec.description,
                quantity=spec.quantity,
                unit_cents=spec.unit_cents,
                amount_cents=spec.amount_cents,
                sort_order=index,
            )
        )
    db.flush()
    db.refresh(invoice)
    return invoice


def _load_demo(db: Session, shop: Shop) -> None:
    elena = Customer(
        name="Elena Vasquez",
        email="elena.vasquez@example.com",
        phone="(928) 555-0142",
        city="Flagstaff",
        notes="Prefers work at Pulliam when the weather holds.",
    )
    marcus = Customer(
        name="Marcus Hale",
        email="marcus.hale@example.com",
        phone="(928) 555-0177",
        city="Prescott",
    )
    club = Customer(
        name="Desert Ridge Flying Club",
        email="dispatch@desertridge.example",
        phone="(480) 555-0194",
        city="Scottsdale",
        notes="Club dispatch approves squawks before work starts.",
    )
    aisha = Customer(
        name="Aisha Rahman",
        email="aisha.rahman@example.com",
        phone="(520) 555-0160",
        city="Tucson",
    )
    db.add_all([elena, marcus, club, aisha])
    db.flush()

    skyhawk = Aircraft(
        customer_id=elena.id,
        registration="N5183K",
        make="Cessna",
        model="172S",
        serial_number="172S10483",
        year_manufactured=2008,
        engine_model="Lycoming IO-360-L2A",
        tach_hours=1842.6,
        hobbs_hours=2104.3,
        total_time_hours=1842.6,
        home_airport="KFLG",
        annual_due=date(2026, 12, 1),
    )
    archer = Aircraft(
        customer_id=marcus.id,
        registration="N8146Q",
        make="Piper",
        model="PA-28-181",
        serial_number="2843561",
        year_manufactured=2001,
        engine_model="Lycoming O-360-A4M",
        tach_hours=4210.2,
        hobbs_hours=4388.0,
        total_time_hours=4210.2,
        home_airport="KPRC",
        annual_due=date(2027, 3, 31),
    )
    bonanza = Aircraft(
        customer_id=club.id,
        registration="N35DR",
        make="Beechcraft",
        model="V35B",
        serial_number="D-10218",
        year_manufactured=1978,
        engine_model="Continental IO-520-BB",
        tach_hours=3126.8,
        hobbs_hours=3301.4,
        total_time_hours=3126.8,
        home_airport="KSDL",
        annual_due=date(2026, 11, 20),
        notes="Club aircraft. Ferry only when the PIC is current in type.",
    )
    cirrus = Aircraft(
        customer_id=aisha.id,
        registration="N22AZ",
        make="Cirrus",
        model="SR22",
        serial_number="1842",
        year_manufactured=2012,
        engine_model="Continental IO-550-N",
        tach_hours=968.4,
        hobbs_hours=1102.1,
        total_time_hours=968.4,
        home_airport="KTUS",
        annual_due=date(2026, 10, 30),
    )
    db.add_all([skyhawk, archer, bonanza, cirrus])
    db.flush()

    annual = MaintenanceRecord(
        aircraft_id=archer.id,
        number=next_number(db, MaintenanceRecord.number, "WO", date(2026, 3, 2)),
        kind="annual",
        status="complete",
        title="Annual inspection",
        discrepancy="Annual inspection due. Owner reports slight right brake drag.",
        corrective_action="Completed the annual inspection. Cleaned and adjusted the right brake. No other airworthy items found.",
        location="KPRC",
        opened_on=date(2026, 3, 2),
        closed_on=date(2026, 3, 6),
        tach_hours=4198.4,
        hobbs_hours=4360.0,
        rating="AP",
        signoff_name=shop.mechanic_name,
        certificate_ref="A&P",
        travel_hours=0,
        rts_statement=(
            "I certify that this aircraft has been inspected in accordance with an annual "
            "inspection and was determined to be in airworthy condition."
        ),
    )
    db.add(annual)
    db.flush()
    annual.labor_lines = [
        LaborLine(description="Annual inspection", hours=12.0, rate_cents=12500),
        LaborLine(description="Right brake clean and adjust", hours=1.5, rate_cents=12500),
    ]
    annual.part_lines = [
        PartLine(part_number="AA48110-2", description="Oil filter", quantity=1, unit_price_cents=4250),
        PartLine(part_number="XC2050", description="Engine oil", quantity=12, unit_price_cents=1100),
    ]
    db.flush()
    paid = _invoice_from(
        db,
        shop,
        annual,
        issued_on=date(2026, 3, 6),
        due_on=date(2026, 3, 21),
        notes="Paid at delivery in Prescott.",
    )
    _, paid_total, _ = invoice_totals(paid)
    db.add(
        Payment(
            invoice_id=paid.id,
            paid_on=date(2026, 3, 10),
            amount_cents=paid_total,
            method="check",
            reference="1038",
        )
    )
    db.flush()
    db.refresh(paid)
    recompute_invoice(paid)

    ferry = MaintenanceRecord(
        aircraft_id=bonanza.id,
        number=next_number(db, MaintenanceRecord.number, "WO", date(2026, 3, 6)),
        kind="ferry",
        status="complete",
        title="Reposition KPRC to KSDL",
        discrepancy="Club asked for the airplane back at Scottsdale after the Prescott stop.",
        corrective_action="Preflight completed. Aircraft flown from KPRC to KSDL and delivered to club dispatch.",
        location="KSDL",
        opened_on=date(2026, 3, 6),
        closed_on=date(2026, 3, 6),
        tach_hours=3088.0,
        hobbs_hours=3255.2,
        rating="AP",
        signoff_name=shop.mechanic_name,
        certificate_ref="A&P",
        travel_hours=1.8,
        rts_statement="Aircraft repositioned and delivered. No maintenance discrepancy remains open from this flight.",
    )
    db.add(ferry)
    db.flush()
    ferry.labor_lines = [LaborLine(description="Preflight and delivery", hours=0.5, rate_cents=12500)]
    db.flush()
    partial = _invoice_from(
        db,
        shop,
        ferry,
        issued_on=date(2026, 3, 6),
        due_on=date(2026, 3, 21),
        notes="Club paid a deposit. Balance remains open.",
    )
    db.add(Payment(invoice_id=partial.id, paid_on=date(2026, 3, 7), amount_cents=10000, method="check", reference="1042"))
    db.flush()
    db.refresh(partial)
    recompute_invoice(partial)

    ad = MaintenanceRecord(
        aircraft_id=cirrus.id,
        number=next_number(db, MaintenanceRecord.number, "WO", date(2026, 9, 12)),
        kind="ad",
        status="complete",
        title="Exhaust AD compliance",
        discrepancy="Exhaust airworthiness directive requires inspection and clamp replacement.",
        corrective_action="Inspected the exhaust per the AD. Replaced clamps and heat shields. No cracks found.",
        location="KTUS",
        opened_on=date(2026, 9, 12),
        closed_on=date(2026, 9, 12),
        tach_hours=940.0,
        hobbs_hours=1068.5,
        rating="P",
        signoff_name=shop.mechanic_name,
        certificate_ref="A&P",
        travel_hours=2.2,
        rts_statement="The work described above was performed and the aircraft is approved for return to service with respect to that work.",
    )
    db.add(ad)
    db.flush()
    ad.labor_lines = [
        LaborLine(description="Exhaust AD inspection and clamp replacement", hours=3.5, rate_cents=12500)
    ]
    ad.part_lines = [
        PartLine(part_number="AD-CLAMP-KIT", description="Exhaust clamp and shield kit", quantity=1, unit_price_cents=21500)
    ]
    db.flush()
    issued = _invoice_from(
        db,
        shop,
        ad,
        issued_on=date(2026, 9, 12),
        due_on=date(2026, 9, 27),
        notes="Invoice left with the owner at Tucson.",
    )
    recompute_invoice(issued)

    skyhawk_annual = MaintenanceRecord(
        aircraft_id=skyhawk.id,
        number=next_number(db, MaintenanceRecord.number, "WO", date(2026, 10, 18)),
        kind="annual",
        status="in_work",
        title="Annual inspection",
        discrepancy="Annual inspection due. Nosewheel shimmy above about 15 knots.",
        corrective_action="Inspection opened. Shimmy damper ordered.",
        location="KFLG",
        opened_on=date(2026, 10, 18),
        tach_hours=1842.6,
        hobbs_hours=2104.3,
        rating="AP",
        signoff_name=shop.mechanic_name,
        certificate_ref="A&P",
        travel_hours=1.0,
    )
    db.add(skyhawk_annual)
    db.flush()
    skyhawk_annual.labor_lines = [
        LaborLine(description="Annual inspection, open and inspect", hours=6.0, rate_cents=12500)
    ]
    skyhawk_annual.part_lines = [
        PartLine(part_number="SHIMMY-172", description="Nosewheel shimmy damper", quantity=1, unit_price_cents=18640)
    ]
    db.flush()
    draft = _invoice_from(db, shop, skyhawk_annual, notes="Annual opened at Flagstaff. Shimmy damper is on order.")
    recompute_invoice(draft)

    oil = MaintenanceRecord(
        aircraft_id=bonanza.id,
        number=next_number(db, MaintenanceRecord.number, "WO", date(2026, 10, 20)),
        kind="oil",
        status="awaiting_parts",
        title="Oil change and magneto inspection",
        discrepancy="500-hour magneto inspection is due, along with oil and filter.",
        corrective_action="Oil and filter replaced. Magnetos removed and sent for overhaul.",
        location="KSDL",
        opened_on=date(2026, 10, 20),
        tach_hours=3126.8,
        hobbs_hours=3301.4,
        rating="P",
        signoff_name=shop.mechanic_name,
        certificate_ref="A&P",
        travel_hours=0,
    )
    db.add(oil)
    db.flush()
    oil.labor_lines = [LaborLine(description="Oil service and magneto removal", hours=2.0, rate_cents=12500)]
    oil.part_lines = [
        PartLine(part_number="AA48110-2", description="Oil filter", quantity=1, unit_price_cents=4250),
        PartLine(part_number="XC2050", description="Engine oil", quantity=8, unit_price_cents=1100),
        PartLine(part_number="4371-OH", description="Magneto overhaul", quantity=2, unit_price_cents=128500),
    ]
    db.flush()
