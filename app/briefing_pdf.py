"""Aircraft briefing PDF laid out like the sheet on the Aircraft page."""

from collections.abc import Callable

from app.schemas import PresentAircraft

PAGE_W = 612.0
PAGE_H = 792.0
MARGIN_X = 42.0
MARGIN_BOTTOM = 40.0
BAR = 8.0
CONTENT_TOP = PAGE_H - BAR - 22.0
CONTENT_W = PAGE_W - MARGIN_X * 2

NAVY = (11 / 255, 31 / 255, 58 / 255)
BRASS = (196 / 255, 163 / 255, 90 / 255)
BRASS_DEEP = (154 / 255, 123 / 255, 47 / 255)
INK = (16 / 255, 38 / 255, 61 / 255)
STEEL = (74 / 255, 101 / 255, 120 / 255)
MUTED = (90 / 255, 115 / 255, 136 / 255)
CLOUD = (232 / 255, 241 / 255, 246 / 255)
LINE = (226 / 255, 228 / 255, 231 / 255)
DANGER = (140 / 255, 47 / 255, 47 / 255)

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
_DASH = "\x97"


def briefing_pdf(sheet: PresentAircraft) -> bytes:
    canvas = _Canvas(sheet.aircraft.registration)
    _draw_sheet(canvas, sheet)
    return _document(canvas.finish())


def _draw_sheet(canvas: "_Canvas", sheet: PresentAircraft) -> None:
    shop = sheet.shop
    aircraft = sheet.aircraft
    money_rows = [row for row in sheet.invoices if row.status != "void"]
    open_balance = sum(row.balance_cents for row in money_rows)
    canvas.header(
        _plain(shop.business_name),
        _plain(f"{shop.certificate_label} · {shop.base_city}"),
        [_date(sheet.generated_on), _plain(shop.phone), _plain(shop.email)],
    )
    canvas.registration(_plain(aircraft.registration))
    canvas.subtitle(_identity(aircraft))
    annual_color = NAVY
    if aircraft.days_to_annual is not None:
        if aircraft.days_to_annual < 0:
            annual_color = DANGER
        elif aircraft.days_to_annual <= 30:
            annual_color = BRASS_DEEP
    canvas.facts(
        [
            ("Owner", _plain(aircraft.customer_name), NAVY),
            ("Tach / Hobbs", f"{_hours(aircraft.tach_hours)} / {_hours(aircraft.hobbs_hours)}", NAVY),
            ("Annual", _annual(aircraft.days_to_annual), annual_color),
            ("Engine", _plain(aircraft.engine_model) or _DASH, NAVY),
            ("Total time", _hours(aircraft.total_time_hours), NAVY),
            ("Open balance", _money(open_balance), NAVY),
        ]
    )
    canvas.heading("Open items")
    if sheet.open_items:
        for item in sheet.open_items:
            kind = _KINDS.get(item.kind, item.kind)
            status = _RECORD_STATUS.get(item.status, item.status)
            canvas.card(
                f"{item.number} · {kind} · {status}",
                _plain(item.discrepancy or item.title),
            )
    else:
        canvas.paragraph("No open discrepancies.", MUTED)

    canvas.heading("Log")
    log_rows = []
    for item in sheet.logbook:
        log_rows.append(
            [
                _date(item.closed_on or item.opened_on) or _DASH,
                _plain(item.number),
                _KINDS.get(item.kind, item.kind),
                _plain(item.corrective_action or item.discrepancy or item.title),
                _plain(item.signoff_name) or _DASH,
            ]
        )
    canvas.table(
        ["Date", "Work order", "Kind", "Entry", "Signed"],
        log_rows,
        [76, 88, 72, CONTENT_W - 76 - 88 - 72 - 78, 78],
        ["left", "left", "left", "left", "left"],
    )

    canvas.heading("Account")
    if money_rows:
        canvas.table(
            ["Invoice", "Status", "Total", "Due"],
            [
                [
                    _plain(invoice.number),
                    _INVOICE_STATUS.get(invoice.status, invoice.status),
                    _money(invoice.total_cents),
                    _money(invoice.balance_cents),
                ]
                for invoice in money_rows
            ],
            [CONTENT_W - 110 - 90 - 90, 110, 90, 90],
            ["left", "left", "right", "right"],
        )
    else:
        canvas.paragraph("No invoices on file.", MUTED)

    canvas.note(
        f"Working record for {_plain(shop.mechanic_name)}. "
        "The aircraft logbook remains the official record."
    )


