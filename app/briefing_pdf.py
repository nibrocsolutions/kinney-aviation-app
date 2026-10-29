"""Aircraft briefing as a downloadable PDF. Standard fonts, no extra packages."""

from dataclasses import dataclass
from datetime import date

from app.schemas import PresentAircraft

PAGE_W = 612
PAGE_H = 792
MARGIN_X = 54
MARGIN_BOTTOM = 48
CONTENT_W = PAGE_W - MARGIN_X * 2

NAVY = (11 / 255, 31 / 255, 58 / 255)
BRASS = (154 / 255, 123 / 255, 47 / 255)
INK = (16 / 255, 38 / 255, 61 / 255)
STEEL = (74 / 255, 101 / 255, 120 / 255)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_KINDS = {
    "annual": "Annual",
    "hundred_hour": "100-hour",
    "repair": "Repair",
    "ad": "AD / SB",
    "oil": "Oil service",
    "ferry": "Ferry",
    "other": "Other",
}
_RECORD_STATUS = {
    "open": "Open",
    "in_work": "In work",
    "awaiting_parts": "Awaiting parts",
    "complete": "Complete",
}
_INVOICE_STATUS = {
    "draft": "Draft",
    "issued": "Issued",
    "partial": "Partial",
    "paid": "Paid",
    "void": "Void",
}


@dataclass
class _Span:
    text: str
    size: float = 11
    bold: bool = False
    color: tuple[float, float, float] = INK
    before: float = 2
    after: float = 2
    rule: bool = False


def briefing_pdf(sheet: PresentAircraft) -> bytes:
    aircraft = sheet.aircraft
    spans = _briefing_spans(sheet)
    pages = _paginate(spans, aircraft.registration)
    streams = [_paint(page, index + 1, len(pages)) for index, page in enumerate(pages)]
    return _document(streams)


def _briefing_spans(sheet: PresentAircraft) -> list[_Span]:
    shop = sheet.shop
    aircraft = sheet.aircraft
    money_rows = [row for row in sheet.invoices if row.status != "void"]
    open_balance = sum(row.balance_cents for row in money_rows)
    identity = " ".join(
        part
        for part in (
            str(aircraft.year_manufactured or ""),
            aircraft.make,
            aircraft.model,
        )
        if part
    )
    extras = []
    if aircraft.serial_number:
        extras.append(f"S/N {aircraft.serial_number}")
    if aircraft.home_airport:
        extras.append(aircraft.home_airport)
    subtitle = identity
    if extras:
        subtitle = f"{identity} · {' · '.join(extras)}" if identity else " · ".join(extras)

    spans = [
        _Span(_plain(shop.business_name), size=16, bold=True, color=NAVY, before=0, after=2),
        _Span(
            _plain(f"{shop.certificate_label} · {shop.base_city}"),
            size=9,
            color=BRASS,
            before=0,
            after=1,
        ),
        _Span(
            _plain(" · ".join(part for part in (shop.phone, shop.email, _date(sheet.generated_on)) if part)),
            size=9,
            color=STEEL,
            before=0,
            after=8,
        ),
        _Span("Aircraft briefing", size=10, bold=True, color=BRASS, before=2, after=4),
        _Span(_plain(aircraft.registration), size=22, bold=True, color=NAVY, before=0, after=2),
        _Span(_plain(subtitle), size=11, color=INK, before=0, after=10),
        _Span(f"Owner: {_plain(aircraft.customer_name)}", before=1),
        _Span(f"Tach / Hobbs: {_hours(aircraft.tach_hours)} / {_hours(aircraft.hobbs_hours)}"),
        _Span(f"Total time: {_hours(aircraft.total_time_hours)}"),
        _Span(f"Engine: {_plain(aircraft.engine_model) or '-'}"),
        _Span(f"Annual: {_annual(aircraft)}"),
        _Span(f"Open balance: {_money(open_balance)}", bold=True, before=4, after=8),
        _Span("Open items", size=13, bold=True, color=NAVY, before=12, after=6),
    ]
    if sheet.open_items:
        for item in sheet.open_items:
            kind = _KINDS.get(item.kind, item.kind)
            status = _RECORD_STATUS.get(item.status, item.status)
            spans.append(_Span(f"{item.number} · {kind} · {status}", bold=True, before=6, after=1))
            spans.append(_Span(_clip(item.discrepancy or item.title), color=STEEL, before=0))
    else:
        spans.append(_Span("No open discrepancies.", color=STEEL))

    spans.append(_Span("Log", size=13, bold=True, color=NAVY, before=14, after=6))
    if sheet.logbook:
        for item in sheet.logbook:
            kind = _KINDS.get(item.kind, item.kind)
            when = _date(item.closed_on or item.opened_on)
            signed = _plain(item.signoff_name) or "-"
            spans.append(_Span(f"{when} · {item.number} · {kind} · {signed}", bold=True, before=6, after=1))
            spans.append(_Span(_clip(item.corrective_action or item.discrepancy or item.title), color=STEEL, before=0))
    else:
        spans.append(_Span("No log entries yet.", color=STEEL))

    spans.append(_Span("Account", size=13, bold=True, color=NAVY, before=14, after=6))
    if money_rows:
        for invoice in money_rows:
            status = _INVOICE_STATUS.get(invoice.status, invoice.status)
            spans.append(
                _Span(
                    f"{invoice.number} · {status} · total {_money(invoice.total_cents)} · due {_money(invoice.balance_cents)}",
                    before=3,
                )
            )
    else:
        spans.append(_Span("No invoices on file.", color=STEEL))

    spans.append(
        _Span(
            f"Working record for {_plain(shop.mechanic_name)}. The aircraft logbook remains the official record.",
            size=9,
            color=STEEL,
            before=16,
            after=0,
        )
    )
    return spans


