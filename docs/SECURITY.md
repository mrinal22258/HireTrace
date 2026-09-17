# HireTrace Security & Multi-Tenancy Architecture

This document details the security posture, multi-tenant isolation, access control, rate limiting, and data protection mechanisms implemented in **HireTrace**.

---

## 1. Authentication & API Key Scoping

HireTrace protects all `/api/*` endpoints with API Key-based authentication.

### Authentication Modes
1. **Header Authentication**:
   - `X-API-Key: <key>`
   - `Authorization: Bearer <key>`
2. **Environment Configuration**:
   - Single Key: `HIRETRACE_API_KEY="sk_live_abc123"` (maps to `default_tenant`)
   - Multi-Tenant Mapping: JSON dictionary via `HIRETRACE_API_KEYS`:
     ```json
     {
       "sk_acme_corp_live": "tenant_acme",
       "sk_globex_tech_live": "tenant_globex"
     }
     ```
   - Strict Mode: Set `HIRETRACE_REQUIRE_AUTH=1` in production. When set to `0` or unset, requests default gracefully to `tenant_id="default_tenant"` (or honor `X-Tenant-ID`) to allow frictionless local offline development and zero-dependency evaluation runs.

Unauthenticated requests under strict mode yield `HTTP 401 Unauthorized`.

---

## 2. Multi-Tenant Data Isolation

Candidate evaluation dossiers contain sensitive corporate and hiring data. HireTrace enforces row-level tenant boundaries:

1. **Schema Isolation**:
   - The `candidates` and `job_queue` database tables include a `tenant_id` index column.
   - All database reads (`get_candidate_full`, `list_candidates`, `get_evaluation`) filter on `tenant_id = :tenant_id`.
2. **Cross-Tenant Access Prevention**:
   - `enforce_candidate_tenant_isolation(candidate_id, tenant_id)` verifies ownership prior to evaluating or retrieving candidate dossiers.
   - If Tenant A attempts to access or trigger evaluation for a candidate owned by Tenant B, the API returns `HTTP 403 Forbidden`.
   - If the candidate does not exist, the API returns `HTTP 404 Not Found` without revealing whether the ID exists in another tenant's namespace.

---

## 3. Rate Limiting & Abuse Prevention

LLM inference pipelines are computationally heavy and vulnerable to denial-of-wallet / denial-of-service abuse. HireTrace implements in-memory sliding-window rate limiting:

- **Configurable Limits**:
  - `HIRETRACE_RATE_LIMIT_EVAL` (Default: `30` requests / minute per tenant or IP).
  - Tracked per tenant ID (or client IP for unauthenticated callers).
- **Behavior**:
  - Evaluated on `/api/candidate/new`, `/api/candidate/upload`, `/api/candidates/bulk/`, and `/api/evaluate/{id}`.
  - Exceeding the window limit results in `HTTP 429 Too Many Requests` with a `Retry-After` header.

---

## 4. Pydantic Request Validation

All ingestion endpoints replace legacy ad hoc regex checks with formal Pydantic schema validation:
- `CandidateCreateRequest`: Enforces typed fields, character bounds (e.g., `candidate_id` format matching `^[a-zA-Z0-9_\-\.]{1,128}$`), string length boundaries on text inputs, and rejects malformed inputs with `HTTP 422 Unprocessable Entity`.

---

## 5. Data Protection & At-Rest Encryption

For production deployments processing real applicant PII:

### At-Rest Encryption
1. **PostgreSQL Encryption**:
   - Utilize PostgreSQL Transparent Data Encryption (TDE) or cloud provider KMS (AWS RDS KMS, GCP Cloud SQL CMEK).
   - Use encrypted storage volumes (LUKS on Linux, AWS EBS encrypted volumes).
2. **File Uploads & Trajectories**:
   - Upload directories (`eval_cases/custom_uploads/` and `cache/trajectories/`) must reside on encrypted persistent volumes (e.g., EBS with KMS) or S3-compatible buckets with Server-Side Encryption (`SSE-KMS` or `SSE-S3`).

### PII Handling & Minimization
1. **Redaction**: Strip or hash candidate personally identifiable information (government IDs, SSNs, credit cards, dates of birth) prior to storing resumes in the database or passing them to the local embedding/LLM pipeline.
2. **Offline Inference Architecture**: Because HireTrace operates over local Ollama / vLLM instances, applicant data is never transmitted across third-party public API networks, satisfying strict GDPR, HIPAA, and SOC-2 data residency requirements.