def _identity(aircraft) -> str:
    parts = [
        part
        for part in (str(aircraft.year_manufactured or ""), aircraft.make, aircraft.model)
        if part
    ]
    line = " ".join(parts)
    if aircraft.serial_number:
        line = f"{line} · S/N {_plain(aircraft.serial_number)}".strip(" ·")
    if aircraft.home_airport:
        line = f"{line} · {_plain(aircraft.home_airport)}".strip(" ·")
    return line


class _Canvas:
    def __init__(self, registration: str) -> None:
        self.registration_text = registration
        self.pages: list[list[str]] = [[]]
        self.y = CONTENT_TOP
        self._breaking = False

    @property
    def ops(self) -> list[str]:
        return self.pages[-1]

    def header(self, name: str, kicker: str, meta: list[str]) -> None:
        self._bar()
        self.ops.append(_text(name, MARGIN_X, self.y - 20, 20, True, NAVY))
        self.ops.append(_text(kicker, MARGIN_X, self.y - 36, 9, False, STEEL))
        meta_lines = ["AIRCRAFT BRIEFING", *[line for line in meta if line]]
        cursor = self.y
        right = PAGE_W - MARGIN_X
        for index, line in enumerate(meta_lines):
            size = 8 if index == 0 else 9
            bold = index == 0
            color = NAVY if index == 0 else STEEL
            tracking = 0.55 if index == 0 else 0
            width = _text_width(line, size, bold, tracking)
            self.ops.append(_text(line, right - width, cursor - size, size, bold, color, tracking))
            cursor -= size + 3
        self.y = min(self.y - 46, cursor - 8)
        self._rule()

    def registration(self, registration: str) -> None:
        self.need(46)
        self.ops.append(_text(registration, MARGIN_X, self.y - 36, 36, True, NAVY))
        self.y -= 42

    def subtitle(self, text: str) -> None:
        lines = _wrap(text, 11, False, CONTENT_W) or [""]
        self.need(len(lines) * 14 + 8)
        for line in lines:
            self.ops.append(_text(line, MARGIN_X, self.y - 11, 11, False, STEEL))
            self.y -= 14
        self.y -= 10

    def facts(self, cells: list[tuple[str, str, tuple[float, float, float]]]) -> None:
        gap = 16.0
        col_w = (CONTENT_W - gap * 2) / 3
        for start in (0, 3):
            row = cells[start : start + 3]
            wrapped = [_wrap(value, 11, True, col_w - 2) or [""] for _label, value, _color in row]
            row_h = 14 + max(len(lines) for lines in wrapped) * 14 + 8
            self.need(row_h)
            x = MARGIN_X
            top = self.y
            for (label, _value, color), lines in zip(row, wrapped):
                self.ops.append(_hline(x, top, col_w, LINE, 0.8))
                self.ops.append(_text(label.upper(), x, top - 12, 7.5, True, MUTED, 0.45))
                cursor = top - 26
                for line in lines:
                    self.ops.append(_text(line, x, cursor, 11, True, color))
                    cursor -= 14
                x += col_w + gap
            self.y -= row_h

    def heading(self, text: str) -> None:
        self.need(28)
        self.y -= 10
        self.ops.append(_text(text, MARGIN_X, self.y - 13, 13, True, NAVY))
        self.y -= 18

    def paragraph(self, text: str, color: tuple[float, float, float]) -> None:
        lines = _wrap(text, 10, False, CONTENT_W) or [""]
        self.need(len(lines) * 13)
        for line in lines:
            self.ops.append(_text(line, MARGIN_X, self.y - 10, 10, False, color))
            self.y -= 13

    def card(self, title: str, body: str) -> None:
        inner = CONTENT_W - 16
        title_lines = _wrap(title, 10, True, inner) or [""]
        body_lines = _wrap(body, 10, False, inner) or [""]
        height = 8 + len(title_lines) * 13 + 2 + len(body_lines) * 13 + 8
        self.need(height + 4)
        bottom = self.y - height
        self.ops.append(_fill(MARGIN_X, bottom, CONTENT_W, height, CLOUD))
        cursor = self.y - 8
        for line in title_lines:
            self.ops.append(_text(line, MARGIN_X + 8, cursor - 10, 10, True, NAVY))
            cursor -= 13
        cursor -= 2
        for line in body_lines:
            self.ops.append(_text(line, MARGIN_X + 8, cursor - 10, 10, False, INK))
            cursor -= 13
        self.y = bottom - 6

    def table(
        self,
        headers: list[str],
        rows: list[list[str]],
        widths: list[float],
        aligns: list[str],
    ) -> None:
        def draw_header() -> None:
            self._table_header(headers, widths, aligns)

        draw_header()
        for row in rows:
            wrapped = [
                _wrap(cell, 9, False, max(12, width - 8)) or [""]
                for cell, width in zip(row, widths)
            ]
            row_h = 8 + max(len(lines) for lines in wrapped) * 12
            self.need(row_h, draw_header)
            x = MARGIN_X
            for lines, width, align in zip(wrapped, widths, aligns):
                cursor = self.y - 4
                for line in lines:
                    width_px = _text_width(line, 9, False)
                    origin = x + 2 if align == "left" else x + width - 4 - width_px
                    self.ops.append(_text(line, origin, cursor - 9, 9, False, INK))
                    cursor -= 12
                x += width
            self.y -= row_h
            self.ops.append(_hline(MARGIN_X, self.y, CONTENT_W, LINE, 0.6))

    def note(self, text: str) -> None:
        self.y -= 8
        self.paragraph(text, MUTED)

    def need(self, height: float, on_break: Callable[[], None] | None = None) -> None:
        room = CONTENT_TOP - MARGIN_BOTTOM - 48
        if self.y - height >= MARGIN_BOTTOM or self._breaking or not self.ops or height > room:
            return
        self._breaking = True
        try:
            self.pages.append([])
            self.y = CONTENT_TOP
            self._bar()
            self._continued_head()
            if on_break:
                on_break()
        finally:
            self._breaking = False

    def finish(self) -> list[bytes]:
        total = len(self.pages)
        streams = []
        for index, ops in enumerate(self.pages, start=1):
            label = f"Page {index} of {total}"
            width = _text_width(label, 8, False)
            ops.append(_text(label, PAGE_W - MARGIN_X - width, 24, 8, False, MUTED))
            streams.append("\n".join(ops).encode("latin-1", "replace"))
        return streams

    def _bar(self) -> None:
        self.ops.append(_fill(0, PAGE_H - BAR, PAGE_W, BAR, BRASS))

    def _rule(self) -> None:
        self.ops.append(_hline(MARGIN_X, self.y, CONTENT_W, BRASS, 1))
        self.y -= 16

    def _continued_head(self) -> None:
        self.ops.append(_text(self.registration_text, MARGIN_X, self.y - 12, 12, True, NAVY))
        label = "AIRCRAFT BRIEFING"
        width = _text_width(label, 8, True, 0.55)
        self.ops.append(
            _text(label, PAGE_W - MARGIN_X - width, self.y - 11, 8, True, NAVY, 0.55)
        )
        self.y -= 20
        self._rule()

    def _table_header(self, headers: list[str], widths: list[float], aligns: list[str]) -> None:
        x = MARGIN_X
        for header, width, align in zip(headers, widths, aligns):
            label = header.upper()
            tracking = 0.4
            text_w = _text_width(label, 7.5, True, tracking)
            origin = x + 2 if align == "left" else x + width - 4 - text_w
            self.ops.append(_text(label, origin, self.y - 10, 7.5, True, STEEL, tracking))
            x += width
        self.y -= 14
        self.ops.append(_hline(MARGIN_X, self.y, CONTENT_W, LINE, 0.8))
        self.y -= 2


