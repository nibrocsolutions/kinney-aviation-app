from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Shop(Base):
    __tablename__ = "shop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_name: Mapped[str] = mapped_column(String(160))
    mechanic_name: Mapped[str] = mapped_column(String(160))
    certificate_label: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    base_city: Mapped[str] = mapped_column(String(80), default="Arizona")
    default_labor_rate_cents: Mapped[int] = mapped_column(Integer, default=12500)
    default_travel_rate_cents: Mapped[int] = mapped_column(Integer, default=9500)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=15)
    demo_seeded: Mapped[bool] = mapped_column(Boolean, default=False)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    aircraft: Mapped[list["Aircraft"]] = relationship(back_populates="customer")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="customer")


class Aircraft(Base):
    __tablename__ = "aircraft"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    registration: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    make: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    serial_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    year_manufactured: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engine_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tach_hours: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    hobbs_hours: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    total_time_hours: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    home_airport: Mapped[str | None] = mapped_column(String(4), nullable=True)
    annual_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="aircraft")
    records: Mapped[list["MaintenanceRecord"]] = relationship(back_populates="aircraft")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="aircraft")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey("aircraft.id"), index=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    title: Mapped[str] = mapped_column(String(200))
    discrepancy: Mapped[str] = mapped_column(Text, default="")
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str | None] = mapped_column(String(4), nullable=True)
    opened_on: Mapped[date] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    tach_hours: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    hobbs_hours: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    rating: Mapped[str] = mapped_column(String(2), default="AP")
    signoff_name: Mapped[str] = mapped_column(String(160), default="")
    certificate_ref: Mapped[str] = mapped_column(String(160), default="")
    travel_hours: Mapped[float] = mapped_column(Numeric(8, 1), default=0)
    rts_statement: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    aircraft: Mapped[Aircraft] = relationship(back_populates="records")
    labor_lines: Mapped[list["LaborLine"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )
    part_lines: Mapped[list["PartLine"]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="record")


class LaborLine(Base):
    __tablename__ = "labor_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("maintenance_records.id"), index=True)
    description: Mapped[str] = mapped_column(String(200))
    hours: Mapped[float] = mapped_column(Numeric(8, 1))
    rate_cents: Mapped[int] = mapped_column(Integer)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="labor_lines")


class PartLine(Base):
    __tablename__ = "part_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("maintenance_records.id"), index=True)
    part_number: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Numeric(8, 2))
    unit_price_cents: Mapped[int] = mapped_column(Integer)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="part_lines")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey("aircraft.id"), index=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("maintenance_records.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")

    customer: Mapped[Customer] = relationship(back_populates="invoices")
    aircraft: Mapped[Aircraft] = relationship(back_populates="invoices")
    record: Mapped[MaintenanceRecord] = relationship(back_populates="invoices")
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(240))
    quantity: Mapped[float] = mapped_column(Numeric(8, 2))
    unit_cents: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16), default="shop")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scheduled_on: Mapped[date] = mapped_column(Date, index=True)
    starts_at: Mapped[str | None] = mapped_column(String(5), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="visit")
    title: Mapped[str] = mapped_column(String(160))
    notes: Mapped[str] = mapped_column(Text, default="")
    aircraft_id: Mapped[int | None] = mapped_column(
        ForeignKey("aircraft.id", ondelete="SET NULL"), nullable=True, index=True
    )
    record_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    aircraft: Mapped[Aircraft | None] = relationship()
    record: Mapped[MaintenanceRecord | None] = relationship()


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    paid_on: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16), default="check")
    reference: Mapped[str] = mapped_column(String(80), default="")

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
