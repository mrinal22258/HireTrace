# HireTrace Full UX Hardening & Security Audit Findings
**Date:** 2026-09-13  
**Auditor:** Antigravity Engineering & Security Agent  
**Repository:** `micro1/micro1` (HireTrace)  
**Baseline Status:** `pytest -v` passing (177 tests passed, 2 skipped)

---

## Executive Summary

A comprehensive security, accessibility, UX resilience, and architecture audit was performed across the frontend single-page application (`ui/index.html`, 5,294 lines) and backend services (`agents/`, `ui/server.py`). While HireTrace maintains rigorous core defenses (strict CSP headers, constant-time API key verification, and basic zip-bomb protections), several systemic vulnerability patterns and UX gaps were identified. This document provides a complete enumeration and severity ranking before code remediation begins.

---

## 1A. Frontend Audit (`ui/index.html`)

### 1A.1 Inline Event-Handler Variable Interpolation (Injection Class)
- **Severity: CRITICAL**
- **Vulnerability Mechanism:**
  When browser HTML parsers process attributes (e.g. `onclick="..."`), HTML entity decoding (e.g. `&#39;` or `&quot;`) occurs **before** the JavaScript engine compiles the attribute script. As a result, wrapping user- or LLM-derived text in `escapeHtml()` escapes HTML quotes into entity references, but the browser translates them back into raw `'` or `"` characters in the JavaScript evaluation context.
  Any single quote / apostrophe (e.g. "What's your experience...", candidate name "O'Connor", or quote snippets) causes syntax errors or arbitrary code execution / XSS if an attacker controls the text.
- **Enumerated Instances:**
  1. **Line 4583**: `onclick="copySingleQuestion('${escapeHtml(q)}')"`  
     *Trigger:* Interview probe questions rendered in profile. Attack vector: adversarial interview question containing `'); alert(document.cookie); //` breaks string delimiter.
  2. **Line 4406**: `onclick="navigateTo('profile', '${escapeHtml(c.candidate_id)}')"`  
     *Trigger:* Click on candidate dot in 2D quadrant scatter plot.
  3. **Line 4407**: `onmouseenter="showQuadrantTooltip(event, '${escapeHtml(c.name)}', '${escapeHtml(c.target_role || '')}', ${x.toFixed(1)}, ${y.toFixed(1)}, '${escapeHtml(quad)}')"`  
     *Trigger:* Hover over quadrant dot. Candidate name or target role with an apostrophe (e.g., "Senior VP's Engineer") breaks JS syntax or executes code.
  4. **Line 4477**: `onclick="jumpToEvidence('${escapeHtml(srcA)}', '${escapeHtml(quoteA)}')"`  
     *Trigger:* Discrepancy card "Inspect in Dossier →" button for Source A. `quoteA` contains arbitrary CV/interview excerpts which frequently contain apostrophes.
  5. **Line 4485**: `onclick="jumpToEvidence('${escapeHtml(srcB)}', '${escapeHtml(quoteB)}')"`  
     *Trigger:* Discrepancy card "Inspect in Dossier →" button for Source B. `quoteB` contains arbitrary interview/assessment quotes.
  6. **Line 4762**: `onclick="navigateTo('profile', '${escapeHtml(c.candidate_id)}')"`  
     *Trigger:* Leaderboard table candidate name link.
  7. **Line 4772**: `onclick="navigateTo('profile', '${escapeHtml(c.candidate_id)}')"`  
     *Trigger:* Leaderboard table "Inspect →" button.
  8. **Line 3474**: `onclick="executeCmdPaletteItem(${idx})"` (Integer index, not injectable, but still inline handler pattern).
  9. **Line 3847**: `onclick="removeFilterPill(${idx})"` (Integer index, not injectable).

---

