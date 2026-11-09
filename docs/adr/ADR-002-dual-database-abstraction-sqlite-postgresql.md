# ADR-002: Dual Database Abstraction (Local SQLite and Supabase PostgreSQL)

## Status
Accepted (Inferred from codebase implementation: `backend/database.py`, `alembic.ini`, `migrations/`)

## Context
Developers and evaluators need a frictionless zero-configuration local review environment that runs out-of-the-box without requiring live cloud infrastructure or external Docker containers. Simultaneously, enterprise deployment requires a multi-user, ACID-compliant relational database (PostgreSQL on Supabase) with automated migrations and secure TLS connections.

## Problem
Hardcoding PostgreSQL complicates quick local testing and CI/CD validation. Conversely, relying solely on SQLite limits production readiness due to table-level file locking and concurrency limitations.

## Decision
1. Implement a unified SQLAlchemy 2.0 ORM abstraction with dynamic dialect detection in [`backend/database.py`](file:///backend/database.py).
2. Default to local SQLite (`sqlite:///./instance/forgequote.db`) when `DATABASE_URL` is omitted.
3. Automatically normalize `postgres://` or `postgresql://` URIs to `postgresql+psycopg://` using modern `psycopg` (v3).
4. Auto-inject `sslmode=require` for Supabase hosts (`*.supabase.co`, `*.supabase.com`) to guarantee in-transit encryption.
5. Use Alembic for explicit schema versioning across both engines (`migrations/versions/0001` through `0004`).
6. Restrict automatic demo data seeding to local SQLite; require explicit `SEED_DEMO_DATA=true` for PostgreSQL environments.

## Alternatives Considered
1. **SQLite Only:** Rejected due to concurrency bottlenecks and lack of production multi-user scalability.
2. **PostgreSQL Only:** Rejected to preserve local review portability and autonomous evaluation without external credentials.
3. **Container-only (docker-compose):** Viable, but raises barrier to entry for reviewers testing on bare-metal Python 3.12 environments.

## Advantages
- Instant local development with zero external dependencies.
- Production-ready PostgreSQL connectivity with automatic TLS enforcement for Supabase.
- Uniform data models managed via Alembic migrations.

## Disadvantages
- Minor SQL dialect differences (e.g., date functions, case sensitivity in `ILIKE`, locking semantics) must be guarded against. SQLite emulates `ILIKE` via SQLAlchemy compile hooks.

## Consequences
All schema alterations must be scripted via Alembic migrations that maintain cross-compatibility between SQLite and PostgreSQL 15+.
