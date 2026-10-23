from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RecordKind = Literal["annual", "hundred_hour", "repair", "ad", "oil", "ferry", "other"]
RecordStatus = Literal["open", "in_work", "awaiting_parts", "complete"]
Rating = Literal["A", "P", "AP"]
PaymentMethod = Literal["check", "card", "ach", "cash", "other"]

N_NUMBER = r"N[1-9][0-9A-Z]{0,4}"


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _airport(value: str | None) -> str | None:
    text = _blank(value)
    if text is None:
        return None
    code = text.upper()
    if len(code) < 3 or len(code) > 4 or not code.isalnum():
        raise ValueError("Use a 3- or 4-character airport identifier such as KFLG.")
    return code


class ShopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_name: str
    mechanic_name: str
    certificate_label: str
    phone: str
    email: str
    base_city: str
    default_labor_rate_cents: int
    default_travel_rate_cents: int
    payment_terms_days: int
    demo_seeded: bool


class ShopUpdate(BaseModel):
    business_name: str | None = Field(default=None, min_length=1, max_length=160)
    mechanic_name: str | None = Field(default=None, min_length=1, max_length=160)
    certificate_label: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=160)
    base_city: str | None = Field(default=None, max_length=80)
    default_labor_rate_cents: int | None = Field(default=None, ge=0)
    default_travel_rate_cents: int | None = Field(default=None, ge=0)
    payment_terms_days: int | None = Field(default=None, ge=0, le=180)


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=80)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Name is required.")
        return text

    @field_validator("email", "phone", "city", "notes")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _blank(value)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=80)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("Name is required.")
        return text

    @field_validator("email", "phone", "city", "notes")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _blank(value)


class CustomerOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    city: str | None
    notes: str | None
    aircraft_count: int