### 1A.2 InnerHTML Assignment Sites & Escaping Analysis
- **Severity: HIGH**
- **Total `innerHTML =` Sites:** 25
- **Detailed Site Analysis:**
  1. **Line 3454**: `container.innerHTML = '<div class="cmd-palette-empty">No results found for "${escapeHtml(query)}"</div>'`  
     *Escaping:* `escapeHtml(query)` applied. Safe.
  2. **Line 3459**: `container.innerHTML = items.map(it => ...)`  
     *Escaping:* `escapeHtml(it.title)`, `escapeHtml(it.sub)` applied; badges hardcoded. Safe.
  3. **Line 3699**: `roleSelect.innerHTML = '<option value="all">...' + roles.map(r => '<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>').join("")`  
     *Escaping:* `escapeHtml(r)` applied. Safe.
  4. **Line 3844**: `pillsBar.innerHTML = pills.map((p, idx) => ...)`  
     *Escaping:* `escapeHtml(p.label)` applied. Safe.
  5. **Line 3855**: `pillsBar.innerHTML = ''`  
     *Escaping:* Empty string. Safe.
  6. **Line 3982**: `grid.innerHTML = '<div class="empty-state">...'`  
     *Escaping:* Hardcoded SVG + markup. Safe.
  7. **Line 3991**: `grid.innerHTML = newTileHtml + realCandidates.map(c => renderCandidateCard(c, false)).join('')`  
     *Escaping:* Analyzed `renderCandidateCard`: all fields (`escapeHtml(c.name)`, `escapeHtml(c.target_role)`, `escapeHtml(initials)`, `escapeHtml(c.quadrant)`) are escaped. Safe.
  8. **Line 3999**: `demoCards.innerHTML = benchmarkCandidates.map(...)`  
     *Escaping:* Uses `renderCandidateCard`. Safe.
  9. **Line 4002**: `demoCards.innerHTML = ''`  
     *Escaping:* Empty string. Safe.
  10. **Line 4014**: `tbody.innerHTML = '<tr><td colspan="7">No candidates match current filters...</td></tr>'`  
      *Escaping:* Hardcoded markup. Safe.
  11. **Line 4018**: `tbody.innerHTML = realCandidates.map(c => ...)`  
      *Escaping:* `c.name` and `c.target_role` are passed through `escapeHtml()`. Numbers formatted with `.toFixed()`. Safe.
  12. **Line 4227**: `tagsContainer.innerHTML = tags.map(t => '...${escapeHtml(t)}...').join('')`  
      *Escaping:* `escapeHtml(t)` applied. Safe.
  13. **Line 4356**: `candExpl.innerHTML = 'Candidate <strong>${escapeHtml(name)}</strong> evaluated...'`  
      *Escaping:* `escapeHtml(name)` applied. Safe.
  14. **Line 4394**: `container.innerHTML = deduped.map(c => ...)`  
      *Escaping:* Dots in quadrant canvas. Inline handlers on dots contained injection bugs (see 1A.1).
  15. **Line 4418**: `tooltip.innerHTML = '...'`  
      *Escaping:* `escapeHtml(name)`, `escapeHtml(role)`, `escapeHtml(quad)` applied. Safe.
  16. **Line 4451**: `container.innerHTML = '...'`  
      *Escaping:* Hardcoded success card. Safe.
  17. **Line 4459**: `container.innerHTML = discrepancies.map((d, i) => ...)`  
      *Escaping:* Quotes and topics escaped with `escapeHtml()`, but inline `jumpToEvidence` buttons contained unescaped attribute execution vectors (see 1A.1).
  18. **Line 4554**: `container.innerHTML = '${before}<mark class="evidence-highlight-target">${matched}</mark>${after}'`  
      *Escaping:* In `highlightDossierExcerpt()`, `before`, `matched`, and `after` are passed through `escapeHtml()`. Safe.
  19. **Line 4573**: `container.innerHTML = '<div>No priority probe questions required...</div>'`  
      *Escaping:* Hardcoded string. Safe.
  20. **Line 4577**: `container.innerHTML = questions.map((q, i) => ...)`  
      *Escaping:* Question text escaped with `escapeHtml(q)`, but copy button contained inline `onclick="copySingleQuestion('${escapeHtml(q)}')"` injection vector.
  21. **Line 4611**: `grid.innerHTML = '...'`  
      *Escaping:* Rubric scores formatted with integer fallback `cats.xxx || 0`. Safe.
  22. **Line 4624**: `listEl.innerHTML = '<span>No specific signal rules matched.</span>'`  
      *Escaping:* Hardcoded string. Safe.
  23. **Line 4626**: `listEl.innerHTML = signals.map(s => '<div>✓ ${escapeHtml(s)}</div>').join('')`  
      *Escaping:* `escapeHtml(s)` applied. Safe.
  24. **Line 4747**: `tbody.innerHTML = '<tr><td colspan="7">No candidates for selected requisition.</td></tr>'`  
      *Escaping:* Hardcoded string. Safe.
  25. **Line 4751**: `tbody.innerHTML = list.map(c => ...)`  
      *Escaping:* Candidate table in leaderboard; names/roles escaped. Contains inline `onclick="navigateTo(...)"`.

