from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RFQ(Base):
    __tablename__ = "rfqs"
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_number: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    customer: Mapped[str] = mapped_column(String(180), index=True)
    received_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="estimating", index=True)
    loss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    source_label: Mapped[str] = mapped_column(String(80), default="Demo seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    owner: Mapped[User] = relationship()
    parts: Mapped[list["Part"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")
    revisions: Mapped[list["QuoteRevision"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")
    sources: Mapped[list["RFQSource"]] = relationship(back_populates="rfq", cascade="all, delete-orphan")


class RFQSource(Base):
    __tablename__ = "rfq_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    rfq_id: Mapped[int | None] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), index=True, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer)
    extraction_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    rfq: Mapped[RFQ | None] = relationship(back_populates="sources")


class Part(Base):
    __tablename__ = "parts"
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), index=True)
    part_name: Mapped[str] = mapped_column(String(180))
    material: Mapped[str] = mapped_column(String(120))
    gross_weight_kg: Mapped[float] = mapped_column(Float)
    annual_volume: Mapped[int] = mapped_column(Integer)
    cycle_time_min: Mapped[float] = mapped_column(Float)
    machine_rate_key: Mapped[str] = mapped_column(String(120), default="General machining")
    scrap_pct: Mapped[float] = mapped_column(Float, default=0)
    overhead_per_part: Mapped[float] = mapped_column(Float, default=0)
    freight_per_part: Mapped[float] = mapped_column(Float, default=0)
    packing_per_part: Mapped[float] = mapped_column(Float, default=0)
    margin_pct: Mapped[float] = mapped_column(Float, default=15)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    rfq: Mapped[RFQ] = relationship(back_populates="parts")
    routing_operations: Mapped[list["RoutingOperation"]] = relationship(
        back_populates="part", cascade="all, delete-orphan", order_by="RoutingOperation.sequence_no")


class RoutingOperation(Base):
    __tablename__ = "routing_operations"
    __table_args__ = (UniqueConstraint("part_id", "sequence_no", name="uq_part_route_sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    operation_name: Mapped[str] = mapped_column(String(120))
    machine_rate_key: Mapped[str] = mapped_column(String(120))
    cycle_time_min: Mapped[float] = mapped_column(Float)
    part: Mapped[Part] = relationship(back_populates="routing_operations")


class RateVersion(Base):
    __tablename__ = "rate_versions"
    __table_args__ = (UniqueConstraint("rate_type", "rate_key", "effective_from", name="uq_rate_key_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rate_type: Mapped[str] = mapped_column(String(30), index=True)
    rate_key: Mapped[str] = mapped_column(String(120), index=True)
    unit: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Float)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class QuoteRevision(Base):
    __tablename__ = "quote_revisions"
    __table_args__ = (UniqueConstraint("rfq_id", "revision_number", name="uq_rfq_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    scenarios_json: Mapped[str] = mapped_column(Text)
    breakdown_json: Mapped[str] = mapped_column(Text)
    rate_snapshot_json: Mapped[str] = mapped_column(Text)
    annual_value: Mapped[float] = mapped_column(Float, default=0)
    gst_rate_percent: Mapped[float] = mapped_column(Float, default=0)
    formula_version: Mapped[str] = mapped_column(String(30), default="cost-v1")
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rfq: Mapped[RFQ] = relationship(back_populates="revisions")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("quote_revisions.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(80))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HistoricalQuote(Base):
    __tablename__ = "historical_quotes"
    __table_args__ = (UniqueConstraint("batch_id", "source_row", name="uq_history_source_row"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(80), index=True)
    source_row: Mapped[int] = mapped_column(Integer)
    rfq_number: Mapped[str] = mapped_column(String(100), index=True)
    customer: Mapped[str] = mapped_column(String(180), index=True)
    part_name: Mapped[str] = mapped_column(String(180), index=True)
    material: Mapped[str] = mapped_column(String(120), index=True)
    gross_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    annual_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cycle_time_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quoted_unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quoted_annual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    quoted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_label: Mapped[str] = mapped_column(String(180), default="Imported historical quote")
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
