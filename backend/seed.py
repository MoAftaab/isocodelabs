import random
import json
from datetime import date, datetime, timedelta, timezone

from .costing import calculate_part
from .models import Approval, HistoricalQuote, Part, QuoteRevision, RFQ, RateVersion, RoutingOperation, User
from .security import password_hash

MATERIAL_RATES = {
    "EN8": 118.0, "40Cr4 forging": 94.0, "20MnCr5": 142.0,
    "EN19": 176.0, "EN24": 212.0, "C45": 108.0,
    "Aluminium 6061": 286.0, "MS": 72.0,
}
PARTS = [
    ("Rear wheel spindle", "EN8", 0.61, 3.2),
    ("Hydraulic lift arm", "40Cr4 forging", 4.60, 11.5),
    ("Gear blank", "20MnCr5", 1.48, 4.8),
    ("Front axle pin", "EN19", 1.24, 5.1),
    ("PTO coupling hub", "EN24", 2.35, 7.4),
    ("Brake cam shaft", "C45", 0.82, 3.8),
    ("Steering knuckle", "40Cr4 forging", 3.25, 9.6),
    ("Clutch sleeve", "EN8", 0.94, 4.2),
    ("Bearing retainer", "MS", 0.48, 2.1),
    ("Engine spacer", "Aluminium 6061", 0.36, 1.8),
]
MACHINE_RATES = {"Turning cell": 850.0, "Forging machining": 1450.0, "Gear cutting": 950.0,
                 "General machining": 920.0, "Precision grinding": 1280.0}


