import io
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .costing import calculate_part
from .database import Base, SessionLocal, engine, get_db
from .models import Approval, AuditEvent, HistoricalQuote, Part, QuoteRevision, RFQ, RFQSource, RateVersion, RoutingOperation, User
from .security import SESSIONS, check_csrf, new_session, session_user, verify_password
from .seed import MACHINE_RATES, MATERIAL_RATES, seed_database

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(ROOT / "instance" / "uploads"))).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.lumosel.vip").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "claude-opus-4-8").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_PROTOCOL = os.getenv("AI_PROTOCOL", "openai" if AI_BASE_URL.endswith("/v1") else "anthropic").strip().lower()
AI_NDA_APPROVED = os.getenv("AI_NDA_APPROVED", "false").lower() == "true"
GST_RATE_PERCENT = float(os.getenv("GST_RATE_PERCENT", "0") or 0)
if not 0 <= GST_RATE_PERCENT <= 100:
    raise RuntimeError("GST_RATE_PERCENT must be between 0 and 100.")
AI_LAST_CHECK = {"ok": None, "error": None, "at": None}
MAX_UPLOAD = 12 * 1024 * 1024
MAX_OCR_PAGES = 20
SUPABASE_URL = os.getenv("SUPABASE_URL", os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")).rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "rfq-source-documents").strip()

if not SUPABASE_URL:
    try:
        db_host = urlsplit(os.getenv("DATABASE_URL", "")).hostname or ""
        if db_host.startswith("db.") and db_host.endswith(".supabase.co"):
            SUPABASE_URL = f"https://{db_host[3:]}"
    except ValueError:
        pass

app = FastAPI(title="ForgeQuote", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


class LoginBody(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class RFQPartBody(BaseModel):
    part_name: str = Field(min_length=1, max_length=180)
    material: str = Field(min_length=1, max_length=120)
    gross_weight_kg: float = Field(gt=0)
    annual_volume: int = Field(gt=0)
    cycle_time_min: float = Field(ge=0)
    machine_rate_key: str = Field(min_length=1, max_length=120)
    source_ref: str | None = Field(default=None, max_length=8000)


class RFQBody(BaseModel):
    rfq_number: str = Field(min_length=3, max_length=80)
    customer: str = Field(min_length=1, max_length=180)
    due_date: date
    parts: list[RFQPartBody] | None = Field(default=None, min_length=1, max_length=100)
    # Legacy single-part fields remain accepted for existing clients.
    part_name: str | None = Field(default=None, min_length=1, max_length=180)
    material: str | None = Field(default=None, min_length=1, max_length=120)
    gross_weight_kg: float | None = Field(default=None, gt=0)
    annual_volume: int | None = Field(default=None, gt=0)
    cycle_time_min: float | None = Field(default=None, ge=0)
    machine_rate_key: str | None = Field(default=None, min_length=1, max_length=120)
    source_ref: str | None = Field(default=None, max_length=8000)
    source_file_ids: list[str] = Field(default_factory=list, max_length=20)


class RFQMetaBody(BaseModel):
    rfq_number: str = Field(min_length=3, max_length=80)
    customer: str = Field(min_length=1, max_length=180)
    due_date: date


class RoutingOperationBody(BaseModel):
    operation_name: str = Field(min_length=1, max_length=120)
    machine_rate_key: str = Field(min_length=1, max_length=120)
    cycle_time_min: float = Field(ge=0)


class PartPatch(BaseModel):
    gross_weight_kg: float | None = Field(default=None, gt=0)
    annual_volume: int | None = Field(default=None, gt=0)
    cycle_time_min: float | None = Field(default=None, ge=0)
    scrap_pct: float | None = Field(default=None, ge=0, lt=100)
    overhead_per_part: float | None = Field(default=None, ge=0)
    freight_per_part: float | None = Field(default=None, ge=0)
    packing_per_part: float | None = Field(default=None, ge=0)
    margin_pct: float | None = Field(default=None, ge=0, lt=100)
    machine_rate_key: str | None = Field(default=None, min_length=1, max_length=120)
    source_ref: str | None = Field(default=None, max_length=8000)
    routing_operations: list[RoutingOperationBody] | None = Field(default=None, min_length=1, max_length=12)


class IntakeExtractBody(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    text: str = Field(min_length=1, max_length=40000)


class CostBody(BaseModel):
    volumes: list[int] = Field(min_length=2, max_length=3)


class DecisionBody(BaseModel):
    decision: str
    reason: str | None = None


class OwnerAssignBody(BaseModel):
    owner_id: int


class AssistantBody(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    rfq_id: int | None = None


class RateBody(BaseModel):
    rate_type: str
    rate_key: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=30)
    amount: float = Field(ge=0)
    effective_from: date
    effective_to: date | None = None


def serialize_user(user: User):
    return {"id": user.id, "username": user.username, "display_name": user.display_name, "role": user.role}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("fq_session")
    session = session_user(token)
    if not session:
        raise HTTPException(401, "Sign in to continue.")
    user = db.get(User, session["user_id"])
    if not user or not user.active:
        SESSIONS.pop(token, None)
        raise HTTPException(401, "Session expired. Sign in again.")
    request.state.session_token = token
    return user


def require_csrf(request: Request):
    token = request.cookies.get("fq_session")
    if not check_csrf(token, request.headers.get("x-csrf-token")):
        raise HTTPException(403, "Session check failed. Refresh and try again.")


def require_role(user: User, *roles: str):
    if user.role not in roles:
        raise HTTPException(403, "Your account cannot perform this action.")


def audit(db: Session, user_id: int | None, action: str, entity: str, entity_id, detail: str = ""):
    db.add(AuditEvent(actor_id=user_id, action=action, entity_type=entity,
                      entity_id=str(entity_id), detail=detail[:600]))


def effective_rate(db: Session, kind: str, key: str, on_date: date | None = None):
    on_date = on_date or date.today()
    rate = (db.query(RateVersion).filter(RateVersion.rate_type == kind,
             RateVersion.rate_key == key, RateVersion.effective_from <= on_date,
             or_(RateVersion.effective_to.is_(None), RateVersion.effective_to >= on_date))
            .order_by(RateVersion.effective_from.desc()).first())
    if not rate:
        raise HTTPException(409, f"No effective {kind} rate for {key} on {on_date.isoformat()}.")
    return rate


def as_rfq(rfq: RFQ):
    latest = max(rfq.revisions, key=lambda r: r.revision_number, default=None)
    return {"id": rfq.id, "rfq_number": rfq.rfq_number, "customer": rfq.customer,
            "received_date": rfq.received_date.isoformat(), "due_date": rfq.due_date.isoformat(),
            "owner": rfq.owner.display_name if rfq.owner else "Estimator", "owner_id": rfq.owner_id,
            "status": rfq.status, "loss_reason": rfq.loss_reason, "synthetic": rfq.synthetic,
            "source_label": rfq.source_label, "part_count": len(rfq.parts),
            "sources": [as_source(s) for s in rfq.sources],
            "annual_value": round(latest.annual_value, 2) if latest else None,
            "revision_id": latest.id if latest else None}


def as_part(part: Part):
    return {"id": part.id, "part_name": part.part_name, "material": part.material,
            "gross_weight_kg": part.gross_weight_kg, "annual_volume": part.annual_volume,
            "cycle_time_min": part.cycle_time_min, "machine_rate_key": part.machine_rate_key,
            "routing_operations": [{"sequence_no": x.sequence_no, "operation_name": x.operation_name,
                "machine_rate_key": x.machine_rate_key, "cycle_time_min": x.cycle_time_min}
                for x in part.routing_operations],
            "scrap_pct": part.scrap_pct, "overhead_per_part": part.overhead_per_part,
            "freight_per_part": part.freight_per_part, "packing_per_part": part.packing_per_part,
            "margin_pct": part.margin_pct, "synthetic": part.synthetic, "source_ref": part.source_ref}


def as_source(source: RFQSource):
    return {"file_id": source.file_id, "filename": source.original_filename,
            "size_bytes": source.size_bytes, "media_type": source.media_type,
            "extraction_method": source.extraction_method,
            "extraction_error": source.extraction_error,
            "created_at": source.created_at.isoformat() if source.created_at else None,
            "download_url": f"/api/sources/{source.file_id}"}


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite" or os.getenv("SEED_DEMO_DATA", "false").lower() == "true":
        with SessionLocal() as db:
            seed_database(db)


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/api/health")
def health():
    if not AI_API_KEY:
        ai_status = "not_configured"
    elif AI_LAST_CHECK["ok"] is True:
        ai_status = "reachable"
    elif AI_LAST_CHECK["ok"] is False:
        ai_status = "unavailable"
    else:
        ai_status = "unverified"
    return {"status": "ok", "database": engine.dialect.name,
            "ai": ai_status,
            "file_storage": "supabase" if SUPABASE_URL and SUPABASE_SECRET_KEY else "local"}


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Those sign-in details did not match.")
    token, csrf = new_session(user.id)
    response.set_cookie("fq_session", token, httponly=True, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
                        samesite="strict", max_age=43_200, path="/")
    audit(db, user.id, "sign_in", "user", user.id)
    db.commit()
    return {"user": serialize_user(user), "csrf_token": csrf}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_csrf(request)
    token = request.cookies.get("fq_session")
    SESSIONS.pop(token, None)
    response.delete_cookie("fq_session", path="/")
    audit(db, user.id, "sign_out", "user", user.id)
    db.commit()
    return {"ok": True}


@app.get("/api/me")
def me(request: Request, user: User = Depends(get_current_user)):
    session = session_user(request.cookies.get("fq_session"))
    return {"user": serialize_user(user), "csrf_token": session["csrf"]}


@app.get("/api/rfqs")
def list_rfqs(q: str = "", status: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(RFQ).options(joinedload(RFQ.owner), joinedload(RFQ.parts), joinedload(RFQ.revisions), joinedload(RFQ.sources))
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(RFQ.rfq_number.ilike(term), RFQ.customer.ilike(term)))
    if status:
        query = query.filter(RFQ.status == status)
    rows = query.order_by(RFQ.due_date.asc(), RFQ.rfq_number.asc()).all()
    today = date.today()
    return {"items": [as_rfq(r) for r in rows], "total": len(rows),
            "overdue": sum(1 for r in rows if r.status in ("estimating", "pending_approval") and r.due_date < today)}


@app.get("/api/users/estimators")
def list_estimators(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "sales")
    rows = db.query(User).filter(User.role == "estimator", User.active.is_(True)).order_by(User.display_name).all()
    return {"items": [{"id": row.id, "display_name": row.display_name} for row in rows]}


@app.post("/api/rfqs")
def create_rfq(body: RFQBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    if db.query(RFQ).filter(RFQ.rfq_number == body.rfq_number.strip()).first():
        raise HTTPException(409, "That RFQ number already exists.")
    input_parts = body.parts
    if input_parts is None:
        legacy = (body.part_name, body.material, body.gross_weight_kg, body.annual_volume,
                  body.cycle_time_min, body.machine_rate_key)
        if any(value is None for value in legacy):
            raise HTTPException(422, "Add at least one complete part, or provide the legacy single-part fields.")
        input_parts = [RFQPartBody(part_name=body.part_name, material=body.material,
            gross_weight_kg=body.gross_weight_kg, annual_volume=body.annual_volume,
            cycle_time_min=body.cycle_time_min, machine_rate_key=body.machine_rate_key,
            source_ref=body.source_ref)]
    file_ids = list(dict.fromkeys(body.source_file_ids))
    if len(file_ids) != len(body.source_file_ids):
        raise HTTPException(422, "A source document was attached more than once.")
    sources = []
    if file_ids:
        sources = db.query(RFQSource).filter(RFQSource.file_id.in_(file_ids),
            RFQSource.uploaded_by == user.id, RFQSource.rfq_id.is_(None)).all()
        if len(sources) != len(file_ids):
            raise HTTPException(422, "One or more uploaded source files are missing or already attached.")
    rfq = RFQ(rfq_number=body.rfq_number.strip(), customer=body.customer.strip(), received_date=date.today(),
              due_date=body.due_date, owner_id=user.id, status="estimating", synthetic=False,
              source_label="Entered by estimator" if not sources else "Estimator intake · source documents attached")
    for item in input_parts:
        rfq.parts.append(Part(part_name=item.part_name.strip(), material=item.material.strip(),
            gross_weight_kg=item.gross_weight_kg, annual_volume=item.annual_volume,
            cycle_time_min=item.cycle_time_min, machine_rate_key=item.machine_rate_key.strip(),
            scrap_pct=0, overhead_per_part=0, freight_per_part=0, packing_per_part=0,
            margin_pct=15, synthetic=False, source_ref=item.source_ref or body.source_ref))
    for source in sources:
        rfq.sources.append(source)
    db.add(rfq)
    db.flush()
    audit(db, user.id, "create_rfq", "rfq", rfq.id, rfq.rfq_number)
    db.commit()
    db.refresh(rfq)
    return as_rfq(rfq)


@app.patch("/api/rfqs/{rfq_id}/owner")
def assign_rfq_owner(rfq_id: int, body: OwnerAssignBody, request: Request,
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "sales")
    rfq = db.get(RFQ, rfq_id)
    owner = db.get(User, body.owner_id)
    if not rfq:
        raise HTTPException(404, "RFQ not found.")
    if not owner or not owner.active or owner.role != "estimator":
        raise HTTPException(422, "Choose an active estimator as the RFQ owner.")
    old_owner = rfq.owner_id
    rfq.owner_id = owner.id
    audit(db, user.id, "assign_rfq_owner", "rfq", rfq.id,
          f"owner_id={old_owner}->{owner.id}")
    db.commit()
    return {"rfq_id": rfq.id, "owner_id": owner.id, "owner": owner.display_name}


@app.get("/api/rfqs/{rfq_id}")
def get_rfq(rfq_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rfq = db.query(RFQ).options(joinedload(RFQ.owner), joinedload(RFQ.parts), joinedload(RFQ.revisions)).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found.")
    return {**as_rfq(rfq), "parts": [as_part(p) for p in rfq.parts],
            "sources": [as_source(s) for s in rfq.sources],
            "revisions": [{"id": r.id, "revision_number": r.revision_number, "status": r.status,
                           "annual_value": r.annual_value, "created_at": r.created_at.isoformat()} for r in rfq.revisions]}


@app.patch("/api/rfqs/{rfq_id}")
def update_rfq(rfq_id: int, body: RFQMetaBody, request: Request,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(404, "RFQ not found.")
    if user.role == "estimator" and rfq.owner_id != user.id:
        raise HTTPException(403, "Only the RFQ owner or Sales Head can edit its header.")
    duplicate = db.query(RFQ).filter(RFQ.rfq_number == body.rfq_number.strip(), RFQ.id != rfq.id).first()
    if duplicate:
        raise HTTPException(409, "That RFQ number is already in use.")
    before = f"{rfq.rfq_number}|{rfq.customer}|{rfq.due_date.isoformat()}"
    rfq.rfq_number = body.rfq_number.strip()
    rfq.customer = body.customer.strip()
    rfq.due_date = body.due_date
    audit(db, user.id, "update_rfq_header", "rfq", rfq.id, f"{before} -> {rfq.rfq_number}|{rfq.customer}|{rfq.due_date}")
    db.commit()
    return {"rfq_id": rfq.id, "rfq_number": rfq.rfq_number, "customer": rfq.customer,
            "due_date": rfq.due_date.isoformat()}


@app.patch("/api/parts/{part_id}")
def update_part(part_id: int, body: PartPatch, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    part = db.get(Part, part_id)
    if not part:
        raise HTTPException(404, "Part not found.")
    values = body.model_dump(exclude_unset=True)
    route_inputs = values.pop("routing_operations", None)
    for key, value in values.items():
        if value is not None:
            setattr(part, key, value)
    if route_inputs is not None:
        names = [str(x["operation_name"]).strip() for x in route_inputs]
        if any(not name for name in names):
            raise HTTPException(422, "Every routing operation needs a name.")
        part.routing_operations.clear()
        db.flush()
        for index, operation in enumerate(route_inputs, 1):
            part.routing_operations.append(RoutingOperation(sequence_no=index,
                operation_name=operation["operation_name"].strip(),
                machine_rate_key=operation["machine_rate_key"].strip(),
                cycle_time_min=operation["cycle_time_min"]))
        part.machine_rate_key = route_inputs[0]["machine_rate_key"].strip()
        part.cycle_time_min = route_inputs[0]["cycle_time_min"]
    audit(db, user.id, "update_part_cost_inputs", "part", part.id,
          ",".join(body.model_dump(exclude_unset=True).keys()))
    db.commit()
    return as_part(part)


@app.get("/api/rates")
def list_rates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(RateVersion).order_by(RateVersion.rate_type, RateVersion.rate_key, RateVersion.effective_from.desc()).all()
    return {"items": [{"id": r.id, "rate_type": r.rate_type, "rate_key": r.rate_key, "unit": r.unit,
                        "amount": r.amount, "effective_from": r.effective_from.isoformat(),
                        "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                        "synthetic": r.synthetic} for r in rows]}


@app.post("/api/rates")
def create_rate(body: RateBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "sales")
    rate_key = body.rate_key.strip()
    expected_unit = {"material": "₹ / kg", "machine": "₹ / hour"}.get(body.rate_type)
    if not rate_key or not expected_unit or body.unit != expected_unit or (body.effective_to and body.effective_to < body.effective_from):
        raise HTTPException(422, "Rate type or effective period is invalid.")
    overlaps = db.query(RateVersion).filter(RateVersion.rate_type == body.rate_type,
        RateVersion.rate_key == rate_key,
        or_(RateVersion.effective_to.is_(None), RateVersion.effective_to >= body.effective_from),
        or_(body.effective_to is None, RateVersion.effective_from <= body.effective_to)).all()
    for old in overlaps:
        if old.effective_from < body.effective_from and (old.effective_to is None or old.effective_to >= body.effective_from):
            old.effective_to = body.effective_from - timedelta(days=1)
        else:
            raise HTTPException(409, "This rate period conflicts with an existing version. Choose a non-overlapping start date.")
    rate = RateVersion(rate_type=body.rate_type, rate_key=rate_key, unit=body.unit,
                       amount=body.amount, effective_from=body.effective_from, effective_to=body.effective_to,
                       editor_id=user.id, synthetic=False)
    db.add(rate)
    db.flush()
    audit(db, user.id, "create_rate_version", "rate_version", rate.id, f"{rate_key} · {body.effective_from}")
    db.commit()
    return {"id": rate.id}


@app.post("/api/rfqs/{rfq_id}/cost")
def calculate_rfq(rfq_id: int, body: CostBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    if len(body.volumes) not in (2, 3) or any(v <= 0 for v in body.volumes) or len(set(body.volumes)) != len(body.volumes):
        raise HTTPException(422, "Choose two or three distinct positive volume points.")
    rfq = db.query(RFQ).options(joinedload(RFQ.parts), joinedload(RFQ.revisions)).filter(RFQ.id == rfq_id).first()
    if not rfq:
        raise HTTPException(404, "RFQ not found.")
    breakdown, snapshots = [], []
    for part in rfq.parts:
        material_rate = effective_rate(db, "material", part.material)
        operations = [{"operation_name": op.operation_name, "machine_rate_key": op.machine_rate_key,
                      "cycle_time_min": op.cycle_time_min} for op in part.routing_operations]
        if not operations:
            operations = [{"operation_name": "Primary operation", "machine_rate_key": part.machine_rate_key,
                           "cycle_time_min": part.cycle_time_min}]
        operation_rates = []
        for index, operation in enumerate(operations, 1):
            rate = effective_rate(db, "machine", operation["machine_rate_key"])
            operation_rates.append({**operation, "sequence_no": index, "rate_id": rate.id,
                                    "rate_amount": rate.amount, "rate_unit": rate.unit})
        machine_rate = effective_rate(db, "machine", operations[0]["machine_rate_key"])
        part_data = as_part(part)
        results = calculate_part(part_data,
            {"amount": material_rate.amount}, {"amount": machine_rate.amount}, body.volumes,
            route_rates=[{"cycle_time_min": x["cycle_time_min"], "amount": x["rate_amount"]} for x in operation_rates])
        breakdown.append({"part_id": part.id, "part_name": part.part_name, "material": part.material,
                          "routing_operations": operation_rates, "scenarios": results, "margin_pct": part.margin_pct})
        snapshots.append({"part_id": part.id, "material_rate_id": material_rate.id,
                          "material_rate": material_rate.amount, "material_rate_key": material_rate.rate_key,
                          "material_unit": material_rate.unit, "machine_rate_id": machine_rate.id,
                          "machine_rate": machine_rate.amount, "machine_rate_key": machine_rate.rate_key,
                          "machine_unit": machine_rate.unit, "operation_rates": operation_rates})
    if not breakdown:
        raise HTTPException(422, "Add at least one part before costing.")
    reference = max(body.volumes)
    annual = sum(next(s["annual_value"] for s in row["scenarios"] if s["volume"] == reference) for row in breakdown)
    rev_no = max((r.revision_number for r in rfq.revisions), default=0) + 1
    revision = QuoteRevision(rfq_id=rfq.id, revision_number=rev_no, status="draft",
                             scenarios_json=json.dumps(body.volumes), breakdown_json=json.dumps(breakdown),
                             rate_snapshot_json=json.dumps(snapshots), annual_value=annual,
                              gst_rate_percent=GST_RATE_PERCENT,
                              formula_version="cost-v1", submitted_by=user.id)
    db.add(revision)
    db.flush()
    audit(db, user.id, "calculate_quote", "quote_revision", revision.id, f"{len(body.volumes)} volume scenarios")
    db.commit()
    return {"revision_id": revision.id, "revision_number": rev_no, "status": revision.status,
            "annual_value": annual, "reference_volume": reference, "breakdown": breakdown,
            "rate_snapshots": snapshots, "gst_rate_percent": revision.gst_rate_percent,
            "gst_annual_value": round(annual * revision.gst_rate_percent / 100, 2),
            "annual_value_including_gst": round(annual * (1 + revision.gst_rate_percent / 100), 2)}


@app.post("/api/revisions/{revision_id}/submit")
def submit_revision(revision_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    rev = db.query(QuoteRevision).options(joinedload(QuoteRevision.rfq)).filter(QuoteRevision.id == revision_id).first()
    if not rev or rev.status != "draft":
        raise HTTPException(409, "Only a saved draft can be submitted.")
    if not rev.breakdown_json or rev.breakdown_json == "[]":
        raise HTTPException(422, "Calculate the quote before submitting.")
    rev.status = "pending_approval"
    rev.submitted_by = user.id
    rev.rfq.status = "pending_approval"
    audit(db, user.id, "submit_for_approval", "quote_revision", rev.id)
    db.commit()
    return {"status": rev.status}


@app.get("/api/approvals")
def approvals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_role(user, "sales")
    rows = (db.query(QuoteRevision).options(joinedload(QuoteRevision.rfq).joinedload(RFQ.owner))
            .filter(QuoteRevision.status == "pending_approval").order_by(QuoteRevision.created_at.asc()).all())
    return {"items": [{"id": r.id, "rfq_id": r.rfq_id, "rfq_number": r.rfq.rfq_number,
                        "customer": r.rfq.customer, "owner": r.rfq.owner.display_name,
                        "annual_value": r.annual_value, "revision_number": r.revision_number,
                        "created_at": r.created_at.isoformat(), "synthetic": r.rfq.synthetic,
                        "breakdown": json.loads(r.breakdown_json), "rates": json.loads(r.rate_snapshot_json)} for r in rows]}


@app.post("/api/revisions/{revision_id}/decision")
def decision(revision_id: int, body: DecisionBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "sales")
    if body.decision not in ("approve", "return"):
        raise HTTPException(422, "Decision must be approve or return.")
    if body.decision == "return" and not (body.reason or "").strip():
        raise HTTPException(422, "Add a reason when returning a quote.")
    rev = db.query(QuoteRevision).options(joinedload(QuoteRevision.rfq)).filter(QuoteRevision.id == revision_id).first()
    if not rev or rev.status != "pending_approval":
        raise HTTPException(409, "This revision is no longer awaiting approval.")
    gate = rev.annual_value > 2_500_000
    # Every quote is reviewed in this MVP; the statutory minimum gate above is separately flagged.
    rev.status = "approved" if body.decision == "approve" else "returned"
    rev.approved_at = datetime.now(timezone.utc) if body.decision == "approve" else None
    rev.rfq.status = "approved" if body.decision == "approve" else "estimating"
    db.add(Approval(revision_id=rev.id, reviewer_id=user.id, decision=body.decision,
                    reason=(body.reason or "")[:1000] or None))
    audit(db, user.id, f"quote_{body.decision}", "quote_revision", rev.id,
          f"annual_value={rev.annual_value:.2f}; threshold_flag={gate}; reason={(body.reason or '')[:250]}")
    db.commit()
    return {"status": rev.status, "threshold_flag": gate}


@app.get("/api/revisions/{revision_id}/pdf")
def quote_pdf(revision_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rev = db.query(QuoteRevision).options(joinedload(QuoteRevision.rfq)).filter(QuoteRevision.id == revision_id).first()
    if not rev:
        raise HTTPException(404, "Quote revision not found.")
    if rev.status not in ("approved", "sent"):
        raise HTTPException(409, "Only an approved quote can be downloaded as final.")
    rfq = rev.rfq
    rows = [["Part", "Volume", "Material ₹", "Process ₹", "Overhead ₹", "Freight ₹", "Packing ₹", "Unit price ₹", "GST ₹", "Total ₹"]]
    for line in json.loads(rev.breakdown_json):
        for scenario in line["scenarios"]:
            gst = scenario["unit_price"] * rev.gst_rate_percent / 100
            rows.append([line["part_name"], f"{scenario['volume']:,}", f"{scenario['material']:,.2f}",
                         f"{scenario['processing']:,.2f}", f"{scenario['overhead']:,.2f}",
                         f"{scenario['freight']:,.2f}", f"{scenario['packing']:,.2f}", f"{scenario['unit_price']:,.2f}",
                         f"{gst:,.2f}", f"{scenario['unit_price'] + gst:,.2f}"])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=34, leftMargin=34, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = [Paragraph("FORGEQUOTE · QUOTATION", styles["Title"]), Spacer(1, 10),
             Paragraph(f"RFQ {rfq.rfq_number} · Revision {rev.revision_number}", styles["Heading2"]),
             Paragraph(f"Customer: {rfq.customer}", styles["BodyText"]),
             Paragraph(f"Status: Approved · Annual value at reference volume: ₹{rev.annual_value:,.2f}", styles["BodyText"]),
             Spacer(1, 16)]
    table = Table(rows, repeatRows=1, colWidths=[82, 42, 48, 48, 43, 42, 42, 50, 42, 48])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#182a28")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#d9dfdc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([table, Spacer(1, 14), Paragraph(
        f"GST ({rev.gst_rate_percent:.2f}%) is shown separately from unit price. "
        "Annual approval value is calculated before GST.", styles["BodyText"])])
    if rfq.synthetic:
        story.append(Spacer(1, 8))
        story.append(Paragraph("SYNTHETIC DEMO — NOT A CUSTOMER QUOTE", styles["Italic"]))
    doc.build(story)
    buffer.seek(0)
    audit(db, user.id, "download_quote_pdf", "quote_revision", rev.id)
    db.commit()
    return StreamingResponse(buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{rfq.rfq_number}-R{rev.revision_number}.pdf"'})


@app.post("/api/revisions/{revision_id}/sent")
def mark_sent(revision_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "sales")
    rev = db.query(QuoteRevision).options(joinedload(QuoteRevision.rfq)).filter(QuoteRevision.id == revision_id).first()
    if not rev or rev.status != "approved":
        raise HTTPException(409, "Only an approved revision can be marked sent.")
    rev.status = "sent"
    rev.sent_at = datetime.now(timezone.utc)
    rev.rfq.status = "sent"
    audit(db, user.id, "mark_quote_sent", "quote_revision", rev.id)
    db.commit()
    return {"status": "sent", "sent_at": rev.sent_at.isoformat()}


@app.post("/api/rfqs/{rfq_id}/outcome")
def outcome(rfq_id: int, body: DecisionBody, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "sales")
    rfq = db.query(RFQ).options(joinedload(RFQ.revisions)).filter(RFQ.id == rfq_id).first()
    if not rfq or rfq.status != "sent":
        raise HTTPException(409, "Record won/lost only after a quote is sent.")
    if body.decision not in ("won", "lost"):
        raise HTTPException(422, "Outcome must be won or lost.")
    if body.decision == "lost" and not (body.reason or "").strip():
        raise HTTPException(422, "A reason is required for a lost RFQ.")
    rfq.status = body.decision
    rfq.loss_reason = (body.reason or "").strip()[:1000] or None
    audit(db, user.id, f"rfq_{body.decision}", "rfq", rfq.id, rfq.loss_reason or "")
    db.commit()
    return {"status": rfq.status}


@app.get("/api/history")
def history(q: str = "", page: int = 1, page_size: int = 25,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Part).join(RFQ).options(joinedload(Part.rfq))
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(Part.part_name.ilike(term), Part.material.ilike(term), RFQ.rfq_number.ilike(term), RFQ.customer.ilike(term)))
    rows = query.order_by(RFQ.received_date.desc()).all()
    items = [{"rfq_id": p.rfq_id, "rfq_number": p.rfq.rfq_number, "customer": p.rfq.customer,
                        "part_name": p.part_name, "material": p.material, "gross_weight_kg": p.gross_weight_kg,
                        "annual_volume": p.annual_volume, "cycle_time_min": p.cycle_time_min,
                        "status": p.rfq.status, "synthetic": p.synthetic or p.rfq.synthetic,
                        "source_label": p.rfq.source_label, "quoted_unit_price": None,
                         "quoted_annual_value": None, "quoted_at": p.rfq.received_date.isoformat(),
                         "record_type": "active", "_sort": p.rfq.received_date} for p in rows]
    historical = db.query(HistoricalQuote)
    if q.strip():
        term = f"%{q.strip()}%"
        historical = historical.filter(or_(HistoricalQuote.part_name.ilike(term), HistoricalQuote.material.ilike(term),
            HistoricalQuote.rfq_number.ilike(term), HistoricalQuote.customer.ilike(term)))
    items.extend({"rfq_id": None, "rfq_number": h.rfq_number, "customer": h.customer,
        "part_name": h.part_name, "material": h.material, "gross_weight_kg": h.gross_weight_kg,
        "annual_volume": h.annual_volume, "cycle_time_min": h.cycle_time_min, "status": "historical",
        "synthetic": h.synthetic, "source_label": h.source_label, "quoted_unit_price": h.quoted_unit_price,
        "quoted_annual_value": h.quoted_annual_value,
        "quoted_at": h.quoted_at.isoformat() if h.quoted_at else h.created_at.date().isoformat(),
        "record_type": "historical", "_sort": h.quoted_at or h.created_at.date()}
        for h in historical.order_by(HistoricalQuote.quoted_at.desc()).all())
    items.sort(key=lambda item: (item["_sort"], item["rfq_number"]), reverse=True)
    total = len(items)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    start = (page - 1) * page_size
    selected = items[start:start + page_size]
    for item in selected:
        item.pop("_sort", None)
    return {"items": selected, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


@app.get("/api/parts/{part_id}/routing-suggestions")
async def routing_suggestions(part_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    part = db.get(Part, part_id)
    if not part:
        raise HTTPException(404, "Part not found.")
    rfq = db.get(RFQ, part.rfq_id)
    prior_parts = db.query(Part).options(joinedload(Part.rfq)).filter(Part.rfq_id != rfq.id).all()
    prior_quotes = db.query(HistoricalQuote).all()
    if not AI_NDA_APPROVED:
        prior_parts = [p for p in prior_parts if p.synthetic or p.rfq.synthetic]
        prior_quotes = [q for q in prior_quotes if q.synthetic]

    candidates = []
    target_tokens = set(re.findall(r"[a-z0-9]+", part.part_name.lower()))
    def score_candidate(name, material, weight):
        score = 3 if material.lower() == part.material.lower() else 0
        score += 2 * len(target_tokens & set(re.findall(r"[a-z0-9]+", name.lower())))
        if weight and part.gross_weight_kg:
            ratio = min(weight, part.gross_weight_kg) / max(weight, part.gross_weight_kg)
            if ratio > .75:
                score += 1
        return score

    for prior in prior_parts:
        operations = [{"operation_name": op.operation_name, "machine_rate_key": op.machine_rate_key,
                       "cycle_time_min": op.cycle_time_min} for op in prior.routing_operations]
        if not operations:
            operations = [{"operation_name": "Primary operation", "machine_rate_key": prior.machine_rate_key,
                           "cycle_time_min": prior.cycle_time_min}]
        candidates.append({"source_id": f"part-{prior.id}", "rfq_number": prior.rfq.rfq_number,
            "customer": prior.rfq.customer, "part_name": prior.part_name, "material": prior.material,
            "gross_weight_kg": prior.gross_weight_kg, "synthetic": prior.synthetic or prior.rfq.synthetic,
            "source_label": prior.rfq.source_label, "operations": operations,
            "match_score": score_candidate(prior.part_name, prior.material, prior.gross_weight_kg)})
    for quote in prior_quotes:
        if not quote.routing_key:
            continue
        operation = {"operation_name": "Recorded operation", "machine_rate_key": quote.routing_key,
                     "cycle_time_min": quote.cycle_time_min or 0}
        candidates.append({"source_id": f"quote-{quote.id}", "rfq_number": quote.rfq_number,
            "customer": quote.customer, "part_name": quote.part_name, "material": quote.material,
            "gross_weight_kg": quote.gross_weight_kg, "synthetic": quote.synthetic,
            "source_label": quote.source_label, "operations": [operation],
            "match_score": score_candidate(quote.part_name, quote.material, quote.gross_weight_kg)})
    candidates = [c for c in candidates if c["match_score"] > 0 and c["operations"]]
    candidates.sort(key=lambda c: c["match_score"], reverse=True)
    candidates = candidates[:30]
    if not candidates:
        return {"items": [], "method": "historical search", "ai_used": False, "warning": None}

    ai_allowed = bool(AI_API_KEY and (AI_NDA_APPROVED or (rfq.synthetic and all(c["synthetic"] for c in candidates))))
    method, warning = "historical similarity fallback", None
    if ai_allowed:
        prompt = ("Rank up to five similar parts and their recorded routing operations for this target part. "
                  "Return JSON {suggestions:[{source_id,reason}]}. Choose only source_id values provided. "
                  "Do not invent operations or change operation names, machine rate keys, or cycle times. "
                  "Reasons must describe evidence in the supplied record.\n"
                  f"Target: {json.dumps({'part_name': part.part_name, 'material': part.material, 'gross_weight_kg': part.gross_weight_kg})}\n"
                  f"Historical candidates: {json.dumps(candidates, ensure_ascii=False)}")
        try:
            raw = await gateway_chat([
                {"role": "system", "content": "You rank historical manufacturing routes. Cite only supplied source IDs; do not invent or edit route steps. Return JSON only."},
                {"role": "user", "content": prompt}], json_mode=True)
            parsed = json.loads(raw)
            by_id = {c["source_id"]: c for c in candidates}
            ranked = []
            for suggestion in parsed.get("suggestions", []):
                candidate = by_id.get(str(suggestion.get("source_id", "")))
                if candidate and candidate["source_id"] not in [x["source_id"] for x in ranked]:
                    ranked.append({**candidate, "suggestion": str(suggestion.get("reason") or "Similar historical part; estimator review required.")[:240]})
            if ranked:
                candidates, method = ranked, f"AI-ranked historical routes · {AI_MODEL}"
            else:
                warning = "The model returned no valid historical citations; showing attribute matches."
        except (HTTPException, json.JSONDecodeError, TypeError, ValueError):
            warning = "AI ranking is unavailable; showing attribute matches."
    items = []
    for candidate in candidates[:5]:
        operations = candidate["operations"]
        items.append({**candidate, "routing_key": operations[0]["machine_rate_key"],
            "cycle_time_min": operations[0]["cycle_time_min"],
            "suggestion": candidate.get("suggestion", "Review this prior route; estimator acceptance is required.")})
    return {"items": items, "method": method, "ai_used": method.startswith("AI-ranked"), "warning": warning}


def storage_headers():
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise HTTPException(503, "Supabase Storage is not configured. Add SUPABASE_URL and SUPABASE_SECRET_KEY to the private environment.")
    return {"apikey": SUPABASE_SECRET_KEY}


def ensure_private_storage_bucket():
    headers = storage_headers()
    base = f"{SUPABASE_URL}/storage/v1/bucket/{quote(SUPABASE_STORAGE_BUCKET, safe='')}"
    try:
        with httpx.Client(timeout=20) as client:
            response = client.get(base, headers=headers)
            missing_bucket = response.status_code == 404
            if response.status_code == 400:
                try:
                    missing_bucket = response.json().get("message") == "Bucket not found"
                except ValueError:
                    missing_bucket = False
            if missing_bucket:
                response = client.post(f"{SUPABASE_URL}/storage/v1/bucket", headers=headers, json={
                    "id": SUPABASE_STORAGE_BUCKET, "name": SUPABASE_STORAGE_BUCKET,
                    "public": False, "file_size_limit": MAX_UPLOAD,
                    "allowed_mime_types": ["text/plain", "message/rfc822", "text/csv",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "application/pdf", "image/png", "image/jpeg", "image/tiff", "image/bmp"]})
            response.raise_for_status()
            bucket = response.json()
            if bucket.get("public") is True:
                raise HTTPException(503, "The configured RFQ source bucket is public. Make it private before uploading documents.")
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Supabase Storage bucket request failed ({exc.response.status_code}).") from exc
    except Exception as exc:
        raise HTTPException(502, f"Supabase Storage is unavailable ({type(exc).__name__}).") from exc


def store_source_file(file_id: str, media_type: str, payload: bytes):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        (UPLOAD_DIR / file_id).write_bytes(payload)
        return
    ensure_private_storage_bucket()
    url = f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_STORAGE_BUCKET, safe='')}/{quote(file_id, safe='')}"
    try:
        response = httpx.post(url, headers={**storage_headers(), "Content-Type": media_type,
            "x-upsert": "false", "cache-control": "3600"}, content=payload, timeout=60)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Supabase Storage upload failed ({exc.response.status_code}); RFQ source was not saved.") from exc
    except Exception as exc:
        raise HTTPException(502, f"Supabase Storage upload failed ({type(exc).__name__}); RFQ source was not saved.") from exc


def retrieve_source_file(file_id: str) -> bytes:
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        path = UPLOAD_DIR / file_id
        if not path.is_file():
            raise HTTPException(404, "Source file is missing from local storage.")
        return path.read_bytes()
    url = f"{SUPABASE_URL}/storage/v1/object/authenticated/{quote(SUPABASE_STORAGE_BUCKET, safe='')}/{quote(file_id, safe='')}"
    try:
        response = httpx.get(url, headers=storage_headers(), timeout=60)
        if response.status_code == 404:
            raise HTTPException(404, "Source file is missing from Supabase Storage.")
        response.raise_for_status()
        return response.content
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Supabase Storage download failed ({exc.response.status_code}).") from exc
    except Exception as exc:
        raise HTTPException(502, f"Supabase Storage is unavailable ({type(exc).__name__}).") from exc


def persist_source(db: Session, user: User, filename: str, media_type: str | None,
                   payload: bytes, rfq_id: int | None = None) -> RFQSource:
    clean_name = Path(filename.replace("\\", "/")).name[:255] or "source"
    suffix = Path(clean_name).suffix.lower()
    if suffix not in {".txt", ".eml", ".csv", ".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        raise HTTPException(415, "Use email/text, XLSX, PDF, or a PNG/JPEG/TIFF/BMP drawing image.")
    file_id = f"{uuid.uuid4().hex}{suffix}"
    safe_media_type = (media_type or "application/octet-stream")[:120]
    store_source_file(file_id, safe_media_type, payload)
    source = RFQSource(file_id=file_id, rfq_id=rfq_id, uploaded_by=user.id,
        original_filename=clean_name, media_type=safe_media_type,
        size_bytes=len(payload))
    db.add(source)
    db.flush()
    return source


def extract_xlsx_parts(text: str, filename: str) -> list[dict]:
    aliases = {
        "part_name": {"part", "part_name", "part_no", "part_number", "item", "item_name", "item_description", "description"},
        "material": {"material", "alloy", "grade", "material_grade"},
        "gross_weight_kg": {"gross_weight_kg", "gross_weight", "gross_wt_kg", "weight_kg", "weight"},
        "annual_volume": {"annual_volume", "annual_qty", "yearly_volume", "volume", "qty", "quantity"},
        "cycle_time_min": {"cycle_time_min", "cycle_time", "cycle_min", "minutes_per_part"},
        "machine_rate_key": {"machine_rate_key", "machine_rate", "routing_key", "routing", "machine", "operation"},
    }
    rows = []
    for line in text.splitlines():
        if not re.match(r"^.+ row \d+: ", line):
            continue
        values = {}
        for cell in line.split(": ", 1)[-1].split("; "):
            if "=" not in cell:
                continue
            key, value = cell.split("=", 1)
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            match = next((name for name, names in aliases.items() if normalized in names), None)
            if match and value.strip():
                value = value.strip()
                if match in {"gross_weight_kg", "annual_volume", "cycle_time_min"}:
                    number = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
                    if number:
                        value = number.group(0).replace(",", "")
                values[match] = value
        if not values.get("part_name"):
            continue
        rows.append({"values": values, "source": {"file": filename, "excerpt": line[:1000]}})
    return rows[:100]


def read_upload(filename: str, payload: bytes):
    suffix = Path(filename).suffix.lower()
    if suffix in (".txt", ".eml", ".csv"):
        return payload.decode("utf-8", errors="replace"), "text"
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError:
            reader = PdfReader(io.BytesIO(payload))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text, "pdf-text"
        document = fitz.open(stream=payload, filetype="pdf")
        page_text, used_ocr = [], False
        for page_index, page in enumerate(document):
            text = page.get_text("text").strip()
            if not text:
                if page_index >= MAX_OCR_PAGES:
                    raise HTTPException(422, f"Scanned drawing exceeds the {MAX_OCR_PAGES}-page local OCR limit.")
                pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
                from PIL import Image
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                text = ocr_image(image)
                used_ocr = True
            page_text.append(f"Page {page_index + 1}: {text}" if text else f"Page {page_index + 1}:")
        return "\n".join(page_text), "pdf-ocr" if used_ocr else "pdf-text"
    if suffix in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        from PIL import Image
        try:
            image = Image.open(io.BytesIO(payload))
            return ocr_image(image), "image-ocr"
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, "The image could not be read for OCR.") from exc
    if suffix == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
        parts = []
        for sheet in wb.worksheets:
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, None)
            if headers is None:
                continue
            labels = [str(value).strip() if value is not None else f"Column {index + 1}"
                      for index, value in enumerate(headers)]
            for row_no, row in enumerate(rows, 2):
                cells = [f"{labels[i]}={value}" for i, value in enumerate(row)
                         if value is not None and i < len(labels)]
                if cells:
                    parts.append(f"{sheet.title} row {row_no}: " + "; ".join(cells))
            if not any(part.startswith(f"{sheet.title} row ") for part in parts):
                fallback_rows = list(sheet.iter_rows(values_only=True))
                cells = [f"{sheet.title}!{i + 1}={v}" for i, v in enumerate(fallback_rows[0]) if v is not None]
                if cells:
                    parts.append(f"{sheet.title} row 1: " + "; ".join(cells))
        return "\n".join(parts), "xlsx"
    raise HTTPException(415, "Use email/text, XLSX, PDF, or a PNG/JPEG/TIFF/BMP drawing image.")


def ocr_image(image):
    try:
        import pytesseract
    except ImportError as exc:
        raise HTTPException(503, "Local OCR dependencies are missing. Install the requirements and retry.") from exc
    command = os.getenv("TESSERACT_CMD", "").strip()
    if command:
        pytesseract.pytesseract.tesseract_cmd = command
    try:
        return pytesseract.image_to_string(image, lang=os.getenv("OCR_LANGUAGE", "eng"), config="--psm 6")
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(503, "Local OCR needs Tesseract installed. Set TESSERACT_CMD to its executable and retry.") from exc


def rule_extract(text: str, filename: str):
    patterns = {
        "customer": r"\bcustomer(?:\s+name)?\s*[:=]\s*([^;\n]+)",
        "due_date": r"\bdue\s*date\s*[:=]\s*(\d{4}-\d{2}-\d{2})\b",
        "part_name": r"\bpart(?:\s+name|\s+description)?\s*[:=]\s*([^;\n]+)",
        "gross_weight_kg": r"(?:gross\s*(?:wt|weight)(?:\s*kg)?|weight\s*kg)\s*[:=]\s*([\d,]+(?:\.\d+)?)\s*(?:kg)?\b",
        "annual_volume": r"\b(?:annual\s*volume|volume|qty)\s*[:=]\s*([\d,]+)\b",
        "cycle_time_min": r"\bcycle\s*time(?:\s*min)?\s*[:=]\s*([\d,]+(?:\.\d+)?)\s*(?:min|minutes)?\b",
        "machine_rate": r"\bmachine\s*rate\s*[:=]\s*([^;\n]+)",
    }
    fields = []
    for name, pattern in patterns.items():
        m = re.search(pattern, text, re.I)
        if m:
            val = m.group(1).replace(",", "").strip()
            fields.append({"name": name, "value": val, "source": {"file": filename,
                           "excerpt": text[max(0, m.start() - 30):min(len(text), m.end() + 30)].strip()},
                           "confidence": 0.78, "status": "suggested", "method": "local pattern extraction"})
    rfq = re.search(r"\bRFQ\s+(?:number|no\.?)\s*[:=]\s*([A-Z0-9][A-Z0-9-]{3,})", text, re.I)
    if not rfq:
        rfq = re.search(r"\b(RFQ[-#][A-Z0-9][A-Z0-9-]{3,})\b", text, re.I)
    if rfq:
        fields.insert(0, {"name": "rfq_number", "value": rfq.group(1).strip(),
            "source": {"file": filename, "excerpt": text[max(0, rfq.start() - 30):min(len(text), rfq.end() + 30)].strip()},
            "confidence": 0.8, "status": "suggested", "method": "local pattern extraction"})
    material = re.search(r"\b(EN\s?8|EN\s?19|EN\s?24|20MnCr5|40Cr4(?:\s+forging)?|C45|Aluminium\s+\d+)\b", text, re.I)
    if material:
        fields.append({"name": "material", "value": material.group(0), "source": {"file": filename,
                       "excerpt": text[max(0, material.start() - 30):min(len(text), material.end() + 30)].strip()},
                       "confidence": 0.75, "status": "suggested", "method": "local pattern extraction"})
    return fields


async def ai_extract(text: str, filename: str):
    prompt = (
        "Extract only these RFQ facts when directly present: rfq_number, customer, due_date, part_name, material, "
        "gross_weight_kg, annual_volume, cycle_time_min, machine_rate. Return JSON {fields:[{name,value,source_excerpt,confidence}]}. "
        "source_excerpt must be an exact substring from the source text. Leave unsupported facts out. Never calculate cost, "
        "price, margin, tax, or invent a routing. Source file: " + filename + "\n\nSOURCE TEXT:\n" + text[:24000]
    )
    raw = await gateway_chat([
        {"role": "system", "content": "You extract RFQ fields conservatively. Do not infer absent values. Return valid JSON only."},
        {"role": "user", "content": prompt}], json_mode=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(503, "The model returned unreadable structured output. No values were applied.")
    allowed = {"rfq_number", "customer", "due_date", "part_name", "material", "gross_weight_kg",
               "annual_volume", "cycle_time_min", "machine_rate"}
    accepted = []
    for field in data.get("fields", []):
        name = str(field.get("name", ""))
        value = str(field.get("value", "")).strip()
        excerpt = str(field.get("source_excerpt", "")).strip()
        if name in allowed and value and excerpt and excerpt.casefold() in text.casefold():
            accepted.append({"name": name, "value": value,
                "source": {"file": filename, "excerpt": excerpt},
                "confidence": max(0.0, min(1.0, float(field.get("confidence", 0.5)))),
                "status": "suggested", "method": f"AI model: {AI_MODEL}"})
    return accepted


async def gateway_chat(messages: list[dict], json_mode: bool = False, max_tokens: int = 1800):
    if not AI_API_KEY:
        raise HTTPException(503, "AI is not configured. Add a rotated AI_API_KEY privately; no AI result was generated.")
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            headers = {
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json",
                "originator": os.getenv("AI_ORIGINATOR", "codex_cli_rs"),
                "User-Agent": os.getenv("AI_USER_AGENT", "codex_cli_rs/0.149.1"),
            }
            if AI_PROTOCOL in ("openai", "responses"):
                conversation = [{"role": message["role"], "content": message["content"]} for message in messages]
                if json_mode:
                    conversation[-1]["content"] += "\n\nReturn only a valid JSON object. Do not include markdown fences."
                base = AI_BASE_URL if AI_BASE_URL.endswith("/v1") else f"{AI_BASE_URL}/v1"
                use_responses = (
                    AI_PROTOCOL == "responses"
                    or "agentrouter" in AI_BASE_URL.lower()
                    or AI_BASE_URL.rstrip("/").endswith("/responses")
                )
                if use_responses:
                    endpoint = f"{base}/responses" if not base.endswith("/responses") else base
                    payload = {"model": AI_MODEL, "input": conversation}
                    if max_tokens:
                        payload["max_output_tokens"] = max(max_tokens, 4096)
                    response = await client.post(endpoint, headers=headers, json=payload)
                    if response.status_code == 400 and "/chat/completions" in response.text:
                        chat_payload = {"model": AI_MODEL, "max_tokens": max_tokens, "messages": conversation}
                        if json_mode:
                            chat_payload["response_format"] = {"type": "json_object"}
                        response = await client.post(f"{base}/chat/completions", headers=headers, json=chat_payload)
                else:
                    payload = {"model": AI_MODEL, "max_tokens": max_tokens, "messages": conversation}
                    if json_mode:
                        payload["response_format"] = {"type": "json_object"}
                    response = await client.post(f"{base}/chat/completions", headers=headers, json=payload)
                    if response.status_code == 400 and "/v1/responses" in response.text:
                        resp_payload = {"model": AI_MODEL, "input": conversation}
                        if max_tokens:
                            resp_payload["max_output_tokens"] = max_tokens
                        response = await client.post(f"{base}/responses", headers=headers, json=resp_payload)
            elif AI_PROTOCOL == "anthropic":
                system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
                conversation = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
                if json_mode:
                    conversation[-1]["content"] += "\n\nReturn only a valid JSON object. Do not include markdown fences."
                anthropic_headers = {
                    "x-api-key": AI_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                response = await client.post(f"{AI_BASE_URL}/v1/messages", headers=anthropic_headers, json={
                    "model": AI_MODEL, "max_tokens": max_tokens, "system": system, "messages": conversation})
            else:
                raise HTTPException(500, "AI_PROTOCOL must be 'openai', 'responses', or 'anthropic'.")
            if response.status_code in (401, 403):
                raise HTTPException(503, f"AI gateway rejected the configured key or client ({response.status_code}); no result was generated.")
        response.raise_for_status()
        data = response.json()
        content = ""
        if "choices" in data and data["choices"]:
            msg_content = data["choices"][0].get("message", {}).get("content", "")
            if isinstance(msg_content, list):
                content = "".join(item.get("text", "") for item in msg_content if isinstance(item, dict))
            else:
                content = str(msg_content or "")
        elif "output" in data and isinstance(data["output"], list):
            text_parts = []
            for item in data["output"]:
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            text_parts.append(c.get("text", ""))
                        elif isinstance(c, str):
                            text_parts.append(c)
                elif "text" in item:
                    text_parts.append(item["text"])
            content = "".join(text_parts)
        elif "content" in data and isinstance(data["content"], list):
            content = "".join(block.get("text", "") for block in data["content"] if isinstance(block, dict) and block.get("type") == "text")

        content = str(content).strip()
        if json_mode and content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content).strip()

        if not content:
            raise HTTPException(503, "AI gateway returned no text; no result was generated.")
        AI_LAST_CHECK.update(ok=True, error=None, at=datetime.now(timezone.utc).isoformat())
        return content
    except HTTPException as exc:
        AI_LAST_CHECK.update(ok=False, error=exc.detail, at=datetime.now(timezone.utc).isoformat())
        raise
    except httpx.HTTPStatusError as exc:
        detail = f"AI gateway returned HTTP {exc.response.status_code}; no result was generated."
        AI_LAST_CHECK.update(ok=False, error=detail, at=datetime.now(timezone.utc).isoformat())
        raise HTTPException(503, detail)
    except Exception as exc:
        detail = f"AI gateway is unavailable; no result was generated ({type(exc).__name__})."
        AI_LAST_CHECK.update(ok=False, error=detail, at=datetime.now(timezone.utc).isoformat())
        raise HTTPException(503, detail)


@app.get("/api/assistant/status")
async def assistant_status(check: bool = False, user: User = Depends(get_current_user)):
    if not AI_API_KEY:
        return {"available": False, "configured": False, "label": "AI key not configured", "model": AI_MODEL,
                "protocol": AI_PROTOCOL, "nda_approved": AI_NDA_APPROVED, "last_error": None}
    if check or AI_LAST_CHECK["ok"] is None:
        try:
            await gateway_chat([{"role": "user", "content": "ping"}], max_tokens=500)
        except Exception:
            pass
    available = AI_LAST_CHECK["ok"] is True
    label = "AI gateway reachable" if available else "AI gateway unavailable" if AI_LAST_CHECK["ok"] is False else "AI status unverified"
    return {"available": available, "configured": True, "label": label, "model": AI_MODEL,
            "protocol": AI_PROTOCOL, "nda_approved": AI_NDA_APPROVED,
            "last_error": AI_LAST_CHECK["error"], "last_checked_at": AI_LAST_CHECK["at"]}


@app.post("/api/rfqs/{rfq_id}/sources")
async def add_source(rfq_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    rfq = db.get(RFQ, rfq_id)
    if not rfq:
        raise HTTPException(404, "RFQ not found.")
    payload = await file.read(MAX_UPLOAD + 1)
    if len(payload) > MAX_UPLOAD:
        raise HTTPException(413, "File exceeds the 12 MB demo limit.")
    source = persist_source(db, user, file.filename or "source", file.content_type, payload, rfq.id)
    audit(db, user.id, "upload_source", "rfq", rfq.id, source.original_filename)
    db.commit()
    return as_source(source)


@app.post("/api/intake/extract")
async def extract_intake(request: Request, body: IntakeExtractBody, user: User = Depends(get_current_user)):
    require_csrf(request)
    if AI_API_KEY and AI_NDA_APPROVED:
        fields = await ai_extract(body.text, body.filename)
        return {"fields": fields, "ai_used": True, "note": "Model suggestions require estimator review."}
    return {"fields": rule_extract(body.text, body.filename), "ai_used": False,
            "note": "Local pattern suggestions only; no AI model ran. Review every value."}


@app.post("/api/intake/file-extract")
async def extract_intake_file(request: Request, file: UploadFile = File(...), demo_only: bool = Form(False),
                              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    payload = await file.read(MAX_UPLOAD + 1)
    if len(payload) > MAX_UPLOAD:
        raise HTTPException(413, "File exceeds the 12 MB demo limit.")
    source = persist_source(db, user, file.filename or "source", file.content_type, payload)
    try:
        text, method = read_upload(file.filename or "source", payload)
        if not text.strip():
            raise HTTPException(422, "No readable text was found. The original file is retained; enter title-block values manually.")
        source.extraction_method = method
        allow_model = bool(AI_API_KEY and (AI_NDA_APPROVED or demo_only))
        fields = await ai_extract(text, file.filename or "source") if allow_model else rule_extract(text, file.filename or "source")
        parts = extract_xlsx_parts(text, file.filename or "source") if method == "xlsx" else []
    except (HTTPException, Exception) as exc:
        source.extraction_error = exc.detail if isinstance(exc, HTTPException) else f"Extraction failed: {exc}"
        method, allow_model, fields, parts = "unavailable", False, [], []
    db.commit()
    return {"file_id": source.file_id, "filename": source.original_filename, "method": method,
            "ai_used": allow_model, "fields": fields, "parts": parts,
            "note": "Model suggestions require estimator review." if allow_model else
                "Original retained. Local pattern suggestions only; no AI model ran. Review every value.",
            "extraction_error": source.extraction_error}


@app.get("/api/sources/{file_id}")
def get_source(file_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not re.fullmatch(r"[a-f0-9]{32}\.(?:txt|eml|csv|pdf|xlsx|png|jpe?g|tiff?|bmp)", file_id):
        raise HTTPException(404, "Source not found.")
    source = db.query(RFQSource).filter_by(file_id=file_id).first()
    if not source or (source.rfq_id is None and source.uploaded_by != user.id):
        raise HTTPException(404, "Source not found.")
    payload = retrieve_source_file(file_id)
    filename = quote(source.original_filename, safe="")
    return Response(payload, media_type=source.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"})


@app.post("/api/assistant/chat")
async def assistant_chat(body: AssistantBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not AI_API_KEY:
        raise HTTPException(503, "AI is not configured. Add a rotated AI_API_KEY privately; no AI answer was generated.")
    selected = None
    current_parts = []
    if body.rfq_id:
        selected = db.get(RFQ, body.rfq_id)
        if selected and not selected.synthetic and not AI_NDA_APPROVED:
            raise HTTPException(403, "Hosted AI with customer RFQ data is disabled until NDA/no-training terms are approved.")
        if selected:
            current_parts = db.query(Part).filter(Part.rfq_id == selected.id).all()
    terms = [t for t in re.findall(r"[\w-]{3,}", body.question.lower()) if t not in {"which", "what", "show", "similar", "past", "part"}]
    history_query = db.query(HistoricalQuote)
    if not AI_NDA_APPROVED:
        history_query = history_query.filter(HistoricalQuote.synthetic.is_(True))
    match_terms = list(terms)
    for p in current_parts:
        match_terms.extend([t for t in re.findall(r"[\w-]{3,}", (p.part_name + " " + p.material).lower())])
    match_terms = list(dict.fromkeys(match_terms))
    if match_terms:
        history_query = history_query.filter(or_(*[
            condition for term in match_terms[:12]
            for condition in (HistoricalQuote.part_name.ilike(f"%{term}%"),
                             HistoricalQuote.material.ilike(f"%{term}%"),
                             HistoricalQuote.rfq_number.ilike(f"%{term}%"))
        ]))
    history_rows = history_query.order_by(HistoricalQuote.quoted_at.desc()).limit(12).all()
    sources = [{"rfq_number": p.rfq.rfq_number, "customer": p.rfq.customer, "part": p.part_name, "part_name": p.part_name,
                "material": p.material, "weight_kg": p.gross_weight_kg, "cycle_min": p.cycle_time_min,
                "routing_key": p.machine_rate_key,
                "volume": p.annual_volume, "synthetic": p.synthetic or p.rfq.synthetic,
                "source_label": p.rfq.source_label} for p in current_parts]
    sources.extend({"rfq_number": h.rfq_number, "customer": h.customer, "part": h.part_name, "part_name": h.part_name,
            "material": h.material, "weight_kg": h.gross_weight_kg, "cycle_min": h.cycle_time_min,
            "routing_key": h.routing_key,
            "volume": h.annual_volume, "synthetic": True, "source_label": h.source_label}
            if h.synthetic else {"rfq_number": h.rfq_number, "customer": h.customer, "part": h.part_name, "part_name": h.part_name,
            "material": h.material, "weight_kg": h.gross_weight_kg, "cycle_min": h.cycle_time_min,
            "routing_key": h.routing_key, "volume": h.annual_volume, "synthetic": False,
            "source_label": h.source_label} for h in history_rows)
    context = json.dumps(sources, ensure_ascii=False)
    answer = await gateway_chat([
        {"role": "system", "content": "You are ForgeQuote's assistive RFQ intake and historical-part assistant. Use only the JSON source records supplied in this conversation. You may suggest a routing key or operation pattern only when a cited historical record contains it, and you must call it a suggestion for estimator review. Do not invent facts, calculate costs/prices/taxes, choose final routing, or approve quotes. Cite source RFQ number and part for every factual statement. State when the records do not support an answer. Mark synthetic demo records as synthetic. Format answers for a business UI: start with one short takeaway; when listing or comparing multiple records, use a Markdown table with clear column headers and one record per row; put headings, bullets, and each table row on separate lines; never put an entire table on one line; avoid raw JSON and code fences."},
        {"role": "user", "content": f"Question: {body.question}\nAccessible historical source records: {context}"}
    ])
    return {"answer": answer, "sources": sources, "model": AI_MODEL}


@app.post("/api/imports/preview")
async def import_preview(request: Request, file: UploadFile = File(...), mapping: str = Form(""),
                         sheet_name: str = Form(""),
                         force_synthetic: bool = Form(False), db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    if Path(file.filename or "").suffix.lower() != ".xlsx":
        raise HTTPException(415, "Upload an .xlsx workbook.")
    from openpyxl import load_workbook
    payload = await file.read(MAX_UPLOAD + 1)
    if len(payload) > MAX_UPLOAD:
        raise HTTPException(413, "File exceeds the 12 MB demo limit.")
    wb = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    if sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
    else:
        sheet = next((candidate for candidate in [wb.active, *wb.worksheets]
                      if candidate.max_row >= 2 and candidate.max_column >= 2), wb.active)
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows) < 2:
        raise HTTPException(422, "Workbook needs a header row and at least one data row.")
    display_headers = [str(v or "").strip() or f"Column {index + 1}" for index, v in enumerate(rows[0])]
    headers = [v.lower().replace(" ", "_") for v in display_headers]
    aliases = {"rfq_number": ["rfq", "rfq_no", "rfq_number"], "customer": ["customer", "customer_name"],
        "part_name": ["part", "part_name", "description"], "material": ["material"],
        "gross_weight_kg": ["gross_wt_kg", "gross_weight_kg", "weight_kg"],
        "annual_volume": ["annual_volume", "volume", "qty"], "cycle_time_min": ["cycle_time_min", "cycle_min", "cycle_time"],
        "machine_rate": ["hour_rate", "hour_rate_inr", "machine_hour_rate"],
        "quoted_unit_price": ["quoted_unit_price", "unit_price", "price_per_part"],
        "quoted_annual_value": ["quoted_annual_value", "annual_quote_value", "annual_value"],
        "quoted_at": ["quoted_at", "quote_date", "date"],
        "routing_key": ["routing", "routing_key", "machine", "operation"],
        "synthetic": ["synthetic", "is_synthetic", "synthetic_flag", "demo"]}
    suggested = {key: next((headers.index(alias) for alias in options if alias in headers), None)
                 for key, options in aliases.items()}
    if not mapping:
        required_fields = ("rfq_number", "customer", "part_name", "material", "gross_weight_kg", "annual_volume", "cycle_time_min")
        return {"needs_mapping": True, "headers": [{"index": i, "label": label} for i, label in enumerate(display_headers)],
                "sheets": wb.sheetnames, "sheet_name": sheet.title,
                "suggested_mapping": suggested,
                "fields": [{"key": key, "required": key in required_fields} for key in aliases],
                "sample_rows": [list(row) for row in rows[1:4]], "source_rows": len(rows) - 1}
    try:
        selected = json.loads(mapping)
        if not isinstance(selected, dict):
            raise ValueError
        mapped = {key: int(value) if str(value).isdigit() and 0 <= int(value) < len(display_headers) else None
                  for key, value in selected.items() if key in aliases and value is not None and value != ""}
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(422, "Column mapping is invalid. Re-select the workbook columns.")
    selected_indices = [index for index in mapped.values() if index is not None]
    if len(selected_indices) != len(set(selected_indices)):
        raise HTTPException(422, "Map each workbook column to only one field.")
    for key in aliases:
        mapped.setdefault(key, None)
    required = ("rfq_number", "customer", "part_name", "material", "gross_weight_kg", "annual_volume", "cycle_time_min")
    missing = [key for key in required if mapped[key] is None]
    if missing:
        raise HTTPException(422, "Missing required columns: " + ", ".join(missing))
    preview, errors = [], []
    existing_rfq_numbers = {number for (number,) in db.query(RFQ.rfq_number).all()}
    workbook_rfq_numbers = set()
    for i, row in enumerate(rows[1:], 2):
        item = {key: row[idx] if idx is not None and idx < len(row) else None for key, idx in mapped.items()}
        try:
            item["rfq_number"] = str(item["rfq_number"]).strip()
            item["customer"] = str(item["customer"]).strip()
            item["part_name"] = str(item["part_name"]).strip()
            item["material"] = str(item["material"]).strip()
            item["gross_weight_kg"] = float(item["gross_weight_kg"])
            item["annual_volume"] = int(float(item["annual_volume"]))
            item["cycle_time_min"] = float(item["cycle_time_min"])
            if item.get("quoted_unit_price") not in (None, ""):
                item["quoted_unit_price"] = float(item["quoted_unit_price"])
            if item.get("quoted_annual_value") not in (None, ""):
                item["quoted_annual_value"] = float(item["quoted_annual_value"])
            if item.get("quoted_at"):
                item["quoted_at"] = str(item["quoted_at"])
            item["synthetic"] = bool(force_synthetic or str(item.get("synthetic") or "").strip().lower()
                                    in {"true", "1", "yes", "y", "synthetic", "demo"})
            if item["gross_weight_kg"] <= 0 or item["annual_volume"] <= 0 or item["cycle_time_min"] < 0:
                raise ValueError("Weight/volume must be positive and cycle non-negative")
            if item["rfq_number"] in existing_rfq_numbers or item["rfq_number"] in workbook_rfq_numbers:
                raise ValueError("RFQ number already exists")
            workbook_rfq_numbers.add(item["rfq_number"])
            preview.append({"row": i, **item})
        except Exception as exc:
            errors.append({"row": i, "reason": str(exc)})
    token = uuid.uuid4().hex
    (UPLOAD_DIR / f"import-{token}.json").write_text(json.dumps(preview), encoding="utf-8")
    return {"needs_mapping": False, "batch_id": token, "valid_count": len(preview), "error_count": len(errors),
            "preview": preview[:12], "errors": errors[:60], "source_rows": len(rows) - 1,
            "sheet_name": sheet.title}


@app.post("/api/imports/{batch_id}/commit")
def import_commit(batch_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_csrf(request)
    require_role(user, "estimator")
    path = UPLOAD_DIR / f"import-{batch_id}.json"
    if not re.fullmatch(r"[a-f0-9]{32}", batch_id) or not path.exists():
        raise HTTPException(404, "Import preview expired or missing.")
    rows = json.loads(path.read_text(encoding="utf-8"))
    added = 0
    existing_rfq_numbers = {number for (number,) in db.query(RFQ.rfq_number).all()}
    for item in rows:
        if item["rfq_number"] in existing_rfq_numbers:
            continue
        existing_rfq_numbers.add(item["rfq_number"])
        quoted_at = None
        if item.get("quoted_at"):
            try:
                quoted_at = date.fromisoformat(item["quoted_at"][:10])
            except ValueError:
                quoted_at = None
        db.add(HistoricalQuote(batch_id=batch_id, source_row=int(item["row"]), rfq_number=item["rfq_number"],
            customer=item["customer"], part_name=item["part_name"], material=item["material"],
            gross_weight_kg=item["gross_weight_kg"], annual_volume=item["annual_volume"],
            cycle_time_min=item["cycle_time_min"], quoted_unit_price=item.get("quoted_unit_price"),
            quoted_annual_value=item.get("quoted_annual_value"), quoted_at=quoted_at,
            routing_key=str(item.get("routing_key") or "").strip() or None,
            source_label=f"{'Synthetic demo import' if item.get('synthetic') else 'Imported history'} · row {item['row']}",
            synthetic=bool(item.get("synthetic"))))
        added += 1
    audit(db, user.id, "import_history", "import_batch", batch_id, f"rows={added}")
    db.commit()
    path.unlink(missing_ok=True)
    return {"imported": added, "source_rows": len(rows), "message": f"Imported {added} historical part rows."}
