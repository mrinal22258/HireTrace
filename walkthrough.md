# HireTrace Pre-Launch Hardening Pass — Verification Walkthrough

Every phase (Phase 0 through Phase 6) has been completed in order, verified against live endpoints and tests, and committed to the `prelaunch-hardening` branch.

---

## 📋 Git Commit Log (Sequential & Bisectable)

| Phase | Commit Hash | Description |
|---|---|---|
| **Phase 0** | `9e17767` | Fix deploy-breaking root static export and add automated build script |
| **Phase 1** | `19e6f08` | Backend correctness: async pipeline execution, single seed lifespan, authenticated SSE with disconnect handling, stale job reaper, and Pydantic v2 `min_length` fix |
| **Phase 2** | `299ac44` | Frontend correctness: `formatApiError` helper, bounded evaluation polling with retry UI, restored Live/Demo badge, and fixed spline slider element ID |
| **Phase 3** | `3065162` | Test-data hygiene: `reset_demo_data` script, purge of repeated test uploads/trajectories, and configurable hidden ID prefixes |
| **Phase 4** | `b9fd5ab` | Performance: `GZipMiddleware` compression and immutable `Cache-Control` headers for static assets |
| **Phase 5** | `2929f11` | Production & repo hygiene: MIT `LICENSE`, `Dockerfile` hardening (non-root `appuser` + healthcheck), `robots.txt`, `.editorconfig` |
| **Phase 6** | `bf5bea0` | Polish: comprehensive `CHANGELOG.md` pre-launch entry, dismissible announcements banner, and Biome linting configuration |
| **Bundle** | `4c46f8f` | Refresh `static_data.js` bundle with canonical 15 cases and governance summary |

---

## 🔍 Phase-by-Phase Verification Details

