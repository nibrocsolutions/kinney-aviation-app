from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.billing import derive_status, line_amount, lines_from_record
from app.schedule import annual_is_due, days_until


def test_line_amount_uses_tenths_and_rounds_half_up():
    assert line_amount(Decimal("2.5"), 12500) == 31250
    assert line_amount(Decimal("1.5"), 12500) == 18750
    assert line_amount(Decimal("12"), 1100) == 13200
    assert line_amount(Decimal("2.2"), 9500) == 20900
    assert line_amount(1.5, 12500) == 18750


def test_invoice_status_follows_the_balance():
    assert derive_status(voided=False, issued=False, total_cents=10000, paid_cents=0) == "draft"
    assert derive_status(voided=False, issued=True, total_cents=10000, paid_cents=0) == "issued"
    assert derive_status(voided=False, issued=True, total_cents=10000, paid_cents=4000) == "partial"
    assert derive_status(voided=False, issued=True, total_cents=10000, paid_cents=10000) == "paid"
    assert derive_status(voided=True, issued=True, total_cents=10000, paid_cents=0) == "void"


def test_lines_from_record_roll_labor_parts_and_travel_into_one_bill():
    record = SimpleNamespace(
        labor_lines=[
            SimpleNamespace(id=1, description="Annual inspection", hours=Decimal("12.0"), rate_cents=12500),
            SimpleNamespace(id=2, description="Right brake clean and adjust", hours=Decimal("1.5"), rate_cents=12500),
        ],
        part_lines=[
            SimpleNamespace(
                id=1,
                part_number="AA48110-2",
                description="Oil filter",
                quantity=Decimal("1"),
                unit_price_cents=4250,
            ),
            SimpleNamespace(
                id=2,
                part_number="XC2050",
                description="Engine oil",
                quantity=Decimal("12"),
                unit_price_cents=1100,
            ),
        ],
        travel_hours=Decimal("0"),
        location="KPRC",
    )
    lines = lines_from_record(record, 9500)
    assert [line.kind for line in lines] == ["labor", "labor", "part", "part"]
    assert lines[2].description == "AA48110-2 — Oil filter"
    assert sum(line.amount_cents for line in lines) == 186200

    record.travel_hours = Decimal("2.2")
    record.location = "KTUS"
    with_travel = lines_from_record(record, 9500)
    assert with_travel[-1].kind == "travel"
    assert with_travel[-1].description == "Pilot-mechanic travel · KTUS"
    assert with_travel[-1].amount_cents == 20900


def test_annual_window_includes_overdue_aircraft():
    today = date(2026, 10, 23)
    assert days_until(date(2026, 10, 30), today) == 7
    assert days_until(date(2026, 10, 1), today) == -22
    assert annual_is_due(date(2026, 12, 1), today, 60) is True
    assert annual_is_due(date(2027, 3, 31), today, 60) is False
    assert annual_is_due(None, today, 60) is False
