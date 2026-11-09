# ADR-006: Multi-Operation Machine Routing and Effective-Dated Rate Masters

## Status
Accepted (Inferred from codebase implementation: `backend/models.py`, `backend/main.py`, `migrations/versions/0002_routing_operations.py`)

## Context
Industrial manufacturing of forged automotive parts rarely involves a single machine step. A typical process includes cutting/shearing, induction heating, closed-die forging, trimming/piercing, shot blasting, heat treatment (annealing/normalizing), and finish CNC machining or precision grinding. Furthermore, material raw costs and machine hourly rates fluctuate over time based on market indexes and labor contracts.

## Problem
A single cycle time and single machine rate per part oversimplifies industrial reality, resulting in inaccurate process costing. Additionally, modifying a global rate must never retroactively alter historical quotes or approved commercial commitments.

## Decision
1. **Multi-Operation Routing (`routing_operations` table):**
   - Model ordered routing operations per part with `sequence_no`, `operation_name`, `machine_rate_key`, and `cycle_time_min`.
   - Enforce database constraint `UniqueConstraint("part_id", "sequence_no")`.
   - Calculate total processing cost as the sum of all individual operation costs:
     $$C_{\text{proc}} = \sum_{i=1}^N \frac{\text{cycle\_time\_min}_i}{60} \times \text{rate}_i$$
   - Provide seamless backward compatibility: if no routing operations exist, default to a single primary operation with the part's base cycle time and machine rate key.
2. **Effective-Dated Rate Masters (`rate_versions` table):**
   - Store rates with `effective_from` (inclusive) and `effective_to` (inclusive or `NULL` for ongoing).
   - Enforce non-overlapping validity periods per `(rate_type, rate_key)`.
   - When adding a new rate, automatically close the preceding period to the day before the new start date (`new_start - 1 day`).
   - Query rates dynamically using `effective_from <= target_date AND (effective_to IS NULL OR effective_to >= target_date)`.

## Alternatives Considered
1. **Single Flat Machine Rate:** Rejected because it cannot accurately capture multi-stage manufacturing lines (e.g., turning cell at ₹850/hr vs. forging press at ₹1450/hr).
2. **Overwriting Existing Rates in Place:** Strictly rejected as it corrupts historical audit trails and alters past quote calculations.

## Advantages
- True-to-life modeling of multi-step industrial manufacturing operations.
- Historical temporal validity: quotes calculated in January reference January rates, even after July price escalations.
- Automated period maintenance avoids accidental rate gaps or overlaps.

## Disadvantages
- Requires complex validation when updating or inserting retroactive rates.
- UI must support dynamic row additions and sequencing for up to 12 routing steps.

## Consequences
Estimators can model up to 12 distinct operations per part, and quote calculations resolve exact machine rates based on the calculation date.