- **Adversarial Injection Cross-Reference:**
  - `eval_cases/adv_02_hidden_html_comment_injection.json`: Contains hidden HTML comments and payload tags. Handled safely by `escapeHtml()` in text nodes.
  - `eval_cases/adv_03_interview_jailbreak.json`: Contains roleplay and quotation marks. In text nodes it is escaped; however, if emitted into question copy buttons or discrepancy quotes, the inline `onclick` handler was vulnerable.

---

### 1A.3 Alert and Confirm Invocations
- **Severity: MEDIUM**
- **Summary:** Total `alert(...)`: 4 calls. Total `confirm(...)`: 0 calls.
- **Enumeration & Context:**
  1. **Line 4852**: `alert("Failed to delete candidate: " + err.message);`  
     *Trigger:* Inside `executeDeleteCandidate()`. Preceded by user confirming deletion in `deleteCandidateModal`. A network error pops a blocking browser alert instead of an inline error banner inside the modal.
  2. **Line 4917**: `alert("Please provide a resume by dropping a file or pasting text.");`  
     *Trigger:* Inside `submitCandidateIntake()`. Preceded by clicking "Start Evaluation" on Step 4 when neither file nor text was uploaded on Step 2. Blocks the UI instead of showing inline validation under the file dropzone.
  3. **Line 5064**: `alert("Evaluation failed: " + err.message);`  
     *Trigger:* Inside `submitCandidateIntake()`. Preceded by submitting intake form when `/api/candidate/upload` network call fails.
  4. **Line 5096**: `alert("Evaluation failed: " + (job.error || "Unknown error"));`  
     *Trigger:* Inside `pollEvaluationJob()`. Preceded by async job returning `status: "failed"`.

---

### 1A.4 Polling Loops (`setInterval`)
- **Severity: HIGH**
- **Enumeration:**
  1. **Line 5076 (`pollEvaluationJob`)**:
     - *Interval:* Fixed 1000ms.
     - *Catch Behavior:* Completely empty `catch (e) {}`. Silent failure on network drop.
     - *Backoff:* None. Does not back off on repeated HTTP errors or server disconnects.
     - *Timeout:* None. If the job gets stuck or backend dies, it polls indefinitely.
     - *Cancel Control:* No cancel button in the stepper modal.
  2. **Line 5150 (`pollBulkBatch`)**:
     - *Interval:* Fixed 1000ms.
     - *Catch Behavior:* Completely empty `catch (e) {}`.
     - *Backoff:* None.
     - *Timeout:* None.
     - *Cancel Control:* No cancel control on bulk progress card.

---

### 1A.5 CSS Breakpoints & Mobile Responsiveness
- **Severity: MEDIUM**
- **Existing `@media` Breakpoints:**
  1. Line 204: `@media (prefers-reduced-motion: reduce)`
  2. Line 2096: `@media (max-width: 900px)`
  3. Line 2102: `@media (max-width: 640px)`
- **High-Traffic Views Lacking Rules Below 768px / 640px / 375px:**
  1. **Candidate Table / Grid:** Below 640px, the table overflows horizontally without card transformation.
  2. **Intake Wizard Modal:** `.modal-dialog` is reset to `max-height: 100vh; border-radius: 0;` but inner dropzones, 4-step wizard header, and action buttons crush on 375px screens.
  3. **Quadrant Scatter (`#quadrantCanvas`):** Fixed aspect ratio / absolute positioning overflows container on small screens.
  4. **Leaderboard Table:** Table headers and multiple metric columns crush together without card view or responsive scroll wrapper.

---

### 1A.6 Keyboard, Focus & Modal Accessibility
- **Severity: HIGH**
- **Modals Checked:**
  1. `applicantModal` (Intake Wizard)
  2. `deleteCandidateModal` (Deletion Confirmation)
  3. `commandPaletteModal` (Command Palette)
- **Deficiencies:**
  - **Focus Trap:** None of the 3 modals trap Tab focus. Users can Tab out of the modal into backdrop page elements.
  - **Focus Restoration:** Closing a modal does not restore focus to the button that opened it.
  - **ARIA Roles:** `applicantModal` and `deleteCandidateModal` lack `role="dialog"`, `aria-modal="true"`, and `aria-labelledby`.
  - **Escape Key:** Global listener on Escape closes modals, but does not return focus.

---

## 1B. Backend Audit