def _text(
    text: str,
    x: float,
    baseline: float,
    size: float,
    bold: bool,
    color: tuple[float, float, float],
    tracking: float = 0,
) -> str:
    red, green, blue = color
    font = "F2" if bold else "F1"
    return (
        f"{red:.3f} {green:.3f} {blue:.3f} rg BT {tracking:.2f} Tc "
        f"/{font} {size:.2f} Tf {x:.2f} {baseline:.2f} Td ({_escape(text)}) Tj ET"
    )


def _fill(x: float, y: float, width: float, height: float, color: tuple[float, float, float]) -> str:
    red, green, blue = color
    return f"{red:.3f} {green:.3f} {blue:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f"


def _hline(x: float, y: float, width: float, color: tuple[float, float, float], thickness: float) -> str:
    red, green, blue = color
    return (
        f"{red:.3f} {green:.3f} {blue:.3f} RG {thickness:.2f} w "
        f"{x:.2f} {y:.2f} m {x + width:.2f} {y:.2f} l S"
    )


def _wrap(text: str, size: float, bold: bool, width: float) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        piece = word if _text_width(word, size, bold) <= width else _break_word(word, size, bold, width)
        parts = piece if isinstance(piece, list) else [piece]
        for part in parts:
            trial = part if not current else f"{current} {part}"
            if current and _text_width(trial, size, bold) > width:
                lines.append(current)
                current = part
            else:
                current = trial
    if current:
        lines.append(current)
    return lines