def _paginate(spans: list[_Span], registration: str) -> list[list[_Span]]:
    pages: list[list[_Span]] = []
    current: list[_Span] = []
    y = PAGE_H - MARGIN_X

    def continuation() -> _Span:
        return _Span(f"{registration} · Aircraft briefing", size=9, bold=True, color=NAVY, before=0, after=10)

    for span in spans:
        needed = _span_height(span)
        if current and y - needed < MARGIN_BOTTOM:
            pages.append(current)
            current = [continuation()]
            y = PAGE_H - MARGIN_X - _span_height(current[0])
        current.append(span)
        y -= needed
    if current:
        pages.append(current)
    return pages or [[_Span(registration)]]


def _span_height(span: _Span) -> float:
    lines = max(1, len(_wrap(span.text, span.size, span.bold)))
    return span.before + lines * (span.size + 3) + span.after


def _paint(spans: list[_Span], page_number: int, page_count: int) -> bytes:
    y = PAGE_H - MARGIN_X
    ops: list[str] = []
    for span in spans:
        y -= span.before
        lines = _wrap(span.text, span.size, span.bold) or [""]
        r, g, b = span.color
        font = "F2" if span.bold else "F1"
        ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        for line in lines:
            y -= span.size
            ops.append(f"BT /{font} {span.size:.1f} Tf {MARGIN_X} {y:.2f} Td ({_escape(line)}) Tj ET")
            y -= 3
        y -= span.after
    ops.append(f"{STEEL[0]:.3f} {STEEL[1]:.3f} {STEEL[2]:.3f} rg")
    ops.append(
        f"BT /F1 9 Tf {MARGIN_X} 32 Td ({_escape(f'Page {page_number} of {page_count}')}) Tj ET"
    )
    return "\n".join(ops).encode("latin-1", "replace")


def _wrap(text: str, size: float, bold: bool) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(trial, size, bold) <= CONTENT_W:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(text: str, size: float, bold: bool) -> float:
    factor = 0.56 if bold else 0.52
    return len(text) * size * factor


def _document(streams: list[bytes]) -> bytes:
    font_regular = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    font_bold = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"
    objects: list[bytes] = [b"", b"", font_regular, font_bold]
    page_ids: list[int] = []
    for stream in streams:
        content = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        objects.append(content)
        content_id = len(objects)
        page_ids.append(content_id + 1)
        objects.append(b"")  # placeholder page object
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = (
        f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode()
    )
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    for index, page_id in enumerate(page_ids):
        content_id = page_id - 1
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()
    return _serialize(objects)


def _serialize(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def _plain(value: object) -> str:
    text = str(value or "")
    for src, dest in (
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u00a0", " "),
    ):
        text = text.replace(src, dest)
    return " ".join(text.split())


def _clip(value: object, limit: int = 1200) -> str:
    text = _plain(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _escape(text: str) -> str:
    encoded = text.encode("latin-1", "replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    amount = abs(int(cents))
    return f"{sign}${amount // 100:,}.{amount % 100:02d}"


def _hours(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.1f}"


def _date(value: date | None) -> str:
    if value is None:
        return ""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _annual(aircraft) -> str:
    if aircraft.annual_due is None or aircraft.days_to_annual is None:
        return "No annual date"
    when = _date(aircraft.annual_due)
    days = aircraft.days_to_annual
    if days < 0:
        label = f"{abs(days)} days overdue"
    elif days == 0:
        label = "Due today"
    elif days == 1:
        label = "Due tomorrow"
    else:
        label = f"Due in {days} days"
    return f"{label} ({when})"
