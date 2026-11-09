# ADR-003: Hybrid Binary Storage (Local Uploads vs. Private Supabase Storage)

## Status
Accepted (Inferred from codebase implementation: `backend/main.py`)

## Context
RFQ packages contain proprietary technical drawings, customer specifications, CAD exports, and bill-of-materials workbooks. These binary files range up to 12 MB and must be retained and linked to the RFQ entity throughout its lifecycle.

## Problem
In local demo mode, developers lack cloud credentials and require local file persistence. In production, local filesystem storage fails across multi-container autoscaled clusters and violates enterprise data compliance if stored in non-redundant ephemeral container filesystems.

## Decision
1. Implement a hybrid storage abstraction in [`backend/main.py`](file:///backend/main.py) via `store_source_file` and `retrieve_source_file`.
2. When `SUPABASE_URL` and `SUPABASE_SECRET_KEY` are provided:
   - Ensure a private Supabase Storage bucket (`rfq-source-documents`) exists with `public=false` and file size limit of 12 MB.
   - Fail closed if the configured bucket is discovered to be public.
   - Upload and download file bytes via authenticated REST endpoints using server-only service credentials.
3. When Supabase credentials are not configured:
   - Persist files locally under the Git-ignored directory `instance/uploads/`.
   - Name files with cryptographic UUID hex strings + original extensions (`{uuid4().hex}.{ext}`).
4. Always persist source document metadata (file ID, original filename, byte size, media type, extraction method) in the relational `rfq_sources` table.

## Alternatives Considered
1. **Storing BLOBs directly in Database:** Rejected because large binary payloads bloat table sizes, slow down backups, and degrade DB buffer pool hit rates.
2. **AWS S3 / GCP Cloud Storage SDKs:** Viable, but Supabase was selected to align with the chosen managed PostgreSQL provider and unified project console.

## Advantages
- Allows offline local testing while providing seamless cloud object storage when credentials are set.
- Enforces private access: raw documents are never accessible via public unauthenticated URLs.
- Retains original source documents indefinitely, even when text or drawing OCR extraction fails.

## Disadvantages
- Local uploads in multi-worker environments are not shared without a distributed file system.
- Staged upload files from incomplete RFQ intake flows require periodic garbage collection.

## Consequences
Production deployments must provide `SUPABASE_URL` and `SUPABASE_SECRET_KEY` in private environment configuration and configure lifecycle retention policies on the storage bucket.