def _break_word(word: str, size: float, bold: bool, width: float) -> list[str]:
    parts: list[str] = []
    current = ""
    for char in word:
        trial = current + char
        if current and _text_width(trial, size, bold) > width:
            parts.append(current)
            current = char
        else:
            current = trial
    if current:
        parts.append(current)
    return parts


def _text_width(text: str, size: float, bold: bool, tracking: float = 0) -> float:
    total = 0.0
    for char in text:
        if char == " ":
            total += 0.28
        elif char in "ijlI.,:;'`|()":
            total += 0.28
        elif char in "MW@%":
            total += 0.86
        elif char.isupper():
            total += 0.68
        else:
            total += 0.52
    if bold:
        total *= 1.06
    return total * size + tracking * max(0, len(text) - 1)


def _document(streams: list[bytes]) -> bytes:
    font_regular = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    font_bold = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    objects: list[bytes] = [b"", b"", font_regular, font_bold]
    page_ids: list[int] = []
    for stream in streams:
        content = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        objects.append(content)
        content_id = len(objects)
        page_ids.append(content_id + 1)
        objects.append(b"")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode()
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    for page_id in page_ids:
        content_id = page_id - 1
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
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
        ("\u2014", _DASH),
        ("\u2013", "-"),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u00a0", " "),
    ):
        text = text.replace(src, dest)
    return " ".join(text.split())


def _escape(text: str) -> str:
    encoded = text.encode("latin-1", "replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    amount = abs(int(cents))
    return f"{sign}${amount // 100:,}.{amount % 100:02d}"


def _hours(value: float | None) -> str:
    if value is None:
        return _DASH
    return f"{float(value):.1f}"


def _date(value) -> str:
    if value is None:
        return ""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def _annual(days: int | None) -> str:
    if days is None:
        return "No annual date"
    if days < 0:
        return f"{abs(days)} days overdue"
    if days == 0:
        return "Due today"
    if days == 1:
        return "Due tomorrow"
    return f"Due in {days} days"
