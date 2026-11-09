# ADR-007: Statutory Sales Governance, Quote Immutability, and GST Snapshots

## Status
Accepted (Inferred from codebase implementation: `backend/models.py`, `backend/main.py`, `migrations/versions/0004_gst_snapshot.py`)

## Context
Commercial quotations in tier-1 manufacturing represent legally binding contracts upon dispatch. To prevent fraud, unilateral price alterations, and audit failures, quotes must follow a formal lifecycle: draft calculation -> internal approval -> customer dispatch -> commercial outcome (won/lost). Furthermore, statutory governance mandates senior sign-off for quotes exceeding ₹25,00,000 (₹25 Lakhs) annual value.

## Problem
Allowing estimators to edit quotes after submission or allowing unapproved quotes to be exported as PDFs creates severe commercial liability. Additionally, global tax rate changes (such as GST percentage updates) must not alter the tax amounts on previously approved and issued quotes.

## Decision
1. **Quote Immutability (`quote_revisions` table):**
   - Every calculation produces a discrete `QuoteRevision` with an incremented `revision_number`.
   - The revision snapshots all formula inputs, line-item breakdowns (`breakdown_json`), effective rate snapshots (`rate_snapshot_json`), and the active GST rate (`gst_rate_percent`).
   - Saved revisions are immutable: modifying part inputs or rates does not alter past revisions.
2. **Four-Eyes Principle & State Machine:**
   - Estimators draft and submit revisions (`status: draft -> pending_approval`).
   - Sales Head reviews the revision and decides:
     - `approve`: records `approved_at`, updates RFQ status to `approved`.
     - `return`: requires a mandatory recorded reason (`Approval.reason`), updates RFQ status back to `estimating`.
3. **Statutory Approval Threshold:**
   - Evaluated before GST: $\sum V_{\text{annual}} > \text{₹25,00,000}$ at reference volume (highest scenario volume).
   - In the current build, all quotes pass through Sales review; quotes exceeding ₹25L are explicitly flagged in audit records (`threshold_flag=True`).
4. **Controlled PDF Export & Dispatch:**
   - Generating cost breakup PDFs (`/api/revisions/{id}/pdf`) is strictly restricted to revisions in `approved` or `sent` status.
   - After manual dispatch, Sales marks the quote `sent`.
   - Recording commercial outcome (`won` or `lost`) is permitted only after a quote has been marked `sent`. Marking an RFQ `lost` mandates recording a non-empty loss reason.

## Alternatives Considered
1. **Directly Editing the RFQ Record:** Rejected because it destroys revision history and makes historical comparison impossible.
2. **Allowing Estimator Self-Approval:** Rejected due to corporate separation of duties and financial governance standards.

## Advantages
- Comprehensive audit trail of every quote revision, rate snapshot, and sales decision.
- Zero risk of unapproved drafts being presented to customers as official quotes.
- Mandatory loss reason collection provides crucial market intelligence for win/loss analysis.

## Disadvantages
- Additional workflow step (Sales review) required even for minor adjustments.
- Increases database storage for JSON snapshots across dozens of revisions (minimal in practice).

## Consequences
Every commercial quote issued to a customer can be traced back to the exact user, timestamp, rate version, and sales approval.