def seed_database(db):
    if db.query(User).first():
        if not db.query(User).filter_by(username="estimator2@demo.local").first():
            db.add(User(username="estimator2@demo.local", display_name="Nisha · Estimator", role="estimator",
                        password_hash=password_hash("estimate2-demo")))
        for part in db.query(Part).filter(Part.synthetic.is_(True)).all():
            if part.id % 2 == 0 and not part.routing_operations:
                first_cycle = round(part.cycle_time_min * 0.7, 1)
                second_cycle = round(part.cycle_time_min - first_cycle, 1)
                if second_cycle > 0:
                    part.cycle_time_min = first_cycle
                    part.routing_operations.extend([
                        RoutingOperation(sequence_no=1, operation_name="Primary machining",
                                          machine_rate_key=part.machine_rate_key, cycle_time_min=first_cycle),
                        RoutingOperation(sequence_no=2, operation_name="Finish grinding",
                                          machine_rate_key="Precision grinding", cycle_time_min=second_cycle),
                    ])
            db.commit()
        return
    estimator = User(username="estimator@demo.local", display_name="Aarav · Estimator", role="estimator",
                     password_hash=password_hash("estimate-demo"))
    estimator_two = User(username="estimator2@demo.local", display_name="Nisha · Estimator", role="estimator",
                         password_hash=password_hash("estimate2-demo"))
    sales = User(username="sales@demo.local", display_name="Mira · Sales Head", role="sales",
                 password_hash=password_hash("approve-demo"))
    db.add_all([estimator, estimator_two, sales])
    db.flush()
    today = date.today()

    material_rows, machine_rows = {}, {}
    for key, amount in MATERIAL_RATES.items():
        row = RateVersion(rate_type="material", rate_key=key, unit="₹ / kg", amount=amount,
                          effective_from=today - timedelta(days=120), synthetic=True)
        db.add(row)
        material_rows[key] = row
    for key, amount in MACHINE_RATES.items():
        row = RateVersion(rate_type="machine", rate_key=key, unit="₹ / hour", amount=amount,
                          effective_from=today - timedelta(days=120), synthetic=True)
        db.add(row)
        machine_rows[key] = row
    db.flush()

    provided = [
        ("RFQ-2611-014", "Company B (two-wheelers)", PARTS[0], 180000, 850),
        ("RFQ-2611-019", "Company C (tractors)", PARTS[1], 24000, 1450),
        ("RFQ-2611-023", "Company D (drivetrains)", PARTS[2], 60000, 950),
    ]
    for number, customer, part, volume, hour_rate in provided:
        name, material, weight, cycle = part
        db.add(RFQ(rfq_number=number, customer=customer, received_date=today - timedelta(days=2),
                   due_date=today + timedelta(days=2), owner_id=estimator.id, status="estimating",
                   synthetic=False, source_label="Provided sample · demo dates and rates"))
        db.flush()
        db.add(Part(rfq_id=db.query(RFQ).filter_by(rfq_number=number).one().id, part_name=name, material=material,
                    gross_weight_kg=weight, annual_volume=volume, cycle_time_min=cycle,
                    machine_rate_key="Turning cell" if hour_rate == 850 else "Forging machining" if hour_rate == 1450 else "Gear cutting",
                    scrap_pct=2.5, overhead_per_part=2.0, freight_per_part=1.0, packing_per_part=0.8,
                    margin_pct=18, synthetic=False, source_ref="Problem statement sample row"))

    rng = random.Random(261102)
    statuses = ["estimating"] * 7 + ["pending_approval"] * 4 + ["sent"] * 5 + ["won"] * 4 + ["lost"] * 4
    rng.shuffle(statuses)
    for i, status in enumerate(statuses, 1):
        rfq = RFQ(
            rfq_number=f"DEMO-RFQ-{i:03d}", customer=f"Demo Customer {((i - 1) % 8) + 1:02d}",
            received_date=today - timedelta(days=rng.randint(1, 24)),
            due_date=today + timedelta(days=rng.randint(-3, 12)), owner_id=estimator.id,
            status=status, loss_reason="Lead time did not meet requirement" if status == "lost" else None,
            synthetic=True, source_label="SYNTHETIC DEMO — NOT CUSTOMER DATA")
        db.add(rfq)
        db.flush()
        for part_idx in range(2):
            name, material, weight, cycle = PARTS[(i * 2 + part_idx) % len(PARTS)]
            volume = rng.choice([12000, 24000, 36000, 60000, 90000, 120000, 180000])
            machine_key = rng.choice(list(MACHINE_RATES.keys()))
            demo_part = Part(rfq_id=rfq.id, part_name=name, material=material,
                        gross_weight_kg=round(weight * rng.uniform(0.78, 1.22), 2), annual_volume=volume,
                        cycle_time_min=round(cycle * rng.uniform(0.8, 1.3), 1), machine_rate_key=machine_key,
                        scrap_pct=rng.choice([1.5, 2.0, 2.5, 3.0]), overhead_per_part=rng.choice([1.5, 2.0, 3.5]),
                        freight_per_part=rng.choice([0.6, 1.0, 1.8]), packing_per_part=rng.choice([0.5, 0.8, 1.2]),
                        margin_pct=rng.choice([12, 15, 18, 20]), synthetic=True,
                        source_ref=f"SYNTHETIC DEMO part {part_idx + 1}")
            if part_idx == 0 and i % 2 == 0:
                first_cycle = round(demo_part.cycle_time_min * 0.7, 1)
                second_cycle = round(demo_part.cycle_time_min - first_cycle, 1)
                if second_cycle > 0:
                    demo_part.cycle_time_min = first_cycle
                    demo_part.routing_operations.extend([
                        RoutingOperation(sequence_no=1, operation_name="Primary machining",
                                         machine_rate_key=machine_key, cycle_time_min=first_cycle),
                        RoutingOperation(sequence_no=2, operation_name="Finish grinding",
                                         machine_rate_key="Precision grinding", cycle_time_min=second_cycle),
                    ])
            db.add(demo_part)
        if status != "estimating":
            revision_status = {"pending_approval": "pending_approval", "sent": "sent", "won": "sent", "lost": "sent"}[status]
            parts = list(rfq.parts)
            # Relationship collection is populated from the just-added rows after a flush.
            db.flush()
            parts = db.query(Part).filter_by(rfq_id=rfq.id).all()
            volumes = [5000, 25000, 75000]
            breakdown, snapshots = [], []
            for part in parts:
                mr = material_rows[part.material]
                operations = [{"sequence_no": op.sequence_no, "operation_name": op.operation_name,
                    "machine_rate_key": op.machine_rate_key, "cycle_time_min": op.cycle_time_min,
                    "rate_amount": machine_rows[op.machine_rate_key].amount,
                    "rate_unit": machine_rows[op.machine_rate_key].unit,
                    "rate_id": machine_rows[op.machine_rate_key].id} for op in part.routing_operations]
                if not operations:
                    cr = machine_rows[part.machine_rate_key]
                    operations = [{"sequence_no": 1, "operation_name": "Primary operation",
                        "machine_rate_key": part.machine_rate_key, "cycle_time_min": part.cycle_time_min,
                        "rate_amount": cr.amount, "rate_unit": cr.unit, "rate_id": cr.id}]
                cr = machine_rows[operations[0]["machine_rate_key"]]
                scenarios = calculate_part({"gross_weight_kg": part.gross_weight_kg,
                    "cycle_time_min": part.cycle_time_min, "scrap_pct": part.scrap_pct,
                    "margin_pct": part.margin_pct, "overhead_per_part": part.overhead_per_part,
                    "freight_per_part": part.freight_per_part, "packing_per_part": part.packing_per_part},
                    {"amount": mr.amount}, {"amount": cr.amount}, volumes,
                    route_rates=[{"cycle_time_min": op["cycle_time_min"], "amount": op["rate_amount"]} for op in operations])
                breakdown.append({"part_id": part.id, "part_name": part.part_name, "material": part.material,
                                  "routing_operations": operations, "scenarios": scenarios, "margin_pct": part.margin_pct})
                snapshots.append({"part_id": part.id, "material_rate_id": mr.id, "material_rate": mr.amount,
                                  "material_rate_key": mr.rate_key, "material_unit": mr.unit,
                                  "machine_rate_id": cr.id, "machine_rate": cr.amount,
                                  "machine_rate_key": cr.rate_key, "machine_unit": cr.unit,
                                  "operation_rates": operations})
                if status in ("sent", "won", "lost"):
                    reference = scenarios[-1]
                    db.add(HistoricalQuote(batch_id="synthetic-seed-v1", source_row=i * 10 + part.id,
                        rfq_number=rfq.rfq_number, customer=rfq.customer, part_name=part.part_name,
                        material=part.material, gross_weight_kg=part.gross_weight_kg,
                        annual_volume=part.annual_volume, cycle_time_min=part.cycle_time_min,
                        routing_key=part.machine_rate_key,
                        quoted_unit_price=reference["unit_price"], quoted_annual_value=reference["annual_value"],
                        quoted_at=today - timedelta(days=rng.randint(2, 80)),
                        source_label="SYNTHETIC DEMO — NOT CUSTOMER DATA", synthetic=True))
            annual = sum(line["scenarios"][-1]["annual_value"] for line in breakdown)
            revision = QuoteRevision(rfq_id=rfq.id, revision_number=1, status=revision_status,
                                     scenarios_json=json.dumps(volumes), breakdown_json=json.dumps(breakdown),
                                     rate_snapshot_json=json.dumps(snapshots), annual_value=annual,
                                     formula_version="cost-v1", submitted_by=estimator.id,
                                     sent_at=(datetime.now(timezone.utc) - timedelta(days=rng.randint(1, 40))) if status in ("sent", "won", "lost") else None,
                                     approved_at=(datetime.now(timezone.utc) - timedelta(days=rng.randint(1, 50))) if status in ("sent", "won", "lost") else None)
            db.add(revision)
            db.flush()
            if status in ("sent", "won", "lost"):
                db.add(Approval(revision_id=revision.id, reviewer_id=sales.id, decision="approve",
                                reason="Synthetic demo approval"))
    db.commit()
