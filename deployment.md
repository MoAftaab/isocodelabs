# ForgeQuote deployment guide

## Local run

1. Install Python 3.12 or newer.
2. Open a terminal in the repository root.
3. Create and activate a virtual environment.
4. Install dependencies with: python -m pip install -r requirements.txt
5. Copy .env.example to .env and keep .env private. Defaults use SQLite and synthetic demo data.
6. Apply the database schema with: python -m alembic upgrade head
7. Start the service with: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
8. Open http://127.0.0.1:8000.

The local demo creates sample accounts and clearly marked synthetic rows on first start. Do not deploy seeded passwords to a shared environment.

## Demo sign-in

- Estimator: estimator@demo.local / estimate-demo
- Estimator: estimator2@demo.local / estimate2-demo
- Sales Head: sales@demo.local / approve-demo

These accounts are for local review only. A hosted review deployment must use named accounts created with python -m backend.bootstrap and private bootstrap credentials.

## PostgreSQL / Supabase

Set DATABASE_URL in the private environment to the deployment's PostgreSQL connection string and require TLS for hosted Supabase connections. Apply migrations with python -m alembic upgrade head. The current schema head is 0004_gst_snapshot. Do not commit the database URL or any password.

To store RFQ source files in a private Supabase Storage bucket, configure the project URL and a server-only secret key. The application creates/uses the configured private bucket and serves files only to authenticated users. Without these settings the local demo writes files to ignored instance/uploads.

## Environment variable names

Set only variables required for the chosen deployment. Values are intentionally omitted.

- DATABASE_URL
- APP_ENV
- SESSION_SECRET
- COOKIE_SECURE
- SUPABASE_URL
- SUPABASE_SECRET_KEY
- SUPABASE_STORAGE_BUCKET
- GST_RATE_PERCENT
- AI_BASE_URL
- AI_PROTOCOL
- AI_MODEL
- AI_API_KEY
- AI_NDA_APPROVED
- AI_ORIGINATOR
- AI_USER_AGENT
- TESSERACT_CMD
- OCR_LANGUAGE
- UPLOAD_DIR
- BOOTSTRAP_ESTIMATOR_USERNAME
- BOOTSTRAP_ESTIMATOR_PASSWORD
- BOOTSTRAP_SALES_USERNAME
- BOOTSTRAP_SALES_PASSWORD
- SEED_DEMO_DATA

GST defaults to zero until the client supplies an approved rate. Keep AI_NDA_APPROVED false until the client confirms hosted inference terms. Store AI and database credentials only in private environment configuration.

## Hosted review deployment

No live application URL is currently provided. Deploy the FastAPI application to a Python 3.12 host with TLS, set required variables in the host's private configuration panel, apply Alembic migrations, bootstrap named users, configure a private Supabase Storage bucket, and verify health, sign-in, source file access, costing, approval, and PDF download. Use a shared session store and secure cookie settings before running multiple processes. Do not expose local demo credentials in a shared deployment.

## Test and seed

Run python -m pytest -q from the repository root. Tests should run with Supabase Storage credentials unset so fixtures cannot upload to the live bucket. For local SQLite, synthetic demo records seed automatically. For PostgreSQL, explicitly set SEED_DEMO_DATA=true only when intentionally loading fictional demo records; leave it false for customer environments.

## Known setup limits

The client's actual historic workbook and scanned drawing samples were not included, so column mapping and OCR require client sample validation. Import each worksheet separately. Install Tesseract and needed language packs on the host before relying on scanned-drawing OCR. Configure a client-approved GST rate before using generated PDFs commercially. Email dispatch and ERP integration are not configured.
