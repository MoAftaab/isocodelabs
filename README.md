# ForgeQuote

An RFQ costing and quotation workspace prototype based on the supplied brief. The responsive frontend is served by FastAPI. It includes PostgreSQL/Supabase support, deterministic costing, dated rates, approvals, PDF output, historical search/import, and an optional OpenAI-compatible AI gateway adapter.

## Local demo

Requires Python 3.12 or later.

1. Create and activate a virtual environment.
2. Install dependencies: pip install -r requirements.txt
3. Copy .env.example to .env.
4. Start the app: uvicorn backend.main:app --reload
5. Open http://127.0.0.1:8000.

Local SQLite seeds 3 provided RFQs and 24 clearly marked synthetic RFQs (about 48 parts), plus synthetic rate, approval, outcome, and history examples. Synthetic rows are fictional and never represent Company A history or actual customer quotes.

Demo accounts:

- Estimator: estimator@demo.local / estimate-demo
- Estimator: estimator2@demo.local / estimate2-demo
- Sales Head: sales@demo.local / approve-demo

These fixed credentials are for the local demo only. Do not use seeded accounts in a shared deployment.

## Supabase PostgreSQL

The backend reads DATABASE_URL from the environment. No live connection string or database password is in this repository. The credential previously pasted into chat should be rotated before connecting. Put the replacement in a private .env file or hosting secret store; .env is Git-ignored. URL-encode reserved characters in the password and require TLS (for example, sslmode=require).

Set DATABASE_URL to the rotated Supabase PostgreSQL URI, then run alembic upgrade head. Demo data is seeded automatically only for local SQLite. PostgreSQL seeding requires SEED_DEMO_DATA=true; leave it false for the shared database unless you explicitly want fictional rows there.

Create named Supabase users by setting BOOTSTRAP_ESTIMATOR_USERNAME, BOOTSTRAP_ESTIMATOR_PASSWORD, BOOTSTRAP_SALES_USERNAME, and BOOTSTRAP_SALES_PASSWORD privately, with unique passwords of at least 12 characters, then run python -m backend.bootstrap. The script never prints passwords.

## AI assistant

The adapter supports OpenAI Chat Completions and Anthropic Messages APIs. The current local demo uses AgentRouter's OpenAI-compatible `/v1` endpoint and the configured model. Add the provider-issued `AI_API_KEY` to a private `.env`; do not put it in source, `.env.example`, or Git. The app reports the AI as unverified until a live response succeeds, and unavailable after a failed response.

The provider's published privacy policy says prompt content is forwarded to the upstream model provider. The public materials reviewed did not establish a no-training commitment. AI_NDA_APPROVED therefore defaults to false: chat uses only synthetic records, and customer RFQ data stays out of hosted inference. The intake dialog permits model processing only when the user confirms that the uploaded file contains synthetic demo data, unless NDA/no-training terms have been verified and AI_NDA_APPROVED is explicitly enabled.

Without a key, the assistant reports unavailable. Local pattern extraction remains labeled non-AI; it never claims a model ran. Text-based PDFs, XLSX, emails, and text files can be parsed. Scanned PDFs and PNG/JPEG/TIFF/BMP drawings use local Tesseract OCR; install the Tesseract executable and set `TESSERACT_CMD` privately if it is not on PATH. OCR is limited to the first 20 pages of scanned PDFs and defaults to English (`OCR_LANGUAGE=eng`). No drawing image is sent to the AI gateway unless the user explicitly approves synthetic-only intake or NDA/no-training terms have been verified and enabled.

## Costing and approval flow

The fixed formula is in backend/costing.py. Demo math adjusts gross material by scrap, calculates machine cost from cycle minutes and hourly rate, adds per-part overhead/packing/freight, then applies markup. Finance must confirm these assumptions before commercial use. GST is configured with GST_RATE_PERCENT, defaults to zero, and is shown separately and snapshotted into each quote.

The estimator calculates a quote and submits a revision. Rates and values are snapshotted. The Sales Head approves or returns it with a reason. The Sales Head downloads the approved PDF and marks the quote sent after manual dispatch. The >₹25 lakh annual-value approval rule is checked before GST; every revision goes through Sales review in this demo.

RFQ intake supports multiple parts in one RFQ. XLSX rows with recognized part/material/weight/volume/cycle/routing headers appear as unaccepted suggestions; the estimator chooses which rows to add and completes missing values. The original upload is saved before extraction and attached to the RFQ on creation, even when extraction fails. Attached files can be downloaded from RFQ details. When `SUPABASE_URL` and the server-only `SUPABASE_SECRET_KEY` are configured, the app creates/uses a private `rfq-source-documents` bucket and stores file bytes there. Otherwise, it clearly reports and uses local `instance/uploads` storage for local demo use.

## Security and known limits

- Keep .env, real customer data, drawings, and production records out of Git.
- Without Supabase Storage credentials, source documents and staged uploads are stored under ignored `instance/uploads`. With credentials, files are stored in the private Supabase bucket and metadata stays in PostgreSQL. Production deployments should use the bucket, verify access/retention policies, and clean up abandoned staged uploads.
- Sessions are in-memory; a server restart signs out users. Production should use a shared session store.
- Supabase Storage uses a private bucket when its URL and server-only secret are configured; production still needs a retention policy and operational review.
- PDF parsing extracts text locally; scanned drawings require a host-installed Tesseract executable and approved OCR samples.
- Excel import supports worksheet selection and column mapping; the actual client workbook has not been supplied and needs validation.
- History search is paginated; import-preview batches are temporary local files and do not survive a host restart.
- Synthetic rates, dates, outcomes, and approvals are demo-only.
- Do not use demo pricing for customer quotes until formulas, rate masters, GST, and terms are approved.