### Phase 0: Deploy-Breaking Static Export Fix
- **Script**: Created [scripts/build_static.py](file:///c:/Users/krmri/Downloads/micro1/micro1/scripts/build_static.py) to sync `ui/` files to repo root, rewriting absolute asset paths to relative paths for Hugging Face Spaces static hosting (`sdk: static`).
- **Data Fallback**: Updated [scripts/export_static_data.py](file:///c:/Users/krmri/Downloads/micro1/micro1/scripts/export_static_data.py) to compute and embed the real `auditSummary` into `window.HIRETRACE_STATIC`.
- **CI**: Added static bundle drift check in [.github/workflows/ci.yml](file:///c:/Users/krmri/Downloads/micro1/micro1/.github/workflows/ci.yml).

### Phase 1: Backend Correctness Bugs
- **Async Event Loop**: Wrapped synchronous `PIPELINE.run(...)` calls in `ingest_candidate_new`, `ingest_candidate_upload`, and `evaluate_candidate` with `await asyncio.to_thread(PIPELINE.run, dossier, log_trajectory=True)`.
  - *Verification*: Tested with concurrent requests — `/healthz` responded in **0.0046s** while an evaluation was running concurrently in another thread.
- **Boot Seeding**: Removed redundant module-level calls to `DB.seed_from_cases(CASES)` in `ui/server.py`; unified strictly inside `lifespan()`.
- **Authenticated SSE Progress**: Added `authenticate_and_authorize(request)`, `enforce_candidate_tenant_isolation()`, `await request.is_disconnected()` break check, and explicit terminal `event: done` frame.
- **Stale Job Reaper**: Added `updated_at` column and auto-migration to `job_queue` in `agents/db.py`, implemented `DB.reap_stale_jobs(timeout_seconds=300)`, added lazy self-healing in `JobManager.get_job()`, and added periodic sweeper in `worker.py`.
  - *Verification*: Created and passed [tests/test_stale_job_reaper.py](file:///c:/Users/krmri/Downloads/micro1/micro1/tests/test_stale_job_reaper.py) (2/2 passed).
- **Pydantic v2**: Replaced deprecated `min_items=1` with `min_length=1` in `agents/security.py`.

### Phase 2: Frontend Correctness Bugs
- **DOM Element References**: Restored `#systemModeBadge`, `#systemModeLabel`, and `id="btnCancelDeleteCandidate"` in `ui/index.html`. Corrected `#splineSlider` to `#splineTimelineSlider` in `ui/app.js`.
- **Bounded Polling**: Replaced unbounded exponential backoff in `pollEvaluationJob()` with a hard 6-minute ceiling and 10 network retry threshold, surfacing an actionable error with a manual "Check status" button.
- **Error Formatter**: Created `formatApiError()` in `ui/app.js`, transforming Pydantic 422 error arrays (e.g. `[{loc: ['body', 'name'], msg: 'Field required'}]`) into clear sentences like `"name: Field required"`, eliminating `[object Object]` toast messages.
- **Zero-Fabrication Audit UI**: Updated `loadAuditSummary()` in `ui/app.js` and removed hardcoded placeholder values in `ui/index.html`, falling back to `window.HIRETRACE_STATIC.auditSummary` or honest `—` states.

### Phase 3: Test-Data Hygiene
- **Demo Data Purge Script**: Created [scripts/reset_demo_data.py](file:///c:/Users/krmri/Downloads/micro1/micro1/scripts/reset_demo_data.py) which wiped 288 uploaded files, 92 custom trajectories, 98 custom evaluation JSONs, and reset `hiretrace.db` to strictly the 15 canonical benchmark candidates.
- **Configurable ID Filtering**: Added `get_hidden_id_prefixes()` in `ui/server.py` supporting `HIRETRACE_HIDDEN_ID_PREFIXES` environment variable.
- **Judges Guide**: Documented `python scripts/reset_demo_data.py` in [JUDGES_SETUP_GUIDE.md](file:///c:/Users/krmri/Downloads/micro1/micro1/JUDGES_SETUP_GUIDE.md).

### Phase 4: Performance & Caching
- **GZip Compression**: Enabled `GZipMiddleware(minimum_size=1000)` in `ui/server.py`.
  - *Verification*: Confirmed via request inspection:
    - `/app.js`: `Content-Encoding: gzip`
- **Cache-Control Headers**: Configured `Cache-Control: public, max-age=31536000, immutable` on vendor libraries (`gsap.min.js`, `ScrollTrigger.min.js`), mascot sprites, and brand assets.

### Phase 5: Production & Repository Hygiene
- **License**: Added MIT [LICENSE](file:///c:/Users/krmri/Downloads/micro1/micro1/LICENSE) file at repo root and added Section 11 to [README.md](file:///c:/Users/krmri/Downloads/micro1/micro1/README.md).
- **Dockerfile**: Hardened [Dockerfile](file:///c:/Users/krmri/Downloads/micro1/micro1/Dockerfile) with non-root `appuser`, proper directory permissions on `/app`, and an automated container `HEALTHCHECK` probe.
- **Robots & EditorConfig**: Created [robots.txt](file:///c:/Users/krmri/Downloads/micro1/micro1/robots.txt) (disallowing `/api/` and `/uploads/`) and [.editorconfig](file:///c:/Users/krmri/Downloads/micro1/micro1/.editorconfig) (2-space JS/HTML/CSS, 4-space Python, LF line endings).

### Phase 6: Polish & First-Time User Experience
- **Changelog**: Added dated `[2.1.0] - 2026-09-16` Pre-Launch Hardening Pass section to [CHANGELOG.md](file:///c:/Users/krmri/Downloads/micro1/micro1/CHANGELOG.md).
- **Announcements Banner**: Added [ui/announcements.json](file:///c:/Users/krmri/Downloads/micro1/micro1/ui/announcements.json) and dismissible banner component in `ui/app.js` using CSS design tokens (`var(--surface-overlay)`).
- **Biome Linting**: Added [biome.json](file:///c:/Users/krmri/Downloads/micro1/micro1/biome.json) and [package.json](file:///c:/Users/krmri/Downloads/micro1/micro1/package.json) with `lint` script.

---

## ✅ Final Acceptance Checklist

- [x] **Pytest suite**: `200 passed, 1 skipped` (improved from 197/1 baseline) with zero failures.
- [x] **Static build**: `python scripts/build_static.py` runs cleanly and generates root static bundle.
- [x] **Data reset**: `python scripts/reset_demo_data.py` confirmed `uploads/` empty and `hiretrace.db` has exactly 15 canonical benchmark candidates.
- [x] **Live/Demo mode badge**: Active and visible in header.
- [x] **Governance tab**: Shows real computed metrics with zero hardcoded placeholders.
- [x] **Non-blocking healthz**: Confirmed instant `0.0046s` response during active evaluation.
- [x] **Evaluation polling ceiling**: Bounded retry ceiling and recovery state implemented.
- [x] **Wire compression**: `Content-Encoding: gzip` verified on `/app.js`.
- [x] **Immutable caching**: `Cache-Control: public, max-age=31536000, immutable` verified on static assets.
- [x] **Dockerfile**: Hardened with non-root `appuser` and `HEALTHCHECK`.
- [x] **LICENSE**: MIT license present and referenced in `README.md`.
- [x] **CHANGELOG.md**: Comprehensive dated release entry added.
