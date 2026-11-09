# ForgeQuote deployment guide

## Live deployment and reviewer access

| Component | Provider | Live URL | Verified status |
| --- | --- | --- | --- |
| Frontend application | Vercel | <https://frontend-seven-tau-20.vercel.app> | HTTP 200; app served and API proxy responds. |
| Backend and API | Render | <https://forgequote-api-aftaab.onrender.com> | HTTP 200. |
| API health | Render | <https://forgequote-api-aftaab.onrender.com/api/health> | HTTP 200; PostgreSQL and Supabase Storage connected. AI unavailable. |
| Interactive API docs | Swagger UI | <https://forgequote-api-aftaab.onrender.com/docs> | HTTP 200. |

### Verified demo logins

Both accounts were seeded in the Supabase-backed application and verified end-to-end through both the direct Render API and the Vercel frontend proxy. Login, authenticated session lookup, and logout succeeded for both roles.

| Role | Username | Password |
| --- | --- | --- |
| Estimator | `estimator@demo.local` | `estimate-demo-2026` |
| Sales Head | `sales@demo.local` | `approve-demo-2026` |

These credentials are intentionally published for reviewer access to the synthetic demo workspace. They are not production credentials. AI inference currently reports unavailable; configure an approved AI key and verify the provider before claiming live AI functionality.

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

The current public review deployment is listed at the top of this guide. For a new hosted deployment, use a Python 3.12 host with TLS, set required variables in the host's private configuration panel, apply Alembic migrations, bootstrap named users, configure a private Supabase Storage bucket, and verify health, sign-in, source file access, costing, approval, and PDF download. Use a shared session store and secure cookie settings before running multiple processes.

## Render API + Vercel frontend

The deployment configuration is split intentionally: Render runs the Dockerized FastAPI service (`render.yaml`, `Dockerfile`), while Vercel publishes `frontend/` and proxies `/api/*` and `/static/*` to that service. The proxy preserves the browser's same-origin cookie and CSRF flow; the browser does not need direct cross-origin API access.

1. Rotate any database or Supabase secret that was previously pasted into chat before using it on a hosted service. Do not commit credentials.
2. Authenticate the CLIs with `render login` and `vercel login`. Validate the Render Blueprint with `render blueprints validate ./render.yaml`.
3. Create a Render Blueprint from `MoAftaab/isocodelabs` on branch `main`, using the checked-in `render.yaml`. Choose the free preview plan; it sleeps when idle and is not suitable for production.
4. At Blueprint creation, provide the `sync: false` values in Render's private environment form: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, the two bootstrap usernames, and two unique passwords of at least 12 characters. Keep the AI key unset until the client has approved hosted inference terms. `SEED_DEMO_DATA=true` seeds fictional sample records; hosted account names/passwords are read from the private bootstrap variables rather than the local demo credentials.
5. Wait for `/api/health` to report PostgreSQL, AI status, and Supabase Storage as expected. Copy the actual Render `onrender.com` URL from the service dashboard; Render may add a unique suffix to the service slug.
6. Update both external rewrite destinations in `frontend/vercel.json` to use that exact Render origin. Run `vercel link` from the `frontend/` directory to create/select the Vercel project with the frontend as its root, then deploy with `vercel --prod` from that directory.
7. Verify the Vercel root page, login/logout, API health through the Vercel origin, RFQ creation, costing, Sales Head approval, and PDF download. Keep `COOKIE_SECURE=true` on Render. Do not configure CORS for this same-origin proxy deployment.

The Render free service has no persistent local disk and may restart or sleep. RFQ source files are kept in Supabase Storage when configured; import previews remain temporary and sessions are in-memory. This is a review deployment, not a production availability or durability guarantee. Vercel uses no secret environment variables for the static frontend.

## Test and seed

Run python -m pytest -q from the repository root. Tests should run with Supabase Storage credentials unset so fixtures cannot upload to the live bucket. For local SQLite, synthetic demo records seed automatically. For PostgreSQL, explicitly set SEED_DEMO_DATA=true only when intentionally loading fictional demo records; leave it false for customer environments.

## Known setup limits

The client's actual historic workbook and scanned drawing samples were not included, so column mapping and OCR require client sample validation. Import each worksheet separately. Install Tesseract and needed language packs on the host before relying on scanned-drawing OCR. Configure a client-approved GST rate before using generated PDFs commercially. Email dispatch and ERP integration are not configured.
