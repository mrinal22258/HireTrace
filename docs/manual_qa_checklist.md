# HireTrace Manual QA Verification Checklist

This document provides a systematic verification plan for the HireTrace web application, covering the Netflix-style candidate browsing grid, decluttered profile view, sample/demo data filtering, theme switching, and candidate deletion flows.

---

### 1. Candidate Grid Loading & Presentation
- [ ] **Initial Page Load**: Navigate to `http://localhost:8000/` or `#/candidates`.
- [ ] **Persistent Intake Tile**: Verify that the first tile in the grid is `+ New Candidate` styled distinctly with an intake affordance.
- [ ] **Candidate Card Tiles**: Each candidate displays:
  - Deterministic initials avatar (colorful background and contrasting text derived from candidate ID hash).
  - Candidate name and target role.
  - Quadrant badge (`[STRONG MATCH]`, `[REVIEW REQUIRED]`, `[WEAK MATCH]`, etc.).
  - Two mini inline meters (Role Fit and Evidence Consistency) with compact score numbers.
- [ ] **Hover & Focus**: Hovering over a card shows subtle elevation and scale effect. Cards are focusable via `Tab` and activatable via `Enter`.
- [ ] **Loading Skeletons**: On slow connection or reload, pulsating skeleton placeholder tiles appear before data is received.

---

### 2. Search & Filter Bar
- [ ] **Real-time Search**: Type in the candidate search box (`#candSearchInput`). Candidate cards instantly filter by name and role.
- [ ] **Quadrant Filter**: Select options from the quadrant dropdown (`#candQuadrantSelect`):
  - "Strong Match", "Review Required", "Insufficient Evidence", "Weak Match", "Fast Reject".
  - Only candidates in the chosen quadrant remain visible in the grid.
- [ ] **Quick Filter Buttons**:
  - **All**: Resets category filtering.
  - **Adversarial**: Filters candidates with discrepancies or adversarial tags.
  - **Strong**: Filters candidates with `STRONG MATCH`.
  - **Weak**: Filters candidates with `WEAK MATCH` or `LOW_FIT_FAST_REJECT`.
- [ ] **Count Badge**: Verify that the badge `#candGridCount` accurately reflects the number of visible candidates.

---

### 3. "Show Sample Data" Toggle (Workstream B)
- [ ] **Default State**: By default, "Show sample data" checkbox is **unchecked**.
  - Synthetic benchmark cases (`case_*`) are completely excluded from the candidate grid and count.
- [ ] **Toggle On**: Check "Show sample data".
  - Benchmark candidates appear in a separate section at the bottom titled: `🧪 Demo & Benchmark Cases (15)`.
  - Section is collapsed by default. Clicking the header expands the benchmark cards grid.
  - Benchmark cards render a distinct `DEMO` corner ribbon.
- [ ] **Persistence**: Reload the browser. Verify the toggle state persists via `localStorage['hiretrace_show_demo_data']`.
- [ ] **Tooltip**: Hover over the ⓘ icon next to "Show sample data" to verify the tooltip text: *"Synthetic test candidates used to validate the evaluation pipeline. Not real applicants."*

---

### 4. Client-Side Hash Routing & Deep Linking (Workstream C1)
- [ ] **Card Click Navigation**: Click any candidate card in the grid.
  - URL updates to `#/candidates/{candidate_id}` without full page reload.
  - Grid view hides and dedicated candidate profile view is displayed.
- [ ] **Back to Grid**: Click `← Back to Candidates Board` button.
  - URL updates to `#/candidates`.
  - Grid view reappears with previously applied search/filters intact.
- [ ] **Browser History**:
  - Navigate into a profile, click Back in the browser → returns to grid.
  - Click Forward in the browser → returns to the candidate profile.
- [ ] **Direct Reload / Deep Link**: Paste `http://localhost:8000/#/candidates/case_15_deceptive_centerpiece` directly into a new browser tab.
  - Page loads straight into the profile for Candidate 15.

---

### 5. Decluttered Candidate Profile Page (Workstream C2)
- [ ] **Sticky Hero Header**:
  - Displays large candidate initials avatar with deterministic palette.
  - Candidate name, target role, category tag, and quadrant pill.
  - Dynamic plain-English verdict sentence matching the quadrant (e.g. *"Strong fit — evidence holds up across all sources"* or *"Review required — CV claims aren't fully backed by the interview"*).
- [ ] **4-Stat Tiles Row**:
  - Role Fit score (blended LLM + Rubric).
  - Evidence Consistency score.
  - Unsupported Claims count.
  - Contradicted Claims count.
- [ ] **Accordion Sections**:
  - Score Transparency Formula (`#accTransp`)
  - Deterministic Rubric Breakdown (`#accRubric`)
  - Terminal Report & Executive Summary (`#accTerminal`)
  - Priority Interview Questions (`#accQuestions`)
  - Discrepancy & Verification Diffs (`#accDiscrepancies`)
  - Multi-Source Dossier Viewer (`#accDossier`)
  - Requisition Leaderboard (`#accLeaderboard`)
  - EEOC Compliance & Counterfactual Fairness Audit (`#accAudit`)
- [ ] **Accordion Persistence**:
  - Expand the "Priority Interview Questions" and "Discrepancy & Verification Diffs" accordions.
  - Reload the page. Verify both accordions remain open while others remain collapsed (`localStorage['hiretrace_open_accordions']`).

---

### 6. Candidate Deletion Flow (Workstream C2)
- [ ] **Trigger**: Click `🗑 Delete Candidate` in the profile navigation bar.
- [ ] **Confirmation Modal**:
  - Warning modal appears showing candidate name and ID.
  - Warning notes that database records, files, caches, and dossier signals will be purged.
- [ ] **Cancel**: Clicking "Cancel" closes modal without deleting.
- [ ] **Confirm Delete**: Click "Yes, Permanently Delete".
  - Backend `DELETE /api/candidate/{id}` is executed.
  - Candidate is purged from `cases` array and grid.
  - UI automatically routes back to `#/candidates` grid.

---

### 7. Theme Switching & Dark Mode (Workstream C3)
- [ ] **Toggle**: Click `🌙 Dark Mode` in the top header.
  - UI transitions smoothly into curated dark pinkish palette.
  - Button text changes to `☀️ Light Mode`.
- [ ] **Contrast Verification**:
  - Quadrant pills (`.badge-strong`, `.badge-review`, `.badge-weak`, `.badge-evaluating`) maintain clear, accessible text contrast against card backgrounds.
  - Text, borders, and meters remain legible throughout grid and profile.
- [ ] **Persistence**: Reload the page. Verify dark mode persists across reloads via `localStorage['hiretrace_theme']`.

---

### 8. Mobile Responsiveness (down to ~375px)
- [ ] **Viewport Resize**: Open browser DevTools, switch to responsive view at 375px width (e.g., iPhone SE).
- [ ] **Grid Layout**: Grid smoothly reflows to a single column. Cards do not overflow horizontally.
- [ ] **Toolbar**: Search, dropdown, filter pills, and demo toggle wrap cleanly without horizontal scrollbars.
- [ ] **Profile View**:
  - Hero header stacks avatar and details vertically without clipping.
  - 4-Stat tiles reflow into a 2x2 grid.
  - Accordion headers and contents fit comfortably within mobile bounds.
- [ ] **Motion Reduction**: Enable `prefers-reduced-motion: reduce` in OS/browser. Verify animations (progress fills, modals, transitions) degrade gracefully without jarring motions.