class AircraftIn(BaseModel):
    customer_id: int
    registration: str
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    serial_number: str | None = Field(default=None, max_length=40)
    year_manufactured: int | None = Field(default=None, ge=1903, le=2100)
    engine_model: str | None = Field(default=None, max_length=80)
    tach_hours: float | None = Field(default=None, ge=0)
    hobbs_hours: float | None = Field(default=None, ge=0)
    total_time_hours: float | None = Field(default=None, ge=0)
    home_airport: str | None = None
    annual_due: date | None = None
    notes: str | None = None

    @field_validator("registration")
    @classmethod
    def clean_registration(cls, value: str) -> str:
        text = value.strip().upper().replace(" ", "")
        import re

        if not re.fullmatch(N_NUMBER, text):
            raise ValueError("Enter a US N-number such as N5183K.")
        return text

    @field_validator("make", "model")
    @classmethod
    def clean_required(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("This field is required.")
        return text

    @field_validator("serial_number", "engine_model", "notes")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _blank(value)

    @field_validator("home_airport")
    @classmethod
    def clean_airport(cls, value: str | None) -> str | None:
        return _airport(value)


class AircraftUpdate(BaseModel):
    customer_id: int | None = None
    registration: str | None = None
    make: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    serial_number: str | None = Field(default=None, max_length=40)
    year_manufactured: int | None = Field(default=None, ge=1903, le=2100)
    engine_model: str | None = Field(default=None, max_length=80)
    tach_hours: float | None = Field(default=None, ge=0)
    hobbs_hours: float | None = Field(default=None, ge=0)
    total_time_hours: float | None = Field(default=None, ge=0)
    home_airport: str | None = None
    annual_due: date | None = None
    notes: str | None = None

    @field_validator("registration")
    @classmethod
    def clean_registration(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper().replace(" ", "")
        import re

        if not re.fullmatch(N_NUMBER, text):
            raise ValueError("Enter a US N-number such as N5183K.")
        return text

    @field_validator("make", "model")
    @classmethod
    def clean_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("This field is required.")
        return text

    @field_validator("serial_number", "engine_model", "notes")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _blank(value)

    @field_validator("home_airport")
    @classmethod
    def clean_airport(cls, value: str | None) -> str | None:
        return _airport(value)


class AircraftOut(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    registration: str
    make: str
    model: str
    serial_number: str | None
    year_manufactured: int | None
    engine_model: str | None
    tach_hours: float | None
    hobbs_hours: float | None
    total_time_hours: float | None
    home_airport: str | None
    annual_due: date | None
    days_to_annual: int | None
    notes: str | None
    open_record_count: int
    balance_cents: int


class LaborIn(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    hours: float = Field(gt=0, le=999)
    rate_cents: int = Field(ge=0)

    @field_validator("description")
    @classmethod
    def clean(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Describe the labor.")
        return text


class LaborUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=200)
    hours: float | None = Field(default=None, gt=0, le=999)
    rate_cents: int | None = Field(default=None, ge=0)

    @field_validator("description")
    @classmethod
    def clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("Describe the labor.")
        return text


class PartIn(BaseModel):
    part_number: str | None = Field(default=None, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0, le=9999)
    unit_price_cents: int = Field(ge=0)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Describe the part.")
        return text

    @field_validator("part_number")
    @classmethod
    def clean_pn(cls, value: str | None) -> str | None:
        return _blank(value) or ""


class PartUpdate(BaseModel):
    part_number: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=200)
    quantity: float | None = Field(default=None, gt=0, le=9999)
    unit_price_cents: int | None = Field(default=None, ge=0)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("Describe the part.")
        return text

    @field_validator("part_number")
    @classmethod
    def clean_pn(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _blank(value) or ""


class LaborOut(BaseModel):
    id: int
    description: str
    hours: float
    rate_cents: int
    amount_cents: int


class PartOut(BaseModel):
    id: int
    part_number: str
    description: str
    quantity: float
    unit_price_cents: int
    amount_cents: int


class InvoiceRef(BaseModel):
    id: int
    number: str
    status: str
    stale: bool


class RecordIn(BaseModel):
    aircraft_id: int
    kind: RecordKind
    title: str = Field(min_length=1, max_length=200)
    discrepancy: str = ""
    corrective_action: str = ""
    location: str | None = None
    opened_on: date | None = None
    status: RecordStatus = "open"
    tach_hours: float | None = Field(default=None, ge=0)
    hobbs_hours: float | None = Field(default=None, ge=0)
    rating: Rating = "AP"
    travel_hours: float = Field(default=0, ge=0, le=999)
    notes: str | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Title is required.")
        return text

    @field_validator("location")
    @classmethod
    def clean_location(cls, value: str | None) -> str | None:
        return _airport(value)

    @field_validator("discrepancy", "corrective_action")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return _blank(value)


class RecordUpdate(BaseModel):
    kind: RecordKind | None = None
    title: str | None = Field(default=None, max_length=200)
    discrepancy: str | None = None
    corrective_action: str | None = None
    location: str | None = None
    opened_on: date | None = None
    closed_on: date | None = None
    status: RecordStatus | None = None
    tach_hours: float | None = Field(default=None, ge=0)
    hobbs_hours: float | None = Field(default=None, ge=0)
    rating: Rating | None = None
    signoff_name: str | None = Field(default=None, max_length=160)
    certificate_ref: str | None = Field(default=None, max_length=160)
    travel_hours: float | None = Field(default=None, ge=0, le=999)
    rts_statement: str | None = None
    notes: str | None = None

    @field_validator("title", "signoff_name", "certificate_ref")
    @classmethod
    def clean_short(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("location")
    @classmethod
    def clean_location(cls, value: str | None) -> str | None:
        return _airport(value)

    @field_validator("discrepancy", "corrective_action", "rts_statement")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return _blank(value)


class RecordOut(BaseModel):
    id: int
    number: str
    aircraft_id: int
    registration: str
    aircraft_label: str
    customer_id: int
    customer_name: str
    kind: str
    status: str
    title: str
    discrepancy: str
    corrective_action: str
    location: str | None
    opened_on: date
    closed_on: date | None
    tach_hours: float | None
    hobbs_hours: float | None
    rating: str
    signoff_name: str
    certificate_ref: str
    travel_hours: float
    travel_rate_cents: int
    rts_statement: str
    notes: str | None
    labor_lines: list[LaborOut]
    part_lines: list[PartOut]
    labor_cents: int
    parts_cents: int
    travel_cents: int
    total_cents: int
    has_billing: bool
    invoice: InvoiceRef | None


class InvoiceLineOut(BaseModel):
    id: int
    kind: str
    description: str
    quantity: float
    unit_cents: int
    amount_cents: int


class PaymentIn(BaseModel):
    amount_cents: int = Field(gt=0)
    paid_on: date | None = None
    method: PaymentMethod = "check"
    reference: str = ""

    @field_validator("reference")
    @classmethod
    def clean_ref(cls, value: str) -> str:
        return value.strip()


class PaymentOut(BaseModel):
    id: int
    paid_on: date
    amount_cents: int
    method: str
    reference: str


class InvoiceUpdate(BaseModel):
    notes: str | None = None
    tax_cents: int | None = Field(default=None, ge=0)
    due_on: date | None = None

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class InvoiceOut(BaseModel):
    id: int
    number: str
    customer_id: int
    customer_name: str
    aircraft_id: int
    registration: str
    aircraft_label: str
    record_id: int
    record_number: str
    record_title: str
    status: str
    issued_on: date | None
    due_on: date | None
    tax_cents: int
    notes: str
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]
    subtotal_cents: int
    total_cents: int
    paid_cents: int
    balance_cents: int
    amount_due_cents: int
    stale: bool


class RecordBrief(BaseModel):
    id: int
    number: str
    registration: str
    title: str
    kind: str
    status: str
    opened_on: date
    total_cents: int


class InvoiceBrief(BaseModel):
    id: int
    number: str
    registration: str
    customer_name: str
    status: str
    total_cents: int
    amount_due_cents: int
    due_on: date | None


class AnnualBrief(BaseModel):
    aircraft_id: int
    registration: str
    make: str
    model: str
    home_airport: str | None
    customer_name: str
    annual_due: date
    days_remaining: int


class DashboardOut(BaseModel):
    shop: ShopOut
    open_work: int
    awaiting_parts: int
    fleet_count: int
    customer_count: int
    receivables_cents: int
    draft_cents: int
    unbilled_count: int
    annuals: list[AnnualBrief]
    recent_records: list[RecordBrief]
    open_invoices: list[InvoiceBrief]


class PresentAircraft(BaseModel):
    shop: ShopOut
    generated_on: date
    aircraft: AircraftOut
    open_items: list[RecordOut]
    logbook: list[RecordOut]
    invoices: list[InvoiceOut]
    open_balance_cents: int


class PresentRecord(BaseModel):
    shop: ShopOut
    generated_on: date
    record: RecordOut


class PresentInvoice(BaseModel):
    shop: ShopOut
    generated_on: date
    invoice: InvoiceOut


UserRole = Literal["admin", "shop"]
ScheduleKind = Literal["visit", "inspection", "parts", "ferry", "other"]
CalendarSource = Literal["entry", "record", "annual", "invoice"]


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    active: bool
    signed_out: bool = False


class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str
    role: UserRole = "shop"

    @field_validator("username")
    @classmethod
    def username_ok(cls, value: str) -> str:
        from app.auth import normalize_username

        return normalize_username(value)

    @field_validator("display_name")
    @classmethod
    def display_ok(cls, value: str) -> str:
        from app.auth import normalize_display_name

        return normalize_display_name(value)

    @field_validator("password")
    @classmethod
    def password_ok(cls, value: str) -> str:
        from app.auth import normalize_password

        return normalize_password(value)


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    active: bool | None = None
    password: str | None = None

    @field_validator("display_name")
    @classmethod
    def display_ok(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from app.auth import normalize_display_name

        return normalize_display_name(value)

    @field_validator("password")
    @classmethod
    def password_ok(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        from app.auth import normalize_password

        return normalize_password(value)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_ok(cls, value: str) -> str:
        from app.auth import normalize_password

        return normalize_password(value)


class LoginIn(BaseModel):
    username: str = ""
    password: str = ""


class CalendarItem(BaseModel):
    key: str
    source: CalendarSource
    date: date
    starts_at: str | None = None
    kind: str
    label: str
    title: str
    detail: str = ""
    href: str | None = None
    editable: bool = False
    entry_id: int | None = None
    registration: str | None = None


class CalendarOut(BaseModel):
    start: date
    end: date
    items: list[CalendarItem]


class ScheduleOut(BaseModel):
    id: int
    scheduled_on: date
    starts_at: str | None
    kind: str
    title: str
    notes: str
    aircraft_id: int | None
    record_id: int | None
    registration: str | None = None


def _clock(value: str | None) -> str | None:
    text = _blank(value)
    if text is None:
        return None
    from app.auth import CLOCK

    if CLOCK.fullmatch(text) is None:
        raise ValueError("Use a time like 08:30.")
    return text


def _schedule_title(value: str) -> str:
    text = value.strip()
    if not text or len(text) > 160:
        raise ValueError("Enter a short title for the day.")
    return text


def _schedule_notes(value: str) -> str:
    text = value.strip()
    if len(text) > 2000:
        raise ValueError("Keep the note under 2000 characters.")
    return text


class ScheduleIn(BaseModel):
    scheduled_on: date
    starts_at: str | None = None
    kind: ScheduleKind = "visit"
    title: str
    notes: str = ""
    aircraft_id: int | None = None
    record_id: int | None = None

    @field_validator("starts_at")
    @classmethod
    def time_ok(cls, value: str | None) -> str | None:
        return _clock(value)

    @field_validator("title")
    @classmethod
    def title_ok(cls, value: str) -> str:
        return _schedule_title(value)

    @field_validator("notes")
    @classmethod
    def notes_ok(cls, value: str) -> str:
        return _schedule_notes(value)


class ScheduleUpdate(BaseModel):
    scheduled_on: date | None = None
    starts_at: str | None = None
    kind: ScheduleKind | None = None
    title: str | None = None
    notes: str | None = None
    aircraft_id: int | None = None
    record_id: int | None = None

    @field_validator("starts_at")
    @classmethod
    def time_ok(cls, value: str | None) -> str | None:
        return _clock(value)

    @field_validator("title")
    @classmethod
    def title_ok(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _schedule_title(value)

    @field_validator("notes")
    @classmethod
    def notes_ok(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _schedule_notes(value)
