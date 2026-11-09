# Technical Design Document — ForgeQuote

**GitHub project:** https://github.com/MoAftaab/isocodelabs  
**Live application:** Not deployed; see deployment.md  
**Status:** Review build  
**Scope:** Company A's Software Engineering Core Build

## 1. Product and workflow

ForgeQuote supports the estimator-to-Sales-Head flow: RFQ register, multi-part costing, effective-dated rates, approval, and a cost-breakup PDF. An estimator signs in, reviews or creates an RFQ, accepts source-linked intake suggestions, prices two or three volume scenarios, and submits an immutable revision. Sales approves or returns it with a reason. After dispatch, Sales records sent, won, or lost (with required loss reason). Approved revisions produce PDFs showing material, process, overhead, packing, freight, unit price, and a separately displayed GST amount.

Historical quote search and mapped Excel import support the core flow. AI extracts only source-supported RFQ values and ranks historical routing candidates. Fixed server-side formulas calculate all prices; AI cannot cost or approve.

## 2. Architecture

Responsive HTML/CSS/JavaScript calls a FastAPI service that serves both API and static assets. FastAPI applies authentication, role checks, CSRF validation, and audit logging; handles local intake parsing, AI calls, historical retrieval, costing, and quote state changes; and generates approved PDFs through ReportLab. SQLAlchemy and Alembic persist data in SQLite for local demo or PostgreSQL for deployment. Private Supabase Storage holds RFQ files when configured.

| Entity | Purpose |
|---|---|
| User | Named username, role, password hash, active flag |
| RFQ | Unique number, customer, receive/due dates, owner, status, loss reason |
| Part | RFQ part details and estimator cost inputs |
| RoutingOperation | Ordered operation, machine key, cycle time |
| RateVersion | Material/machine rate with effective interval and editor |
| QuoteRevision | Scenario inputs, cost breakdown, rate/GST snapshots, formula version |
| Approval | Sales decision and return reason |
| RFQSource | Private object reference, metadata, extraction state, uploader |
| HistoricalQuote | Imported quote, worksheet row, provenance, synthetic flag |
| AuditEvent | Actor, action, entity, timestamp, workflow detail |

## 3. Costing and rate behavior

The API validates positive weight/volumes, nonnegative rates and costs, scrap below 100%, margin below 100%, and two or three distinct positive whole-number volume scenarios. Costing uses Python Decimal with half-up currency rounding.

- Material cost/part = gross weight × effective material rate ÷ (1 − scrap fraction).
- Process cost/part = sum(operation cycle minutes × effective machine rate ÷ 60).
- Unit cost = material + process + per-part overhead + freight + packing.
- Unit quote = unit cost × (1 + markup fraction).
- Annual quote value = unit quote × annual volume.
- GST is calculated separately using GST_RATE_PERCENT and snapshotted in the revision. Approval threshold is evaluated before GST.

Each revision snapshots formulas, inputs, rate values and IDs, and GST percentage. Later rate or tax setting changes do not rewrite saved revisions. Rate periods may not overlap; a later open rate closes the prior period the day before it starts.

## 4. AI, intake, and uncertainty

The adapter supports OpenAI Chat Completions, OpenAI Responses, and Anthropic Messages. Review configuration selects AgentRouter with gpt-6.1-sol. Status distinguishes unverified, reachable, and unavailable. A live synthetic chat response was verified during implementation; recheck availability in the deployment environment.

Email/Excel text and selectable PDF text are parsed locally. Image-only drawings require Tesseract and language data on the host; OCR quality has not been validated on Company A drawings. Model extraction is restricted to listed RFQ fields. Each accepted suggestion must contain an exact source excerpt; unsupported fields are discarded. Estimators review or edit suggestions before RFQ creation. Excel part rows require selection. Routing suggestions are based on matching historical parts and display the source part/RFQ.

