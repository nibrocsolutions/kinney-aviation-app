"""Labor, parts, and travel on a work order become the invoice."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")
TENTH = Decimal("0.1")
WHOLE = Decimal("1")


def as_decimal(value: Decimal | float | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def quantize_hours(value: Decimal | float | int | str) -> Decimal:
    return as_decimal(value).quantize(TENTH, rounding=ROUND_HALF_UP)


def quantize_qty(value: Decimal | float | int | str) -> Decimal:
    return as_decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def line_amount(quantity: Decimal | float | int | str, unit_cents: int) -> int:
    if unit_cents < 0:
        raise ValueError("Unit price cannot be negative.")
    quantity_dec = as_decimal(quantity)
    if quantity_dec < 0:
        raise ValueError("Quantity cannot be negative.")
    raw = (quantity_dec * Decimal(unit_cents)).quantize(WHOLE, rounding=ROUND_HALF_UP)
    return int(raw)


def derive_status(*, voided: bool, issued: bool, total_cents: int, paid_cents: int) -> str:
    if voided:
        return "void"
    if not issued:
        return "draft"
    balance = total_cents - paid_cents
    if balance <= 0:
        return "paid"
    if paid_cents > 0:
        return "partial"
    return "issued"


@dataclass(frozen=True)
class LineSpec:
    kind: str
    description: str
    quantity: Decimal
    unit_cents: int
    amount_cents: int

    def signature(self) -> tuple[str, str, str, int, int]:
        qty = self.quantity.quantize(TWOPLACES)
        return (self.kind, self.description, format(qty, "f"), self.unit_cents, self.amount_cents)


def lines_from_record(record, travel_rate_cents: int) -> list[LineSpec]:
    """Snapshot billable work. Draft invoices can be rebuilt from this list."""
    lines: list[LineSpec] = []
    for labor in sorted(record.labor_lines, key=lambda row: row.id or 0):
        qty = quantize_qty(quantize_hours(labor.hours))
        lines.append(
            LineSpec(
                "labor",
                labor.description.strip(),
                qty,
                labor.rate_cents,
                line_amount(qty, labor.rate_cents),
            )
        )
    for part in sorted(record.part_lines, key=lambda row: row.id or 0):
        qty = quantize_qty(part.quantity)
        label = part.description.strip()
        if part.part_number and part.part_number.strip():
            label = f"{part.part_number.strip()} — {label}"
        lines.append(
            LineSpec(
                "part",
                label,
                qty,
                part.unit_price_cents,
                line_amount(qty, part.unit_price_cents),
            )
        )
    travel = quantize_hours(record.travel_hours or 0)
    if travel > 0:
        qty = quantize_qty(travel)
        place = (record.location or "Arizona").strip() or "Arizona"
        lines.append(
            LineSpec(
                "travel",
                f"Pilot-mechanic travel · {place}",
                qty,
                travel_rate_cents,
                line_amount(qty, travel_rate_cents),
            )
        )
    return lines


def invoice_totals(invoice) -> tuple[int, int, int]:
    subtotal = sum(line.amount_cents for line in invoice.lines)
    tax = invoice.tax_cents or 0
    paid = sum(payment.amount_cents for payment in invoice.payments)
    return subtotal, subtotal + tax, paid


def recompute_invoice(invoice) -> None:
    _subtotal, total, paid = invoice_totals(invoice)
    invoice.status = derive_status(
        voided=bool(invoice.voided),
        issued=invoice.issued_on is not None,
        total_cents=total,
        paid_cents=paid,
    )


def amount_due_cents(invoice) -> int:
    if invoice.voided or invoice.issued_on is None:
        return 0
    _subtotal, total, paid = invoice_totals(invoice)
    return max(total - paid, 0)


def stored_line_signature(invoice) -> list[tuple[str, str, str, int, int]]:
    rows = sorted(invoice.lines, key=lambda line: (line.sort_order, line.id or 0))
    signature: list[tuple[str, str, str, int, int]] = []
    for line in rows:
        qty = quantize_qty(line.quantity)
        signature.append(
            (line.kind, line.description, format(qty, "f"), line.unit_cents, line.amount_cents)
        )
    return signature


def invoice_is_stale(record, invoice, travel_rate_cents: int) -> bool:
    if invoice.voided or invoice.issued_on is not None:
        return False
    expected = [line.signature() for line in lines_from_record(record, travel_rate_cents)]
    return expected != stored_line_signature(invoice)


def apply_lines(invoice, specs: list[LineSpec]) -> None:
    invoice.lines.clear()
    for index, spec in enumerate(specs):
        invoice.lines.append(
            _line_model()(
                kind=spec.kind,
                description=spec.description,
                quantity=spec.quantity,
                unit_cents=spec.unit_cents,
                amount_cents=spec.amount_cents,
                sort_order=index,
            )
        )


def _line_model():
    from app.models import InvoiceLine

    return InvoiceLine