### 1B.1 Bulk Ingestion & Upload Security
- **Severity: HIGH**
- **Wiring Verification:**
  - `agents/zip_safety.py` defines `assert_zip_entry_is_safe` (25MB per entry cap, 200MB total uncompressed cap, 100x compression ratio cap).
  - `agents/bulk_ingestion.py` invokes `assert_zip_entry_is_safe` during `process_archive`.
  - **Gap in Folder Upload (`process_file_tree`):** In `handleBulkFolderSelected`, directory files are sent as multi-part form data and routed directly to `process_file_tree`. Unlike `process_archive`, `process_file_tree` lacks total file count checks (e.g. max 500 files), per-file uncompressed size limits (25MB), and total payload byte limits (200MB).
  - **Gap in DOCX Parser (`agents/document_parser.py`):** `_extract_docx` inspects only `word/document.xml` before decompression. It does not iterate over all entries in the DOCX archive, allowing a malicious DOCX with inflated auxiliary files (e.g. `word/header1.xml`) to bypass the check.
  - **Path-Traversal Guards:** Candidate deletion strictly checks `ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,128}$")`. However, in `process_file_tree`, `path_key` and subfolder names must be rigorously validated against directory traversal (`../`).

---

### 1B.2 Dev Mode Production Bind Guard
- **Severity: CRITICAL**
- **Finding:**
  In `agents/security.py`, `is_auth_required()` returns `False` whenever `HIRETRACE_DEV_MODE=1` is set.
  `validate_security_configuration()` immediately exits when `is_auth_required()` is `False`.
  If a deploy script or Docker container sets `HIRETRACE_DEV_MODE=1` while binding to `0.0.0.0`, the application will start in production with all authentication disabled.
- **Remediation Requirement:**
  On startup, if `HIRETRACE_DEV_MODE=1` or auth is disabled while the server is bound to a non-loopback host (e.g. `0.0.0.0`, or public IP in `HOST`/`PORT`), the system must log a loud warning and refuse to start unless an explicit override `HIRETRACE_I_UNDERSTAND_DEV_MODE_IS_INSECURE=1` is present.

---

### 1B.3 CSP & Security Headers Middleware
- **Severity: LOW (Verified Compliant with Recommendations)**
- **Finding:**
  In `ui/server.py`, `@app.middleware("http")` wraps `call_next(request)` and sets `Content-Security-Policy`, `Referrer-Policy`, `X-Frame-Options`, and `X-Content-Type-Options`.
  This middleware executes for standard API routes, static file endpoints (`/`, `/static_data.js`), and `StreamingResponse` SSE endpoints (`/api/stream/{candidate_id}`).

---

### 1B.4 Rate Limiting Coverage
- **Severity: MEDIUM**
- **Finding:**
  Rate limiting is applied to:
  - `POST /api/candidate/new`
  - `POST /api/candidate/upload`
  - `POST /api/candidates/bulk`
  - `POST /api/candidate/{candidate_id}/evaluate`
  All high-cost LLM evaluation and file parsing endpoints are covered.

---

## Severity Checklist & Action Plan

| ID | Finding | Location | Severity | Phase |
|---|---|---|---|---|
| **SEC-01** | Inline handler template literal injection | `ui/index.html` (lines 4406, 4407, 4477, 4485, 4583, 4762, 4772) | **CRITICAL** | Phase 3 |
| **SEC-02** | Dev-mode public bind refusal guard | `agents/security.py`, `ui/server.py` | **CRITICAL** | Phase 3 |
| **SEC-03** | Bulk folder upload resource limits & path traversal | `agents/bulk_ingestion.py` | **HIGH** | Phase 3 |
| **SEC-04** | DOCX zip-bomb check across all archive entries | `agents/document_parser.py` | **HIGH** | Phase 3 |
| **UX-01** | Unhandled polling failures, infinite polling, lack of backoff/cancel | `ui/index.html` (`pollEvaluationJob`, `pollBulkBatch`) | **HIGH** | Phase 2 |
| **A11Y-01** | Missing focus trap, ARIA dialog roles, focus restoration | `ui/index.html` (`applicantModal`, `deleteCandidateModal`) | **HIGH** | Phase 2 |
| **UX-02** | Blocking `alert()` calls on errors and validation | `ui/index.html` (4 sites) | **MEDIUM** | Phase 2 |
| **UX-03** | Missing mobile responsive rules below 640px/375px | `ui/index.html` (grid, wizard, quadrant, table) | **MEDIUM** | Phase 2 |
| **UX-04** | Button loading states, optimistic UI, completion animation | `ui/index.html` | **LOW** | Phase 2 |
| **SEC-05** | Automated CI security regression test | `tests/test_ui_security_scan.py` | **LOW** | Phase 3 |