AI never calculates cost, chooses final routes, or approves. Invalid output and provider errors leave manual entry available and are shown as failures. Hosted customer/NDA data stays blocked until Company A verifies no-training/NDA terms and privately enables AI_NDA_APPROVED. Default AI context is synthetic-only. Source files use private Supabase Storage when configured; local demo files stay in ignored instance/uploads.

## 5. UI decisions

Main views: RFQ register, costing workspace, rate master, approvals, quote history. Detail/intake/import/account actions use focused dialogs. Costing puts part inputs and the volume comparison table first; restrained neutrals/green, aligned numeric columns, and explicit labels support dense estimator use. On narrow screens, work areas stack and tables scroll horizontally. Assistant answers render headings, lists, and readable tables, including compacted rows. Loading, empty, validation, AI-unavailable, and request-error states are explicit.

## 6. Security and operations

Passwords use PBKDF2-HMAC-SHA256 with per-password salts. Routes require sign-in; estimator and Sales permissions are checked server-side. State-changing requests require CSRF tokens. Source documents use a private Storage bucket and authenticated download when configured. .env, databases, uploads, and generated artifacts are ignored by Git.

Local sessions live in process memory and expire after 12 hours; a server restart signs users out. This is local review behavior only. A hosted multi-instance deployment needs shared durable sessions, secure cookies, TLS, backup/recovery, and named accounts. Demo credentials are for local review only.

## 7. Verification and known limits

Tests cover costing formulas/boundaries, roles and quote workflow, rate snapshots, routing updates, approval/PDF access, Excel mapping and provenance, corrupt extraction, a full synthetic 1,400-row import and search, history pagination, multi-worksheet selection, RFQ header authorization, and separate GST calculations. Migrations are versioned through Alembic. Test runs leave live Supabase Storage credentials unset.

The client workbook and drawings were not supplied; the actual 1,400-row import and OCR quality remain unvalidated. Each workbook worksheet is imported separately. Tesseract installation is host setup. GST defaults to 0 until Finance supplies an approved rate. Formula conventions and approval threshold basis require client confirmation. Import preview batches are local temporary files and expire if the host restarts. History is paginated; production archive performance has not been benchmarked. Email dispatch, ERP integration, supplier portal, CAD analysis, Plant Head, and MD roles/sign-off are outside the Core Build.

## 8. Assumptions register

Only the supplied brief is treated as Company A fact. These choices are assumptions requiring confirmation:

- **A-01 Scrap:** modeled as yield loss: gross material cost ÷ (1 − scrap).
- **A-02 Margin:** input means markup on cost, not gross margin on sales.
- **A-03 Allocation:** overhead, packing, and freight are per-part amounts; no volume discount or tooling amortization is modeled.
- **A-04 GST:** configurable setting defaults to 0. Finance must supply/approve the percentage before commercial use; zero is not a tax determination.
- **A-05 Approval value:** largest entered annual-volume scenario, sum across RFQ parts, before GST. All revisions go through Sales review in this build, including those below ₹25 lakh.
- **A-06 Ownership:** an estimator may edit only an RFQ they own; Sales may edit any RFQ header or reassign owner.
- **A-07 Bounds:** at most 100 parts/RFQ, 12 routing operations/part, and 12 MB/upload.
- **A-08 OCR:** first 20 scanned PDF pages only; English default; host must install Tesseract and language data.
- **A-09 Excel:** user maps one selected worksheet at a time to known fields; unknown workbook conventions require review.
- **A-10 Demo records:** the three rows in the brief are provided sample facts. Extra seeded rows are fictional and labeled synthetic.
- **A-11 Sessions:** local process-memory session, 12-hour expiry; durable store is needed for production.
- **A-12 AI privacy:** customer-data inference remains disabled until Company A verifies written no-training/NDA terms.
- **A-13 Database:** SQLite local fallback; each PostgreSQL deployment supplies its own private connection configuration.
- **A-14 History:** imported rows retain workbook/row provenance; no ERP linkage is inferred.

## 9. References

- Project: https://github.com/MoAftaab/isocodelabs
- Client brief: Company A / Chakan, Pune product brief supplied for this exercise.
