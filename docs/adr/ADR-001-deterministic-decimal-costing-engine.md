# ADR-001: Deterministic Python Decimal Costing Engine

## Status
Accepted (Inferred from codebase implementation: `backend/costing.py`)

## Context
In closed-die forging, machining, and automotive component manufacturing, quoting discrepancies of fractions of a paisa compound rapidly into millions of rupees across high-volume production batches (e.g., 180,000 units/year). Furthermore, statutory automotive audits, customer cost-breakdown validations (open-book costing), and financial governance prohibit floating-point non-determinism, rounding drift, or LLM-generated prices.

## Problem
Standard IEEE-754 binary floating-point arithmetic (native Python `float`) causes representation errors (such as `0.1 + 0.2 = 0.30000000000000004`), which lead to non-deterministic quote amounts and audit failure. Additionally, probabilistic AI/LLM models must never be permitted to calculate prices or alter cost models.

## Decision
Implement a purely deterministic, server-side costing engine strictly isolated in [`backend/costing.py`](file:///backend/costing.py):
1. Use Python's standard `decimal.Decimal` library for all monetary and physical calculations.
2. Explicitly quantize all currency outputs to two decimal places using `ROUND_HALF_UP` (`Decimal("0.01")`).
3. Model gross material yield loss formula: $C_{\text{mat}} = \frac{W_{\text{gross}} \times R_{\text{mat}}}{1 - S}$.
4. Sum process cost across ordered routing steps: $C_{\text{proc}} = \sum \frac{T_i}{60} \times R_{\text{machine}, i}$.
5. Strictly isolate AI from costing: AI models are barred from pricing calculations, and quote numbers are never accepted from external LLM responses.

## Alternatives Considered
1. **IEEE-754 Float Math with `round()`:** Rejected due to binary floating-point representation drift and platform-dependent rounding discrepancies.
2. **Database-level SQL Trigger / Computed Column:** Rejected because costing involves multi-scenario volume simulations (2 to 3 volume points) evaluated prior to committing revisions.
3. **LLM Cost Modeling:** Strictly rejected due to hallucination risk, lack of auditability, and legal non-compliance.

## Advantages
- Absolute arithmetic repeatability across platforms and database engines.
- Meets statutory audit requirements for tier-1 automotive component manufacturing.
- Strict boundary between assistive AI (intake/search) and financial calculation (costing).

## Disadvantages
- Minor performance overhead compared to raw C-level IEEE-754 hardware floats (negligible for batches under 100 parts).
- Conversions between JSON floats and Python `Decimal` require explicit sanitization in Pydantic models.

## Consequences
All new pricing features, tooling amortization additions, or discount curves must be implemented inside `backend/costing.py` using `Decimal` arithmetic and validated against `ROUND_HALF_UP` currency fixtures in `tests/test_costing.py`.
