# ADR-005: Stateful Session Management and Double-Submit CSRF Defense

## Status
Accepted (Inferred from codebase implementation: `backend/security.py`, `backend/main.py`)

## Context
Web applications processing commercial quoting and pricing revisions require robust protection against credential stuffing, session hijacking, Cross-Site Request Forgery (CSRF), and unauthorized state mutation.

## Problem
Stateless JWT tokens stored in browser `localStorage` are vulnerable to Cross-Site Scripting (XSS) exfiltration and lack instantaneous server-side revocation. Conversely, full-blown database session storage adds query overhead during review evaluation.

## Decision
1. Implement cryptographically secure session tokens generated via `secrets.token_urlsafe(32)` stored in an in-memory dictionary `SESSIONS`.
2. Deliver the session token via an `HttpOnly`, `SameSite=Strict` cookie (`fq_session`) with a 12-hour expiration (43,200 seconds).
3. Generate a distinct, cryptographically random CSRF token (`secrets.token_urlsafe(24)`) per session.
4. Require the CSRF token in the `X-CSRF-Token` HTTP header on all state-changing endpoints (`POST`, `PATCH`, `DELETE`).
5. Validate CSRF tokens using constant-time comparison (`hmac.compare_digest`) to prevent timing side-channel attacks.
6. Hash passwords with PBKDF2-HMAC-SHA256, 310,000 iterations, and unique 16-byte cryptographically random salts.

## Alternatives Considered
1. **Stateless JWTs in LocalStorage:** Rejected due to XSS theft vulnerability and inability to revoke compromised tokens immediately.
2. **Redis-backed Session Store:** Recognized as the target production recommendation, but omitted from the demo build to eliminate external daemon dependencies during local evaluation.

## Advantages
- Immunity to JavaScript token exfiltration via `HttpOnly` cookie isolation.
- Strong defense against CSRF attacks via header-based double-token verification.
- Instant session invalidation upon explicit logout.

## Disadvantages
- In-memory session storage does not persist across application server restarts.
- Multiple worker processes (e.g. `uvicorn --workers 4`) cannot share sessions without sticky sessions or an out-of-process store.

## Consequences
Production deployment must migrate `SESSIONS` from the in-memory Python dictionary to an out-of-process distributed cache (e.g., Redis or database-backed session table) prior to running multiple worker replicas.
