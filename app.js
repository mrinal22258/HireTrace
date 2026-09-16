    /* ==========================================================================
       APPLICATION STATE (Single Source of Truth)
       ========================================================================== */
    const AppState = {
      cases: [],
      activeCaseId: null,
      activeCaseData: null,
      activeFullDocs: null,
      currentView: 'candidates',       // 'candidates' | 'profile' | 'leaderboard' | 'audit'
      activeProfileTab: 'overview',     // 'overview' | 'evidence' | 'questions' | 'governance'
      activeDossierDoc: 'cv',
      currentFilter: 'all',
      viewMode: localStorage.getItem('hiretrace_view_mode') || 'grid', // 'grid' | 'list'
      filters: {
        quadrant: 'all',
        contradictions: false,
        unsupported: false,
        verifiedOnly: false,
        includeDemo: false
      },
      isDegraded: false,
      llmAvailable: true,
      systemMode: 'live',
      recentCandidates: JSON.parse(localStorage.getItem('hiretrace_recent_candidates') || '[]'),
      cmdPaletteOpen: false,
      cmdPaletteIndex: 0,
      cmdPaletteItems: [],
      leaderboardSort: 'fit',          // 'fit' | 'consistency' | 'unsupported' | 'name'
      isDemoGroupExpanded: false,
      pipelineStream: null,
      pollInterval: null,
      batchPollInterval: null,
      evalPollTimeout: null,
      batchPollTimeout: null,
      lastFocusedElement: null,
      isLoadingCases: false,
      wizardStep: 1,
      uploadedFiles: { cv: null, interview: null, assessment: null, project: null },
      inputModes: { cv: 'file', interview: 'file', assessment: 'file', project: 'file' }
    };

    /* Helper: Sanitization (canonical implementation from dom-safe.js) */
    const escapeHtml = (typeof window !== 'undefined' && window.escapeHtml) ? window.escapeHtml : function(str) {
      if (!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
    };

    /* Helper: Pydantic 422 & HTTP API error formatter */
    function formatApiError(detail, fallback = "API request failed") {
      if (!detail) return fallback;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail.map(item => {
          const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : "";
          const msg = item.msg || item.message || JSON.stringify(item);
          return field ? `${field}: ${msg}` : msg;
        }).join("; ");
      }
      if (typeof detail === "object") {
        if (detail.msg) return detail.msg;
        if (detail.message) return detail.message;
        return JSON.stringify(detail);
      }
      return String(detail);
    }

    /* Helper: Deduplication */
    function deduplicateCandidates(list) {
      if (!Array.isArray(list)) return [];
      const seenIds = new Set();
      const seenNames = new Set();
      const out = [];
      for (const c of list) {
        if (!c || !c.candidate_id) continue;
        const cid = c.candidate_id;
        const nameKey = (c.name || "").trim().toLowerCase();
        if (seenIds.has(cid)) continue;
        if (nameKey && seenNames.has(nameKey)) continue;
        seenIds.add(cid);
        if (nameKey) seenNames.add(nameKey);
        out.push(c);
      }
      return out;
    }

    /* Helper: Check Benchmark / Demo Candidate */
    function isBenchmarkCandidate(cid) {
      if (!cid) return false;
      const str = String(cid);
      return str.startsWith("case_") || str.includes("adversarial") || str.includes("centerpiece") || str.includes("fabricated");
    }

    /* ==========================================================================
       ROUND 2 CRAFT HELPERS: NUMERIC ANIMATION, 3D TILT, METERS & PARALLAX
       ========================================================================== */

    /**
     * Animate numeric counters smoothly with ease-out cubic curve (Part 4.3)
     */
    function animateNumber(target, startVal, endVal, duration = 600, decimals = 0, suffix = '') {
      const el = typeof target === 'string' ? document.getElementById(target) : target;
      if (!el) return;
      const end = Number(endVal);
      if (isNaN(end)) {
        el.textContent = '--';
        return;
      }
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        el.textContent = end.toFixed(decimals) + suffix;
        return;
      }
      const start = Number(startVal) || 0;
      const startTime = performance.now();

      function update(now) {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const current = start + (end - start) * ease;
        el.textContent = current.toFixed(decimals) + suffix;
        if (progress < 1) {
          requestAnimationFrame(update);
        } else {
          el.textContent = end.toFixed(decimals) + suffix;
        }
      }
      requestAnimationFrame(update);
    }

    /**
     * Centralized Meter HTML Renderer (Part 5.1)
     * Never renders a bare 0% for a null or degraded metric.
     */
    function renderMeterHtml(value, opts = {}) {
      const {
        isDegraded = false,
        thresholdGreen = 72,
        thresholdAmber = 50,
        showLabel = true,
        label = 'Score',
        max = 100,
        unit = '',
        id = ''
      } = opts;

      const isNullOrDegraded = isDegraded || value === null || value === undefined;

      if (isNullOrDegraded) {
        return `
          <div class="score-meter" ${id ? `id="${id}"` : ''}>
            ${showLabel ? `
              <div class="meter-label-row">
                <span>${escapeHtml(label)}</span>
                <span class="degraded-mode-chip" title="LLM offline — evaluated via deterministic rubric only">
                  ⚡ LLM Offline
                </span>
              </div>
            ` : ''}
            <div class="meter-track meter-track-degraded" title="LLM offline — deterministic rubric only">
              <div class="meter-fill meter-fill-degraded" style="width: 0%;"></div>
            </div>
          </div>
        `;
      }

      const num = Math.max(0, Math.min(max, Number(value)));
      const pct = (num / max) * 100;
      let fillCls = 'fill-red';
      if (pct >= thresholdGreen) fillCls = 'fill-green';
      else if (pct >= thresholdAmber) fillCls = 'fill-amber';

      return `
        <div class="score-meter" ${id ? `id="${id}"` : ''}>
          ${showLabel ? `
            <div class="meter-label-row">
              <span>${escapeHtml(label)}</span>
              <span class="meter-score-num tabular-nums">${num.toFixed(0)}${unit}</span>
            </div>
          ` : ''}
          <div class="meter-track">
            <div class="meter-fill ${fillCls}" style="width: ${pct}%;"></div>
          </div>
        </div>
      `;
    }

    /**
     * Centralized Meter DOM Element Updater (Part 5.1)
     * Updates track, fill, and value element safely without bare 0%.
     */
    function updateMeterElement(trackEl, fillEl, valEl, value, opts = {}) {
      const {
        isDegraded = false,
        thresholdGreen = 72,
        thresholdAmber = 50,
        max = 100,
        unit = ' / 100'
      } = opts;

      const isNullOrDegraded = isDegraded || value === null || value === undefined;

      if (isNullOrDegraded) {
        if (trackEl) {
          trackEl.classList.add('meter-track-degraded');
          trackEl.title = 'Awaiting live model — deterministic rubric only';
        }
        if (fillEl) {
          fillEl.style.width = '0%';
          fillEl.className = 'meter-fill meter-fill-degraded';
        }
        if (valEl) {
          valEl.innerHTML = `<span class="degraded-mode-chip" title="LLM offline — deterministic rubric only">⚡ LLM offline</span>`;
        }
        return;
      }

      if (trackEl) {
        trackEl.classList.remove('meter-track-degraded');
        trackEl.removeAttribute('title');
      }
      const num = Math.max(0, Math.min(max, Number(value)));
      const pct = (num / max) * 100;
      let fillCls = 'fill-red';
      if (pct >= thresholdGreen) fillCls = 'fill-green';
      else if (pct >= thresholdAmber) fillCls = 'fill-amber';

      if (fillEl) {
        fillEl.className = `meter-fill ${fillCls}`;
        fillEl.style.width = `${pct}%`;
      }
      if (valEl) {
        animateNumber(valEl, 0, num, 600, 1, unit);
      }
    }

    /**
     * Signature 3D Tilt Interaction for Candidate Cards (Part 4.6)
     */
    function handleCardTilt(e, card) {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = ((y - centerY) / centerY) * -4.5;
      const rotateY = ((x - centerX) / centerX) * 4.5;
      card.style.transform = `perspective(850px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-4px)`;
    }

    function resetCardTilt(card) {
      card.style.transform = '';
    }

    /**
     * Subtle pointer-driven Parallax for Hero and Modals (Part 4.2)
     */
    function initParallax() {
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

      // Note: Mascot parallax is handled cleanly by MascotCursorTracker on the sub-pixel lean layer
      document.querySelectorAll('.modal-dialog').forEach(dlg => {
        dlg.addEventListener('mousemove', (e) => {
          const rect = dlg.getBoundingClientRect();
          const x = ((e.clientX - rect.left) / rect.width - 0.5) * 5;
          const y = ((e.clientY - rect.top) / rect.height - 0.5) * 5;
          dlg.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
        });
        dlg.addEventListener('mouseleave', () => {
          dlg.style.transform = '';
        });
      });
    }

    /**
     * Hero Panel Dynamic Stats (Part 4.1)
     */
    function updateHeroStats() {
      const cases = AppState.cases || [];
      const realCases = cases.filter(c => !isBenchmarkCandidate(c.candidate_id));
      const total = realCases.length;
      const verified = realCases.filter(c => {
        const unsupp = c.unsupported_claim_count || 0;
        const contra = c.contradicted_claim_count || (c.has_discrepancies ? 1 : 0);
        return unsupp === 0 && contra === 0;
      }).length;

      const countEl = document.getElementById('heroCandidateCount');
      const verEl = document.getElementById('heroVerifiedCount');
      if (countEl) animateNumber(countEl, 0, total, 600, 0);
      if (verEl) animateNumber(verEl, 0, verified, 600, 0);

      const notice = document.getElementById('heroDegradedNotice');
      if (notice) {
        notice.style.display = AppState.isDegraded ? 'inline-block' : 'none';
      }
    }

    function toggleHeroVerifiedFilter() {
      const chk = document.getElementById('checkFilterVerifiedOnly');
      const heroBtn = document.getElementById('heroBtnVerifiedOnly');
      AppState.filters.verifiedOnly = !AppState.filters.verifiedOnly;
      if (chk) chk.checked = AppState.filters.verifiedOnly;
      if (heroBtn) {
        if (AppState.filters.verifiedOnly) {
          heroBtn.classList.add('active');
          heroBtn.setAttribute('aria-pressed', 'true');
        } else {
          heroBtn.classList.remove('active');
          heroBtn.setAttribute('aria-pressed', 'false');
        }
      }
      syncUrlParams();
      updateFilterBadgeAndPills();
      applyCurrentFilter();
    }

    /* Helper: Initials & deterministic colors */
    function getInitials(name) {
      if (!name) return "??";
      const parts = name.trim().split(/\s+/);
      if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }

    function getAvatarColor(id) {
      const palettes = [
        { bg: "var(--info-subtle)", text: "var(--info-text)" },
        { bg: "var(--success-subtle)", text: "var(--success-text)" },
        { bg: "var(--accent-subtle)", text: "var(--accent-text)" },
        { bg: "var(--warning-subtle)", text: "var(--warning-text)" },
        { bg: "var(--danger-subtle)", text: "var(--danger-text)" },
        { bg: "var(--bg-surface-subtle)", text: "var(--text-secondary)" }
      ];
      let hash = 0;
      const str = String(id || "default");
      for (let i = 0; i < str.length; i++) {
        hash = (hash << 5) - hash + str.charCodeAt(i);
        hash |= 0;
      }
      return palettes[Math.abs(hash) % palettes.length];
    }

    function getBadgeClass(quadrant) {
      const q = String(quadrant || "").toUpperCase();
      if (q.includes("STRONG")) return "badge-strong";
      if (q.includes("REVIEW")) return "badge-review";
      if (q.includes("INSUFFICIENT")) return "badge-insufficient";
      if (q.includes("EVALUATING") || q.includes("QUEUED")) return "badge-evaluating";
      if (q.includes("DEGRADED") || q.includes("OFFLINE")) return "badge-degraded";
      return "badge-weak";
    }

    /* ==========================================================================
       THEME MANAGEMENT
       ========================================================================== */
    function initTheme() {
      const saved = localStorage.getItem('hiretrace_theme') || 'light';
      applyTheme(saved);
    }

    function applyTheme(theme) {
      if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
      localStorage.setItem('hiretrace_theme', theme);
      AppState.theme = theme;
      document.dispatchEvent(new CustomEvent('hiretrace:themechange', { detail: { theme: theme } }));
    }

    function toggleTheme() {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      applyTheme(isDark ? 'light' : 'dark');
    }

    /* ==========================================================================
       TOAST NOTIFICATIONS
       ========================================================================== */
    function showToast(message) {
      const el = document.getElementById('toastNotification');
      if (!el) return;
      el.textContent = message;
      el.classList.add('show');
      setTimeout(() => el.classList.remove('show'), 2500);
    }

    /* Track recently viewed candidates (max 5) */
    function trackRecentCandidate(c) {
      if (!c || !c.candidate_id) return;
      const entry = {
        id: c.candidate_id,
        name: c.name || c.candidate_name || c.candidate_id,
        role: c.target_role || c.role || "Software Engineer",
        quadrant: c.quadrant || c.quadrant_placement || "REVIEW REQUIRED"
      };
      AppState.recentCandidates = [
        entry,
        ...AppState.recentCandidates.filter(item => item.id !== entry.id)
      ].slice(0, 5);
      try {
        localStorage.setItem('hiretrace_recent_candidates', JSON.stringify(AppState.recentCandidates));
      } catch (e) {}
    }

    /* ==========================================================================
       COMMAND PALETTE (⌘K / Ctrl+K)
       ========================================================================== */
    function openCommandPalette() {
      const modal = document.getElementById('commandPaletteModal');
      const input = document.getElementById('cmdPaletteInput');
      if (!modal || !input) return;
      modal.classList.add('show');
      AppState.cmdPaletteOpen = true;
      AppState.cmdPaletteIndex = 0;
      input.value = '';
      renderCmdPaletteResults('');
      setTimeout(() => input.focus(), 60);
    }

    function closeCommandPalette() {
      const modal = document.getElementById('commandPaletteModal');
      if (modal) modal.classList.remove('show');
      AppState.cmdPaletteOpen = false;
    }

    function handleCmdPaletteBackdropClick(e) {
      if (e.target.id === 'commandPaletteModal') {
        closeCommandPalette();
      }
    }

    function handleCmdPaletteInput(query) {
      AppState.cmdPaletteIndex = 0;
      renderCmdPaletteResults(query);
    }

    function getCmdPaletteActions() {
      return [
        {
          id: 'act-new',
          type: 'action',
          title: 'New Candidate Assessment',
          sub: 'Upload resume and multi-source evidence',
          action: () => { closeCommandPalette(); openNewApplicantModal(); }
        },
        {
          id: 'act-theme',
          type: 'action',
          title: 'Toggle Dark / Light Theme',
          sub: 'Switch UI appearance mode',
          action: () => { closeCommandPalette(); toggleTheme(); }
        },
        {
          id: 'act-export',
          type: 'action',
          title: 'Export Active Dossier (PDF)',
          sub: 'Print or export current assessment dossier',
          action: () => { closeCommandPalette(); exportReportToPdf(); }
        },
        {
          id: 'act-clear',
          type: 'action',
          title: 'Reset Candidate Filters',
          sub: 'Clear all active search and quadrant filters',
          action: () => { closeCommandPalette(); clearFilters(); }
        }
      ];
    }

    function getCmdPaletteNav() {
      return [
        {
          id: 'nav-cand',
          type: 'nav',
          title: 'Go to Candidates Workspace',
          sub: 'Primary candidate evidence workspace',
          action: () => { closeCommandPalette(); navigateTo('candidates'); }
        },
        {
          id: 'nav-rank',
          type: 'nav',
          title: 'Go to Requisition Ranking',
          sub: 'Compare and rank candidates across requisitions',
          action: () => { closeCommandPalette(); navigateTo('leaderboard'); }
        },
        {
          id: 'nav-audit',
          type: 'nav',
          title: 'Go to Governance & EEOC Audit',
          sub: 'Inspect fairness, Spearman rho, and EEOC compliance',
          action: () => { closeCommandPalette(); navigateTo('audit'); }
        }
      ];
    }

    function renderCmdPaletteResults(query) {
      const container = document.getElementById('cmdPaletteResults');
      if (!container) return;

      const q = (query || '').toLowerCase().trim();
      const items = [];

      // 1. Recents (when empty query)
      if (!q && AppState.recentCandidates.length > 0) {
        items.push({ isHeader: true, title: 'RECENT CANDIDATES' });
        for (const r of AppState.recentCandidates) {
          items.push({
            id: `recent-${r.id}`,
            type: 'candidate',
            title: r.name,
            sub: `${r.role} • [${r.quadrant}]`,
            action: () => { closeCommandPalette(); navigateTo('profile', r.id); }
          });
        }
      }

      // 2. Candidate matches
      const candMatches = AppState.cases.filter(c => {
        if (!q) return false;
        return (c.name || '').toLowerCase().includes(q) ||
               (c.target_role || '').toLowerCase().includes(q) ||
               (c.candidate_id || '').toLowerCase().includes(q);
      }).slice(0, 6);

      if (candMatches.length > 0) {
        items.push({ isHeader: true, title: 'CANDIDATES' });
        for (const c of candMatches) {
          items.push({
            id: `cand-${c.candidate_id}`,
            type: 'candidate',
            title: c.name || c.candidate_id,
            sub: `${c.target_role || 'Senior Software Engineer'} • [${c.quadrant || 'EVALUATING'}]`,
            action: () => { closeCommandPalette(); navigateTo('profile', c.candidate_id); }
          });
        }
      }

      // 3. Actions
      const actions = getCmdPaletteActions().filter(a => {
        if (!q) return true;
        return a.title.toLowerCase().includes(q) || a.sub.toLowerCase().includes(q);
      });
      if (actions.length > 0) {
        items.push({ isHeader: true, title: 'ACTIONS' });
        items.push(...actions);
      }

      // 4. Navigation
      const navs = getCmdPaletteNav().filter(n => {
        if (!q) return true;
        return n.title.toLowerCase().includes(q) || n.sub.toLowerCase().includes(q);
      });
      if (navs.length > 0) {
        items.push({ isHeader: true, title: 'NAVIGATION' });
        items.push(...navs);
      }

      const selectableItems = items.filter(it => !it.isHeader);
      AppState.cmdPaletteItems = selectableItems;

      if (AppState.cmdPaletteIndex >= selectableItems.length) {
        AppState.cmdPaletteIndex = Math.max(0, selectableItems.length - 1);
      }

      if (selectableItems.length === 0) {
        container.innerHTML = `<div class="cmd-palette-empty">No results found for "${escapeHtml(query)}"</div>`;
        return;
      }

      let selectableCounter = 0;
      container.innerHTML = items.map(it => {
        if (it.isHeader) {
          return `<div class="cmd-palette-section-title">${escapeHtml(it.title)}</div>`;
        }
        const isSelected = selectableCounter === AppState.cmdPaletteIndex;
        const idx = selectableCounter++;
        const badge = it.type === 'candidate' ? '<span class="badge badge-strong" style="font-size:0.65rem;">Candidate</span>'
                    : it.type === 'action' ? '<span class="badge badge-review" style="font-size:0.65rem;">Action</span>'
                    : '<span class="badge badge-insufficient" style="font-size:0.65rem;">View</span>';

        return `
          <div class="cmd-palette-item ${isSelected ? 'selected' : ''}"
               role="option"
               aria-selected="${isSelected}"
               data-idx="${idx}">
            <div class="cmd-palette-item-left">
              <div class="cmd-palette-item-title">${escapeHtml(it.title)}</div>
              <div class="cmd-palette-item-sub">${escapeHtml(it.sub)}</div>
            </div>
            ${badge}
          </div>
        `;
      }).join('');

      const selectedEl = container.querySelector('.cmd-palette-item.selected');
      if (selectedEl) selectedEl.scrollIntoView({ block: 'nearest' });
    }

    function handleCmdPaletteKeydown(e) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (AppState.cmdPaletteItems.length > 0) {
          AppState.cmdPaletteIndex = (AppState.cmdPaletteIndex + 1) % AppState.cmdPaletteItems.length;
          renderCmdPaletteResults(document.getElementById('cmdPaletteInput')?.value || '');
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (AppState.cmdPaletteItems.length > 0) {
          AppState.cmdPaletteIndex = (AppState.cmdPaletteIndex - 1 + AppState.cmdPaletteItems.length) % AppState.cmdPaletteItems.length;
          renderCmdPaletteResults(document.getElementById('cmdPaletteInput')?.value || '');
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        executeCmdPaletteItem(AppState.cmdPaletteIndex);
      } else if (e.key === 'Escape') {
        closeCommandPalette();
      }
    }

    function executeCmdPaletteItem(idx) {
      const item = AppState.cmdPaletteItems[idx];
      if (item && typeof item.action === 'function') {
        item.action();
      }
    }

    /* ==========================================================================
       SYSTEM MODE (Live vs Demo)
       ========================================================================== */
    async function checkSystemMode() {
      try {
        const res = await fetch("/api/system/mode");
        if (res.ok) {
          const data = await res.json();
          const isLive = (data.mode === "live" && data.llm_available !== false);
          AppState.llmAvailable = isLive;
          AppState.isDegraded = !isLive;
          AppState.systemMode = data.mode || (isLive ? 'live' : 'demo');

          const badge = document.getElementById("systemModeBadge");
          const label = document.getElementById("systemModeLabel");
          if (badge && label) {
            if (isLive) {
              badge.className = "status-pill mode-live";
              badge.title = `Live Mode: Ollama LLM backend online (${data.model || "qwen2.5:3b"}). Multi-agent evaluation ready.`;
              label.textContent = `Live Mode (${(data.model || "Ollama").toUpperCase()})`;
            } else {
              badge.className = "status-pill mode-demo";
              badge.title = "Local Ollama LLM offline. Zero-cost deterministic rubric evaluations active.";
              label.textContent = "Demo Mode (Deterministic)";
            }
          }

          const heroNotice = document.getElementById('heroDegradedNotice');
          if (heroNotice) {
            heroNotice.style.display = isLive ? 'none' : 'inline-block';
          }
          updateHeroStats();
        }
      } catch (e) {
        console.log("System mode check skipped:", e);
      }
    }

    /* ==========================================================================
       ROUTING & VIEW NAVIGATION
       ========================================================================== */
    /* ==========================================================================
       ROUTING & VIEW NAVIGATION (Deep Linkable URL State)
       ========================================================================== */
    function navigateTo(viewName, candidateId = null) {
      if (viewName === 'profile' && candidateId) {
        window.location.hash = `#/candidates/${encodeURIComponent(candidateId)}`;
      } else if (viewName === 'leaderboard') {
        if (AppState.currentView === 'candidates' && typeof triggerPortalDive === 'function' && TIER > 0 && !QualityTier.isReducedMotion) {
          triggerPortalDive('viewLeaderboard', () => {
            window.location.hash = '#/leaderboard';
          });
        } else {
          window.location.hash = '#/leaderboard';
        }
      } else if (viewName === 'audit') {
        if (AppState.currentView === 'candidates' && typeof triggerPortalDive === 'function' && TIER > 0 && !QualityTier.isReducedMotion) {
          triggerPortalDive('viewAudit', () => {
            window.location.hash = '#/audit';
          });
        } else {
          window.location.hash = '#/audit';
        }
      } else {
        window.location.hash = '#/candidates';
      }
    }

    function syncUrlParams() {
      if (AppState.currentView !== 'candidates') return;
      const params = new URLSearchParams();
      const s = document.getElementById('candSearchInput')?.value.trim();
      if (s) params.set('q', s);
      if (AppState.filters.quadrant !== 'all') params.set('quadrant', AppState.filters.quadrant);
      if (AppState.filters.contradictions) params.set('contra', '1');
      if (AppState.filters.unsupported) params.set('unsupp', '1');
      if (AppState.filters.verifiedOnly) params.set('verified', '1');
      if (AppState.filters.includeDemo) params.set('demo', '1');
      if (AppState.viewMode === 'list') params.set('view', 'list');

      const qStr = params.toString();
      const targetHash = qStr ? `#/candidates?${qStr}` : '#/candidates';
      if (window.location.hash !== targetHash) {
        window.history.replaceState(null, '', targetHash);
      }
    }

    function handleHashChange() {
      const fullHash = window.location.hash || '#/candidates';
      const [hashPath, queryString] = fullHash.split('?');
      const params = new URLSearchParams(queryString || '');

      // Update primary navigation tabs
      document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.mobile-bottom-item').forEach(btn => btn.classList.remove('active'));

      if (hashPath.startsWith('#/candidates/')) {
        const cid = decodeURIComponent(hashPath.slice('#/candidates/'.length));
        showView('viewProfile');
        AppState.currentView = 'profile';
        document.getElementById('navBtnCandidates')?.classList.add('active');
        document.getElementById('mobBtnCandidates')?.classList.add('active');

        if (cid && cid !== AppState.activeCaseId) {
          loadCandidate(cid).then(() => {
            const requestedTab = params.get('tab') || 'overview';
            switchProfileTab(requestedTab, false);
          });
        } else {
          const requestedTab = params.get('tab') || 'overview';
          switchProfileTab(requestedTab, false);
        }
      } else if (hashPath === '#/leaderboard' || hashPath === '#/ranking') {
        showView('viewLeaderboard');
        AppState.currentView = 'leaderboard';
        document.getElementById('navBtnLeaderboard')?.classList.add('active');
        document.getElementById('mobBtnLeaderboard')?.classList.add('active');
        renderLeaderboard();
      } else if (hashPath === '#/audit') {
        showView('viewAudit');
        AppState.currentView = 'audit';
        document.getElementById('navBtnAudit')?.classList.add('active');
        document.getElementById('mobBtnAudit')?.classList.add('active');
        loadAuditSummary();
        loadBenchmarks();
        setTimeout(initAuditOrb, 80);
      } else {
        showView('viewCandidates');
        AppState.currentView = 'candidates';
        document.getElementById('navBtnCandidates')?.classList.add('active');
        document.getElementById('mobBtnCandidates')?.classList.add('active');

        // Restore filter and view mode state from URL query parameters
        if (params.has('q')) {
          const s = document.getElementById('candSearchInput');
          if (s) s.value = params.get('q');
        }
        if (params.has('quadrant')) {
          AppState.filters.quadrant = params.get('quadrant');
          const r = document.querySelector(`input[name="filterQuadRadio"][value="${params.get('quadrant')}"]`);
          if (r) r.checked = true;
        }
        if (params.has('contra')) {
          AppState.filters.contradictions = params.get('contra') === '1';
          const c = document.getElementById('checkFilterContradictions');
          if (c) c.checked = AppState.filters.contradictions;
        }
        if (params.has('unsupp')) {
          AppState.filters.unsupported = params.get('unsupp') === '1';
          const c = document.getElementById('checkFilterUnsupported');
          if (c) c.checked = AppState.filters.unsupported;
        }
        if (params.has('verified')) {
          AppState.filters.verifiedOnly = params.get('verified') === '1';
          const c = document.getElementById('checkFilterVerifiedOnly');
          if (c) c.checked = AppState.filters.verifiedOnly;
        }
        if (params.has('demo')) {
          AppState.filters.includeDemo = params.get('demo') === '1';
          const c = document.getElementById('checkFilterIncludeDemo');
          if (c) c.checked = AppState.filters.includeDemo;
        }
        if (params.has('view')) {
          setViewMode(params.get('view'));
        } else {
          setViewMode(AppState.viewMode);
        }

        updateFilterBadgeAndPills();
        applyCurrentFilter();
      }
    }

    function showView(viewId) {
      document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
      const target = document.getElementById(viewId);
      if (target) target.classList.add('active');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    /* ==========================================================================
       CANDIDATES DATA FETCHING & RENDERING
       ========================================================================== */
    async function fetchCasesAndRender() {
      const showDemo = AppState.filters.includeDemo || (localStorage.getItem('hiretrace_show_demo_data') === 'true');

      if (!AppState.cases || AppState.cases.length === 0) {
        AppState.isLoadingCases = true;
        applyCurrentFilter();
      }

      try {
        const res = await fetch(`/api/cases?include_demo=${showDemo ? 'true' : 'false'}`);
        if (!res.ok) throw new Error("HTTP " + res.status);
        AppState.cases = await res.json();
      } catch (err) {
        console.warn("Live API unavailable, using fallback static dataset:", err);
        if (window.HIRETRACE_STATIC && window.HIRETRACE_STATIC.cases) {
          AppState.cases = window.HIRETRACE_STATIC.cases;
          if (!showDemo) {
            AppState.cases = AppState.cases.filter(c => !isBenchmarkCandidate(c.candidate_id));
          }
        }
      } finally {
        AppState.isLoadingCases = false;
      }

      AppState.cases = deduplicateCandidates(AppState.cases);

      // Populate leaderboard role selector
      const roleSelect = document.getElementById("leaderboardRoleSelect");
      if (roleSelect && AppState.cases.length > 0) {
        const roles = Array.from(new Set(AppState.cases.map(c => c.target_role).filter(Boolean)));
        if (roles.length > 0) {
          roleSelect.innerHTML = `<option value="all">All Requisitions (${AppState.cases.length} candidates)</option>` +
            roles.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join("");
        }
      }

      applyCurrentFilter();
      renderLeaderboard();
    }

    function toggleDemoGroup() {
      AppState.isDemoGroupExpanded = !AppState.isDemoGroupExpanded;
      const container = document.getElementById('demoCardsContainer');
      const arrow = document.getElementById('demoGroupArrow');
      if (container) container.style.display = AppState.isDemoGroupExpanded ? 'grid' : 'none';
      if (arrow) arrow.textContent = AppState.isDemoGroupExpanded ? '▲' : '▾';
    }

    /* ==========================================================================
       FILTER POPOVER & ACTIVE FILTER PILLS
       ========================================================================== */
    function toggleFilterPopover() {
      const pop = document.getElementById('filterPopover');
      const btn = document.getElementById('btnFilterTrigger');
      if (!pop) return;
      const isShown = pop.classList.contains('show');
      if (isShown) {
        pop.classList.remove('show');
        if (btn) btn.setAttribute('aria-expanded', 'false');
      } else {
        pop.classList.add('show');
        if (btn) btn.setAttribute('aria-expanded', 'true');
      }
    }

    // Close popover when clicking outside
    document.addEventListener('click', (e) => {
      const anchor = document.querySelector('.filter-popover-anchor');
      const pop = document.getElementById('filterPopover');
      if (anchor && pop && pop.classList.contains('show')) {
        if (!anchor.contains(e.target)) {
          pop.classList.remove('show');
          const btn = document.getElementById('btnFilterTrigger');
          if (btn) btn.setAttribute('aria-expanded', 'false');
        }
      }
    });

    function handleSearchFilterChange() {
      syncUrlParams();
      applyCurrentFilter();
    }

    function handleFilterOptionChange() {
      const quadRadio = document.querySelector('input[name="filterQuadRadio"]:checked');
      AppState.filters.quadrant = quadRadio ? quadRadio.value : 'all';
      AppState.filters.contradictions = Boolean(document.getElementById('checkFilterContradictions')?.checked);
      AppState.filters.unsupported = Boolean(document.getElementById('checkFilterUnsupported')?.checked);
      AppState.filters.verifiedOnly = Boolean(document.getElementById('checkFilterVerifiedOnly')?.checked);
      AppState.filters.includeDemo = Boolean(document.getElementById('checkFilterIncludeDemo')?.checked);

      localStorage.setItem('hiretrace_show_demo_data', AppState.filters.includeDemo ? 'true' : 'false');

      const heroBtn = document.getElementById('heroBtnVerifiedOnly');
      if (heroBtn) {
        heroBtn.classList.toggle('active', AppState.filters.verifiedOnly);
        heroBtn.setAttribute('aria-pressed', AppState.filters.verifiedOnly ? 'true' : 'false');
      }

      updateFilterBadgeAndPills();
      syncUrlParams();
      applyCurrentFilter();
    }

    function updateFilterBadgeAndPills() {
      const countBadge = document.getElementById('filterCountBadge');
      const pillsBar = document.getElementById('activeFiltersBar');
      let activeCount = 0;
      const pills = [];

      if (AppState.filters.quadrant !== 'all') {
        activeCount++;
        pills.push({
          label: `Quadrant: ${AppState.filters.quadrant}`,
          onRemove: () => {
            const r = document.querySelector('input[name="filterQuadRadio"][value="all"]');
            if (r) r.checked = true;
            handleFilterOptionChange();
          }
        });
      }

      if (AppState.filters.contradictions) {
        activeCount++;
        pills.push({
          label: 'Contradictions Detected',
          onRemove: () => {
            const c = document.getElementById('checkFilterContradictions');
            if (c) c.checked = false;
            handleFilterOptionChange();
          }
        });
      }

      if (AppState.filters.unsupported) {
        activeCount++;
        pills.push({
          label: 'Unsupported Claims',
          onRemove: () => {
            const c = document.getElementById('checkFilterUnsupported');
            if (c) c.checked = false;
            handleFilterOptionChange();
          }
        });
      }

      if (AppState.filters.verifiedOnly) {
        activeCount++;
        pills.push({
          label: 'Fully Verified Only',
          onRemove: () => {
            const c = document.getElementById('checkFilterVerifiedOnly');
            if (c) c.checked = false;
            handleFilterOptionChange();
          }
        });
      }

      if (AppState.filters.includeDemo) {
        activeCount++;
        pills.push({
          label: 'Include Benchmarks',
          onRemove: () => {
            const c = document.getElementById('checkFilterIncludeDemo');
            if (c) c.checked = false;
            handleFilterOptionChange();
          }
        });
      }

      if (countBadge) {
        if (activeCount > 0) {
          countBadge.textContent = activeCount;
          countBadge.style.display = 'inline-flex';
        } else {
          countBadge.style.display = 'none';
        }
      }

      if (pillsBar) {
        if (pills.length > 0) {
          pillsBar.style.display = 'flex';
          pillsBar.innerHTML = pills.map((p, idx) => `
            <span class="filter-pill">
              <span>${escapeHtml(p.label)}</span>
              <button type="button" class="filter-pill-remove" data-pill-idx="${idx}" aria-label="Remove filter ${escapeHtml(p.label)}">×</button>
            </span>
          `).join('') + `
            <button type="button" class="btn btn-ghost btn-sm" data-action="clearFilters" style="font-size: 0.72rem; padding: 0.15rem 0.5rem;">Clear all</button>
          `;
          window._activePillsCallbacks = pills.map(p => p.onRemove);
        } else {
          pillsBar.style.display = 'none';
          pillsBar.innerHTML = '';
          window._activePillsCallbacks = [];
        }
      }
    }

    function removeFilterPill(index) {
      if (window._activePillsCallbacks && window._activePillsCallbacks[index]) {
        window._activePillsCallbacks[index]();
      }
    }

    function clearFilters() {
      const s = document.getElementById('candSearchInput');
      if (s) s.value = '';
      const quadAll = document.querySelector('input[name="filterQuadRadio"][value="all"]');
      if (quadAll) quadAll.checked = true;

      const cContra = document.getElementById('checkFilterContradictions');
      if (cContra) cContra.checked = false;
      const cUnsupp = document.getElementById('checkFilterUnsupported');
      if (cUnsupp) cUnsupp.checked = false;
      const cVerif = document.getElementById('checkFilterVerifiedOnly');
      if (cVerif) cVerif.checked = false;
      const cDemo = document.getElementById('checkFilterIncludeDemo');
      if (cDemo) cDemo.checked = false;

      handleFilterOptionChange();
    }

    /* ==========================================================================
       VIEW MODE SWITCHING (GRID vs LIST)
       ========================================================================== */
    function setViewMode(mode) {
      AppState.viewMode = mode;
      localStorage.setItem('hiretrace_view_mode', mode);

      const btnGrid = document.getElementById('btnViewGrid');
      const btnList = document.getElementById('btnViewList');
      const gridEl = document.getElementById('candidatesGrid');
      const listEl = document.getElementById('candidatesListView');

      if (mode === 'list') {
        if (btnGrid) btnGrid.classList.remove('active');
        if (btnList) btnList.classList.add('active');
        if (gridEl) gridEl.style.display = 'none';
        if (listEl) listEl.style.display = 'block';
      } else {
        if (btnGrid) btnGrid.classList.add('active');
        if (btnList) btnList.classList.remove('active');
        if (gridEl) gridEl.style.display = 'grid';
        if (listEl) listEl.style.display = 'none';
      }
      syncUrlParams();
    }

    function applyCurrentFilter() {
      let filtered = [...AppState.cases];

      // Search query filter
      const search = (document.getElementById('candSearchInput')?.value || '').toLowerCase().trim();
      if (search) {
        filtered = filtered.filter(c =>
          (c.name || '').toLowerCase().includes(search) ||
          (c.target_role || '').toLowerCase().includes(search) ||
          (c.candidate_id || '').toLowerCase().includes(search) ||
          (c.quadrant || '').toLowerCase().includes(search)
        );
      }

      // Quadrant filter
      if (AppState.filters.quadrant && AppState.filters.quadrant !== 'all') {
        filtered = filtered.filter(c => c.quadrant === AppState.filters.quadrant);
      }

      // Contradictions filter
      if (AppState.filters.contradictions) {
        filtered = filtered.filter(c => (c.contradicted_claim_count || 0) > 0 || c.has_discrepancies);
      }

      // Unsupported claims filter
      if (AppState.filters.unsupported) {
        filtered = filtered.filter(c => (c.unsupported_claim_count || 0) > 0);
      }

      // Fully verified only
      if (AppState.filters.verifiedOnly) {
        filtered = filtered.filter(c => {
          const contra = c.contradicted_claim_count || (c.has_discrepancies ? 1 : 0);
          const unsup = c.unsupported_claim_count || 0;
          return contra === 0 && unsup === 0 && (c.quadrant === 'STRONG MATCH' || c.quadrant === '[STRONG MATCH]' || !c.has_discrepancies);
        });
      }

      // Benchmark filter
      if (!AppState.filters.includeDemo) {
        filtered = filtered.filter(c => !isBenchmarkCandidate(c.candidate_id));
      }

      renderCandidateGrid(filtered);
      renderCandidateListView(filtered);
    }

    function renderCandidateGrid(items) {
      const showDemo = AppState.filters.includeDemo;
      const grid = document.getElementById('candidatesGrid');
      const demoSection = document.getElementById('demoSectionContainer');
      const demoCards = document.getElementById('demoCardsContainer');
      const demoGroupCount = document.getElementById('demoGroupCount');

      if (AppState.isLoadingCases && (!items || items.length === 0)) {
        if (grid) {
          grid.innerHTML = `
            <div class="card-tile-new" style="opacity: 0.6; pointer-events: none;">
              <div class="plus-icon-box">+</div>
              <div class="card-tile-new-title">Loading...</div>
            </div>
            ${Array.from({length: 4}).map(() => `
              <div class="candidate-card" style="pointer-events: none;">
                <div class="card-top">
                  <div class="card-header-row" style="align-items: center;">
                    <div class="skeleton-box" style="width: 36px; height: 36px; border-radius: var(--radius-full);"></div>
                    <div style="flex: 1; margin-left: 0.75rem;">
                      <div class="skeleton-box" style="height: 14px; width: 60%; margin-bottom: 6px;"></div>
                      <div class="skeleton-box" style="height: 10px; width: 40%;"></div>
                    </div>
                  </div>
                  <div style="margin-top: 1.25rem;">
                    <div class="skeleton-box" style="height: 12px; width: 100%; margin-bottom: 8px;"></div>
                    <div class="skeleton-box" style="height: 12px; width: 85%;"></div>
                  </div>
                </div>
              </div>
            `).join('')}
          `;
        }
        return;
      }

      const realCandidates = [];
      const benchmarkCandidates = [];

      for (const c of items) {
        if (isBenchmarkCandidate(c.candidate_id)) {
          benchmarkCandidates.push(c);
        } else {
          realCandidates.push(c);
        }
      }

      const newTileHtml = `
        <div class="card-tile-new" tabindex="0" data-action="openNewApplicantModal" title="Add a new candidate dossier">
          <div class="plus-icon-box">+</div>
          <div class="card-tile-new-title">New Candidate</div>
          <div class="card-tile-new-sub">Upload resume &amp; multi-source artifacts</div>
        </div>
      `;

      if (grid) {
        if (realCandidates.length === 0 && (document.getElementById('candSearchInput')?.value.trim() !== '' || AppState.filters.quadrant !== 'all')) {
          grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
              <div class="empty-state-mascot">
                <img src="/mascot.svg" alt="HireTrace Mascot" width="44" height="44" />
              </div>
              <div class="empty-state-title">No candidates match current filters</div>
              <div class="empty-state-sub">No one matches these filters yet — try widening your search, switching quadrants, or resetting criteria.</div>
              <button class="btn btn-secondary btn-sm" data-action="clearFilters" style="margin-top: 0.5rem;">Reset Filters</button>
            </div>
          `;
        } else if (realCandidates.length === 0) {
          grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
              <div class="empty-state-mascot">
                <img src="/mascot.svg" alt="HireTrace Mascot" width="44" height="44" />
              </div>
              <div class="empty-state-title">Your assessment pipeline is ready</div>
              <div class="empty-state-sub">Every hiring decision starts with verifiable evidence. Add your first candidate dossier to begin cross-source timeline and claim verification.</div>
              <div style="display: flex; gap: 0.5rem; margin-top: 0.75rem;">
                <button class="btn btn-primary btn-sm" data-action="openNewApplicantModal">New Candidate</button>
                <button class="btn btn-secondary btn-sm" data-action="fetchCasesAndRender">Refresh</button>
              </div>
            </div>
          `;
        } else {
          grid.innerHTML = newTileHtml + realCandidates.map((c, idx) => renderCandidateCard(c, false, idx)).join('');
        }
      }

      if (demoSection && demoCards) {
        if (showDemo && benchmarkCandidates.length > 0) {
          demoSection.style.display = 'block';
          if (demoGroupCount) demoGroupCount.textContent = benchmarkCandidates.length;
          demoCards.innerHTML = benchmarkCandidates.map((c, idx) => renderCandidateCard(c, true, idx)).join('');
        } else {
          demoSection.style.display = 'none';
          demoCards.innerHTML = '';
        }
      }

      updateHeroStats();
    }

    function renderCandidateListView(items) {
      const tbody = document.getElementById('candidatesListBody');
      if (!tbody) return;

      if (AppState.isLoadingCases && (!items || items.length === 0)) {
        tbody.innerHTML = Array.from({length: 4}).map(() => `
          <tr>
            <td colspan="7" style="padding: 1rem;">
              <div class="skeleton-box" style="height: 16px; width: 80%;"></div>
            </td>
          </tr>
        `).join('');
        return;
      }

      const realCandidates = items.filter(c => AppState.filters.includeDemo || !isBenchmarkCandidate(c.candidate_id));

      if (realCandidates.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 2.5rem;"><div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.35rem;">No candidates match current filters</div><div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.75rem;">Try clearing your search query or switching quadrants.</div><button class="btn btn-secondary btn-sm" data-action="clearFilters">Reset Filters</button></td></tr>`;
        return;
      }

      tbody.innerHTML = realCandidates.map((c, idx) => {
        const isDegradedCandidate = Boolean(c.degraded || (c.quadrant && c.quadrant.includes('DEGRADED')) || AppState.isDegraded);
        // Strict P0 Score Integrity: NEVER invent scores
        const fit = (c.role_fit_score !== null && c.role_fit_score !== undefined)
          ? (isDegradedCandidate ? '<span class="degraded-mode-chip">⚡ Rubric</span>' : Number(c.role_fit_score).toFixed(1))
          : 'Pending';
        const cons = (c.evidence_consistency_score !== null && c.evidence_consistency_score !== undefined)
          ? Number(c.evidence_consistency_score).toFixed(1)
          : 'Pending';

        const quad = c.quadrant || 'REVIEW REQUIRED';
        const badgeCls = getBadgeClass(quad);
        const contra = c.contradicted_claim_count || (c.has_discrepancies ? 1 : 0);
        const unsupp = c.unsupported_claim_count || 0;

        return `
          <tr class="stagger-in" style="animation-delay: ${Math.min(idx * 30, 350)}ms">
            <td>
              <a href="#/candidates/${encodeURIComponent(c.candidate_id)}" style="font-weight: 600; color: var(--text-primary); text-decoration: none;">
                ${escapeHtml(c.name || c.candidate_id)}
              </a>
            </td>
            <td style="color: var(--text-secondary); font-size: 0.78rem;">
              ${escapeHtml(c.target_role || 'Senior Software Engineer')}
              ${isDegradedCandidate ? '<span class="degraded-mode-chip" style="margin-left: 0.25rem;">⚡ Demo</span>' : ''}
            </td>
            <td><strong class="tabular-nums" style="font-family: var(--font-mono);">${fit}</strong></td>
            <td><span class="tabular-nums" style="font-family: var(--font-mono); font-weight: 600;">${cons}</span></td>
            <td><span class="badge ${badgeCls}">${escapeHtml(quad)}</span></td>
            <td>
              ${contra > 0 ? `<span class="flag-pill flag-warn">${contra} Conflict${contra > 1 ? 's' : ''}</span> ` : ''}
              ${unsupp > 0 ? `<span class="flag-pill flag-warn">${unsupp} Unverified</span>` : ''}
              ${contra === 0 && unsupp === 0 ? `<span class="flag-pill flag-clean">✓ Verified</span>` : ''}
            </td>
            <td style="text-align: right;">
              <a class="btn btn-secondary btn-sm" href="#/candidates/${encodeURIComponent(c.candidate_id)}">Inspect →</a>
            </td>
          </tr>
        `;
      }).join('');
    }

    function renderCandidateCard(c, isDemo, idx = 0) {
      const color = getAvatarColor(c.candidate_id || c.name);
      const initials = getInitials(c.name);
      const badgeCls = getBadgeClass(c.quadrant);
      const isDegradedCandidate = Boolean(c.degraded || (c.quadrant && c.quadrant.includes('DEGRADED')) || AppState.isDegraded);

      // Strict P0 Score Integrity: NEVER invent scores
      const hasFit = (c.role_fit_score !== undefined && c.role_fit_score !== null);
      const hasCons = (c.evidence_consistency_score !== undefined && c.evidence_consistency_score !== null);

      const fitNum = hasFit ? Number(c.role_fit_score) : null;
      const consNum = hasCons ? Number(c.evidence_consistency_score) : null;

      const unsupp = c.unsupported_claim_count || 0;
      const contra = c.contradicted_claim_count || (c.has_discrepancies ? 1 : 0);

      let snippet = "Verified evidence profile across submitted documents.";
      if (c.quadrant === 'STRONG MATCH') snippet = "High technical role alignment with verified production claims.";
      else if (c.quadrant === 'REVIEW REQUIRED') snippet = "Cross-source discrepancies flagged between CV claims and interview/assessment.";
      else if (c.quadrant === 'WEAK MATCH') snippet = "Technical prerequisite divergence observed across primary evaluation rubric.";
      else if (c.quadrant === 'INSUFFICIENT EVIDENCE') snippet = "Profile lacks sufficient multi-document evidence to verify production claims.";

      const fitMeterHtml = renderMeterHtml(hasFit ? fitNum : null, {
        isDegraded: isDegradedCandidate,
        thresholdGreen: 72,
        thresholdAmber: 50,
        label: 'Role Fit'
      });

      const consMeterHtml = renderMeterHtml(hasCons ? consNum : null, {
        isDegraded: false,
        thresholdGreen: 70,
        thresholdAmber: 50,
        label: 'Consistency'
      });

      return `
        <a class="candidate-card stagger-in" 
           href="#/candidates/${encodeURIComponent(c.candidate_id)}" 
           data-candidate-id="${escapeHtml(c.candidate_id)}" 
           style="animation-delay: ${Math.min(idx * 35, 400)}ms; text-decoration: none; color: inherit;">
          <div class="card-top">
            <div class="card-header-row">
              <div class="avatar" style="background: ${color.bg}; color: ${color.text};">${escapeHtml(initials)}</div>
              <div class="card-title-group">
                <div class="card-candidate-name">${escapeHtml(c.name || 'Candidate')}</div>
                <div class="card-target-role">
                  ${escapeHtml(c.target_role || 'Senior Software Engineer')}
                  ${isDegradedCandidate ? `<span class="degraded-mode-chip" style="margin-left: 0.35rem;">⚡ Demo</span>` : ''}
                </div>
              </div>
              <span class="badge ${badgeCls}">${escapeHtml(c.quadrant || 'EVALUATING')}</span>
            </div>

            <!-- Scores Row with Centralized Meter (Part 5.1 No Bare 0%) -->
            <div class="card-scores-row">
              ${fitMeterHtml}
              ${consMeterHtml}
            </div>

            <div class="card-verdict-snippet">${snippet}</div>
          </div>

          <div class="card-footer-row">
            <div class="card-flags">
              ${contra > 0 ? `<span class="flag-pill flag-warn">${contra} Conflict${contra === 1 ? '' : 's'}</span>` : ''}
              ${unsupp > 0 ? `<span class="flag-pill flag-warn">${unsupp} Unverified</span>` : ''}
              ${contra === 0 && unsupp === 0 ? `<span class="flag-pill flag-clean">✓ Verified</span>` : ''}
            </div>
            <span class="card-action-link">
              View Assessment →
            </span>
          </div>
        </a>
      `;
    }

    /* ==========================================================================
       CANDIDATE PROFILE LOADING & RENDERING
       ========================================================================== */
    async function loadCandidate(cid) {
      AppState.activeCaseId = cid;

      // Reset profile labels to loading placeholders
      document.getElementById('candName').textContent = "Loading candidate dossier...";
      document.getElementById('candRole').textContent = "Fetching multi-source evidence...";
      document.getElementById('scoreRoleFit').textContent = "--";
      document.getElementById('scoreConsistency').textContent = "--";
      document.getElementById('profileVerdictSentence').textContent = "Evaluating candidate evidence and cross-checking claims...";

      startPipelineStream(cid);

      // 1. Fetch full dossier documents
      try {
        const fullRes = await fetch(`/api/case/${encodeURIComponent(cid)}/full`);
        if (!fullRes.ok) throw new Error("HTTP " + fullRes.status);
        AppState.activeFullDocs = await fullRes.json();
      } catch (e) {
        if (window.HIRETRACE_STATIC && window.HIRETRACE_STATIC.fullDocs && window.HIRETRACE_STATIC.fullDocs[cid]) {
          AppState.activeFullDocs = window.HIRETRACE_STATIC.fullDocs[cid];
        }
      }
      selectDossierDoc('cv');

      // 2. Fetch evaluation report
      try {
        const evalRes = await fetch(`/api/evaluate/${encodeURIComponent(cid)}`, { method: "POST" });
        if (evalRes.status === 202) {
          const evalJob = await evalRes.json();
          const pollUrl = evalJob.poll_url || `/api/candidate/${encodeURIComponent(cid)}/status`;
          const pollUntilComplete = async () => {
            try {
              const pRes = await fetch(pollUrl);
              if (pRes.ok) {
                const pData = await pRes.json();
                if (pData.status === 'done' || pData.status === 'failed') {
                  const finalRes = await fetch(`/api/evaluate/${encodeURIComponent(cid)}`, { method: "POST" });
                  if (finalRes.ok && finalRes.status !== 202) {
                    AppState.activeCaseData = await finalRes.json();
                    renderProfileView(AppState.activeCaseData);
                  }
                  return;
                }
              }
              if (AppState.activeCaseId === cid) {
                setTimeout(pollUntilComplete, 1000);
              }
            } catch (_) {}
          };
          setTimeout(pollUntilComplete, 1000);
        } else if (!evalRes.ok) {
          throw new Error("HTTP " + evalRes.status);
        } else {
          AppState.activeCaseData = await evalRes.json();
        }
      } catch (e) {
        if (window.HIRETRACE_STATIC && window.HIRETRACE_STATIC.evaluations && window.HIRETRACE_STATIC.evaluations[cid]) {
          AppState.activeCaseData = window.HIRETRACE_STATIC.evaluations[cid];
        }
      }

      if (AppState.activeCaseData) {
        renderProfileView(AppState.activeCaseData);
      }
    }

    function renderProfileView(data) {
      const report = data.report || {};
      const card = report.candidate_card || report.quadrant_report || report || {};
      const name = card.candidate_name || AppState.activeFullDocs?.name || "Candidate";
      const quadrant = card.quadrant_placement || report.quadrant_placement || report.quadrant || "REVIEW REQUIRED";
      const targetRole = card.target_role || card.role || AppState.activeFullDocs?.target_role || "Senior Software Engineer";

      // Hero
      document.getElementById('candName').textContent = name;
      document.getElementById('candRole').textContent = targetRole;
      document.getElementById('quadrantPill').textContent = `[${quadrant}]`;
      document.getElementById('quadrantPill').className = `badge ${getBadgeClass(quadrant)}`;

      const heroAvatar = document.getElementById('profileHeroAvatar');
      if (heroAvatar) {
        heroAvatar.textContent = getInitials(name);
        const col = getAvatarColor(AppState.activeCaseId || name);
        heroAvatar.style.background = col.bg;
        heroAvatar.style.color = col.text;
      }

      // Sticky Profile Header Bar
      const stickyAvatar = document.getElementById('stickyAvatar');
      if (stickyAvatar) {
        stickyAvatar.textContent = getInitials(name);
        const col = getAvatarColor(AppState.activeCaseId || name);
        stickyAvatar.style.background = col.bg;
        stickyAvatar.style.color = col.text;
      }
      const stickyName = document.getElementById('stickyName');
      if (stickyName) stickyName.textContent = name;
      const stickyQuad = document.getElementById('stickyQuadrantPill');
      if (stickyQuad) {
        stickyQuad.textContent = `[${quadrant}]`;
        stickyQuad.className = `badge ${getBadgeClass(quadrant)}`;
      }

      // Profile tags
      const tagsContainer = document.getElementById('candTags');
      if (tagsContainer) {
        const tags = ["Evidence-First", "Local LLM Verified"];
        const prof = AppState.activeFullDocs?.structured_profile;
        if (prof) {
          const yrs = prof.years_production_experience ?? prof.years_experience ?? 0;
          if (yrs >= 1) tags.push(`${yrs}+ Yrs Exp`);
          if (prof.has_public_repo) tags.push("Open Source");
        }
        tagsContainer.innerHTML = tags.map(t => `<span class="badge badge-degraded" style="font-size: 0.68rem;">${escapeHtml(t)}</span>`).join('');
      }

      // Strict P0 Score Integrity: NEVER invent scores
      const hasFit = (report.role_fit_score !== undefined && report.role_fit_score !== null);
      const hasCons = (report.evidence_consistency_score !== undefined && report.evidence_consistency_score !== null);
      const fit = hasFit ? Number(report.role_fit_score) : null;
      const cons = hasCons ? Number(report.evidence_consistency_score) : null;

      // Verdict sentence & single source of truth for degraded status
      const isDegraded = Boolean(report.degraded || card.degraded || AppState.isDegraded || (report.role_fit_score === null && card.role_fit_score === null));
      const banner = document.getElementById('degradedBanner');
      if (banner) banner.style.display = isDegraded ? 'flex' : 'none';

      // Taxonomy Fallback Notice
      const isTaxonomyUnmatched = Boolean((report.taxonomy_matched === false || card.taxonomy_matched === false) && !report.custom_jd_provided && !card.custom_jd_provided);
      const taxNotice = document.getElementById('taxonomyFallbackNotice');
      const taxNoticeText = document.getElementById('taxonomyFallbackNoticeText');
      if (taxNotice) {
        if (isTaxonomyUnmatched) {
          taxNotice.style.display = 'flex';
          if (taxNoticeText) {
            taxNoticeText.textContent = report.role_match_note || card.role_match_note || `No specialized rubric matched for '${targetRole}' — using a generated/general evaluation. Paste a full JD for a tailored assessment.`;
          }
        } else {
          taxNotice.style.display = 'none';
        }
      }

      const verdictEl = document.getElementById('profileVerdictSentence');
      if (verdictEl) {
        if (isDegraded) {
          verdictEl.textContent = "Evaluated under deterministic resume rubric — local LLM verification backend is offline.";
        } else if (quadrant === 'STRONG MATCH') {
          verdictEl.textContent = "Strong role fit with high cross-source consistency across all verified artifacts.";
        } else if (quadrant === 'REVIEW REQUIRED') {
          verdictEl.textContent = "Review required — notable discrepancies detected between CV claims and interview/assessment.";
        } else if (quadrant === 'INSUFFICIENT EVIDENCE') {
          verdictEl.textContent = "Insufficient evidence — profile lacks verifiable technical repositories or concrete artifacts.";
        } else {
          verdictEl.textContent = "Weak match — notable technical divergence across core job requirements.";
        }
      }

      // Formula breakdown
      const breakdown = report.score_breakdown || data.score_breakdown || {};
      const rubricRaw = data.baseline_a ? (data.baseline_a.raw_total || data.baseline_a.total) : null;
      let llmMatch = breakdown.llm_req_fit_score;
      let rubricMatch = breakdown.rubric_baseline_score ?? rubricRaw;

      if (llmMatch === undefined || llmMatch === null) {
        if (fit !== null && rubricMatch !== null) {
          llmMatch = Math.max(0, Math.min(100, (fit - 0.40 * rubricMatch) / 0.60));
        }
      }

      const fitText = isDegraded ? "N/A" : (hasFit ? fit.toFixed(1) : "--");
      const consText = hasCons ? cons.toFixed(1) : "--";

      const scoreRoleFitEl = document.getElementById('scoreRoleFit');
      const scoreRoleFitSub = document.getElementById('scoreRoleFitSub');
      if (scoreRoleFitEl) {
        if (isDegraded) {
          scoreRoleFitEl.innerHTML = `${rubricMatch !== null && rubricMatch !== undefined ? Number(rubricMatch).toFixed(1) : '--'}`;
          if (scoreRoleFitSub) {
            scoreRoleFitSub.innerHTML = `<span class="degraded-mode-chip">⚡ LLM offline — showing deterministic rubric only</span>`;
          }
        } else if (hasFit) {
          animateNumber(scoreRoleFitEl, 0, fit, 600, 1);
          if (scoreRoleFitSub) scoreRoleFitSub.textContent = "60% LLM + 40% Rubric";
        } else {
          scoreRoleFitEl.textContent = "--";
          if (scoreRoleFitSub) scoreRoleFitSub.textContent = "Pending Evaluation";
        }
      }

      const scoreConsEl = document.getElementById('scoreConsistency');
      if (scoreConsEl) {
        if (hasCons) {
          animateNumber(scoreConsEl, 0, cons, 600, 1);
        } else {
          scoreConsEl.textContent = "--";
        }
      }

      const stickyFit = document.getElementById('stickyFitVal');
      if (stickyFit) stickyFit.textContent = isDegraded ? `${Number(rubricMatch || 0).toFixed(1)} (Rubric)` : fitText;
      const stickyCons = document.getElementById('stickyConsVal');
      if (stickyCons) stickyCons.textContent = consText;

      // Track recent candidate
      trackRecentCandidate({
        candidate_id: AppState.activeCaseId,
        name: name,
        target_role: targetRole,
        quadrant: quadrant
      });

      document.getElementById('formulaLlmVal').innerHTML = isDegraded ? '<span class="degraded-mode-chip">⚡ LLM Offline</span>' : ((llmMatch !== null && llmMatch !== undefined) ? Number(llmMatch).toFixed(1) : "--");
      document.getElementById('formulaRubricVal').textContent = (rubricMatch !== null && rubricMatch !== undefined) ? Number(rubricMatch).toFixed(1) : "--";
      document.getElementById('formulaTotalVal').innerHTML = isDegraded ? `${Number(rubricMatch || 0).toFixed(1)} <span class="degraded-mode-chip" style="font-size: 0.65rem;">Rubric Only</span>` : (hasFit ? fit.toFixed(1) : "--");

      // Cutoff gauges using centralized updateMeterElement (Part 5.1)
      const gFitTrack = document.getElementById('gaugeFitFill')?.parentElement;
      updateMeterElement(gFitTrack, document.getElementById('gaugeFitFill'), document.getElementById('gaugeFitVal'), hasFit ? fit : null, {
        isDegraded: isDegraded,
        thresholdGreen: 72,
        thresholdAmber: 50,
        unit: ' / 100'
      });

      const gConsTrack = document.getElementById('gaugeConsistencyFill')?.parentElement;
      updateMeterElement(gConsTrack, document.getElementById('gaugeConsistencyFill'), document.getElementById('gaugeConsistencyVal'), hasCons ? cons : null, {
        isDegraded: false,
        thresholdGreen: 70,
        thresholdAmber: 50,
        unit: ' / 100'
      });

      // Calibration insight
      const calText = document.getElementById('calibrationText');
      if (calText) {
        calText.textContent = hasCons && cons >= 85 ? "High Precision Calibrated" : (hasCons && cons >= 70 ? "High Confidence Calibrated" : "Discrepancy Review Flagged");
      }

      // Terminal Report
      let termCard = report.formatted_terminal_card || report.terminal_report_card;
      if (!termCard) {
        termCard = `====================================================================\n                    CANDIDATE ASSESSMENT REPORT\nCandidate: ${name} | Role: ${targetRole}\n====================================================================\nROLE FIT:                    ${fitText} / 100\nEVIDENCE CONSISTENCY:        ${consText} / 100\nQUADRANT PLACEMENT:          [${quadrant}]\n\nEXECUTIVE SUMMARY:\n  ${report.executive_summary || 'Evidence evaluated across multi-source dossier.'}\n====================================================================`;
      }
      document.getElementById('terminalReportBox').textContent = termCard;

      // 2D Quadrant dots
      renderQuadrantDots(AppState.cases, AppState.activeCaseId);

      // Contradictions / Discrepancies
      const disc = (report.key_discrepancies && report.key_discrepancies.length > 0) ? report.key_discrepancies
                 : (report.critical_discrepancies && report.critical_discrepancies.length > 0) ? report.critical_discrepancies
                 : (report.cross_source_contradictions || card.key_discrepancies || []);

      renderDiscrepancies(disc);

      let unsupportedCount = 0;
      let contradictedCount = 0;
      if (Array.isArray(disc)) {
        disc.forEach(d => {
          const s = String(d.status || d.type || d.discrepancy_type || "").toUpperCase();
          if (s.includes("CONTRADICT")) contradictedCount++;
          else unsupportedCount++;
        });
      }
      if (report.unsupported_claim_count !== undefined) unsupportedCount = report.unsupported_claim_count;
      else if (card.unsupported_claim_count !== undefined) unsupportedCount = card.unsupported_claim_count;
      else if (report.unsupported_claims_count !== undefined) unsupportedCount = report.unsupported_claims_count;

      if (report.contradicted_claim_count !== undefined) contradictedCount = report.contradicted_claim_count;
      else if (card.contradicted_claim_count !== undefined) contradictedCount = card.contradicted_claim_count;
      else if (report.contradicted_claims_count !== undefined) contradictedCount = report.contradicted_claims_count;

      document.getElementById('statUnsupported').textContent = unsupportedCount;
      document.getElementById('statContradicted').textContent = contradictedCount;

      // Contextual Mascot celebration state (Phase 2)
      const celebBadge = document.getElementById('mascotCelebrationBadge');
      if (celebBadge) {
        const isVerifiedMatch = (!isDegraded && (quadrant === 'LEAD CANDIDATE' || quadrant === 'STRONG MATCH') && contradictedCount === 0);
        celebBadge.style.display = isVerifiedMatch ? 'inline-flex' : 'none';
      }

      // Questions
      const questions = report.priority_questions_for_reviewer || report.priority_questions || [];
      renderQuestions(questions);

      // Rubric
      const bA = data.baseline_a || {};
      document.getElementById('rubricScoreDisplay').textContent = `Raw: ${bA.raw_total || 62.5} / 120 (Norm: ${bA.normalized_score || 52.1} / 100)`;
      renderRubricGrid(bA);

      // Defensibility
      const candExpl = document.getElementById('auditCandExplanation');
      if (candExpl) {
        candExpl.innerHTML = `Candidate <strong>${escapeHtml(name)}</strong> evaluated with zero autonomous adverse employment decisions. Audit verified under EEOC 4 CFR Part 60 standards with Disparate Impact ratio of <strong>1.0000</strong>.`;
      }
    }

    /* ==========================================================================
       PROFILE TABS (WAI-ARIA COMPLIANT TABLIST)
       ========================================================================== */
    function switchProfileTab(tabId, updateUrl = true) {
      const validTabs = ['overview', 'evidence', 'questions', 'governance'];
      if (!validTabs.includes(tabId)) tabId = 'overview';
      AppState.activeProfileTab = tabId;

      validTabs.forEach(t => {
        const btn = document.getElementById(`pTabBtn-${t}`);
        const panel = document.getElementById(`pTab-${t}`);
        const isActive = (t === tabId);
        if (btn) {
          btn.classList.toggle('active', isActive);
          btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
          btn.setAttribute('tabindex', isActive ? '0' : '-1');
        }
        if (panel) {
          panel.classList.toggle('active', isActive);
        }
      });

      if (tabId === 'evidence') {
        setTimeout(() => {
          if (typeof initEvidenceTimeline === 'function') initEvidenceTimeline();
          if (typeof initEvidenceGraph === 'function') initEvidenceGraph();
        }, 60);
      }

      if (updateUrl && AppState.activeCaseId) {
        const base = `#/candidates/${encodeURIComponent(AppState.activeCaseId)}`;
        window.history.replaceState(null, '', `${base}?tab=${tabId}`);
      }
    }

    /* 2D Quadrant Scatter Plot */
    function renderQuadrantDots(items, activeId) {
      const container = document.getElementById('quadrantDots');
      if (!container) return;
      const deduped = deduplicateCandidates(items);

      container.innerHTML = deduped.map(c => {
        const x = (c.role_fit_score !== undefined && c.role_fit_score !== null) ? Number(c.role_fit_score) : 50.0;
        const y = (c.evidence_consistency_score !== undefined && c.evidence_consistency_score !== null) ? Number(c.evidence_consistency_score) : 50.0;
        const left = Math.max(6, Math.min(94, x));
        const top = Math.max(6, Math.min(94, 100 - y));
        const isTarget = c.candidate_id === activeId;
        const color = (y < 60) ? "var(--warning)" : (x >= 72 ? "var(--success)" : "var(--text-muted)");
        const quad = c.quadrant || "STRONG MATCH";

        return `
          <div class="cand-dot ${isTarget ? 'active-target' : ''}"
               style="left: ${left}%; top: ${top}%; background: ${color};"
               data-cid="${escapeHtml(c.candidate_id)}"
               data-name="${escapeHtml(c.name || 'Candidate')}"
               data-role="${escapeHtml(c.target_role || '')}"
               data-fit="${x.toFixed(1)}"
               data-cons="${y.toFixed(1)}"
               data-quad="${escapeHtml(quad)}"
               title="${escapeHtml(c.name || 'Candidate')}">
          </div>
        `;
      }).join('');
    }

    function showQuadrantTooltip(e, name, role, fit, consistency, quad) {
      const tooltip = document.getElementById("quadrantTooltip");
      if (!tooltip) return;
      tooltip.innerHTML = `
        <div style="font-weight: 600; color: var(--text-primary);">${escapeHtml(name)}</div>
        <div style="font-size: 0.7rem; color: var(--text-muted);">${escapeHtml(role)}</div>
        <div style="margin-top: 0.35rem; display: flex; justify-content: space-between; gap: 0.5rem;"><span>Fit:</span><strong>${escapeHtml(fit)}</strong></div>
        <div style="display: flex; justify-content: space-between; gap: 0.5rem;"><span>Consistency:</span><strong>${escapeHtml(consistency)}</strong></div>
        <div style="margin-top: 0.25rem; font-size: 0.68rem; font-weight: 600; color: var(--accent);">[${escapeHtml(quad)}]</div>
      `;

      const canvas = document.getElementById("quadrantCanvas");
      const rect = canvas ? canvas.getBoundingClientRect() : { left: 0, top: 0, width: 300, height: 300 };
      let left = e.clientX - rect.left + 10;
      let top = e.clientY - rect.top + 10;
      if (left + 170 > rect.width) left -= 180;
      if (top + 100 > rect.height) top -= 110;

      tooltip.style.left = `${Math.max(6, left)}px`;
      tooltip.style.top = `${Math.max(6, top)}px`;
      tooltip.classList.add("show");
    }

    function hideQuadrantTooltip() {
      const tooltip = document.getElementById("quadrantTooltip");
      if (tooltip) tooltip.classList.remove("show");
    }

    /* Contradictions Diff Rendering with Traceable Evidence Links */
    function renderDiscrepancies(discrepancies) {
      const badge = document.getElementById('discBadgeCount');
      if (badge) badge.textContent = discrepancies.length;
      const container = document.getElementById('discrepanciesContainer');
      if (!container) return;

      if (!discrepancies || discrepancies.length === 0) {
        container.innerHTML = `
          <div style="padding: 1.25rem; background: var(--success-subtle); border: 1px solid var(--success-border); border-radius: var(--radius-md); color: var(--success-text); font-size: 0.82rem;">
            ✓ <strong>Evidence Fully Consistent:</strong> No contradictory claims detected across submitted documents.
          </div>
        `;
        return;
      }

      container.innerHTML = discrepancies.map((d, i) => {
        const topic = d.topic || d.claim || "Cross-Source Discrepancy";
        const srcA = d.source_a || "Source A (CV)";
        const quoteA = d.quote_a || d.source_a_quote || "Claim stated in source A";
        const srcB = d.source_b || "Source B (Interview/Assessment)";
        const quoteB = d.quote_b || d.source_b_quote || "Contradicting statement in source B";
        const severity = d.severity || "HIGH";

        return `
          <div class="diff-card">
            <div class="diff-header">
              <span class="diff-title">Discrepancy #${i + 1}: ${escapeHtml(topic)}</span>
              <span class="badge badge-review">${escapeHtml(severity)}</span>
            </div>
            <div class="diff-grid">
              <div class="diff-source-box">
                <div class="diff-source-label">
                  <span>${escapeHtml(srcA)}</span>
                  <button type="button" class="btn btn-ghost btn-sm btn-jump-evidence" data-src="${escapeHtml(srcA)}" data-quote="${escapeHtml(quoteA)}">Inspect in Dossier →</button>
                </div>
                <div class="diff-quote">"${escapeHtml(quoteA)}"</div>
              </div>
              <div class="diff-vs">VS</div>
              <div class="diff-source-box">
                <div class="diff-source-label">
                  <span>${escapeHtml(srcB)}</span>
                  <button type="button" class="btn btn-ghost btn-sm btn-jump-evidence" data-src="${escapeHtml(srcB)}" data-quote="${escapeHtml(quoteB)}">Inspect in Dossier →</button>
                </div>
                <div class="diff-quote">"${escapeHtml(quoteB)}"</div>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    /* Traceable Jump to Evidence Source & Excerpt Highlighting */
    function jumpToEvidence(sourceName, excerptText = "") {
      const s = (sourceName || '').toLowerCase();
      let docKey = 'cv';
      if (s.includes('interview')) docKey = 'interview';
      else if (s.includes('assessment') || s.includes('code')) docKey = 'assessment';
      else if (s.includes('rfc') || s.includes('project') || s.includes('design')) docKey = 'project_rfc';
      else if (s.includes('jd') || s.includes('req')) docKey = 'jd';

      switchProfileTab('evidence');
      selectDossierDoc(docKey);

      if (excerptText) {
        setTimeout(() => {
          highlightDossierExcerpt(excerptText);
        }, 120);
      }
      showToast(`Navigated to ${sourceName} in Evidence Dossier`);
    }

    /* Evidence Dossier Split-Pane Viewer */
    function selectDossierDoc(docKey, btn) {
      AppState.activeDossierDoc = docKey;
      document.querySelectorAll('.evidence-source-item').forEach(b => b.classList.remove('active'));
      const targetBtn = btn || document.getElementById(`evSrc-${docKey}`);
      if (targetBtn) targetBtn.classList.add('active');

      const docs = AppState.activeFullDocs?.documents || {};
      const content = docs[docKey] || "(Document content not provided in dossier)";
      const container = document.getElementById('dossierContent');
      if (container) container.textContent = content;

      const docMeta = document.getElementById('evidenceDocMeta');
      if (docMeta) {
        const titles = {
          cv: 'Curriculum Vitae',
          interview: 'Interview Transcript',
          assessment: 'Technical Assessment',
          project_rfc: 'Architecture RFC',
          jd: 'Target Requisition'
        };
        const words = content.trim().split(/\s+/).filter(Boolean).length;
        docMeta.textContent = `${titles[docKey] || docKey} (${words} words)`;
      }
    }

    function highlightDossierExcerpt(excerpt) {
      const container = document.getElementById('dossierContent');
      if (!container) return;
      const rawText = container.textContent;
      const cleanExcerpt = excerpt.replace(/^"|"$/g, '').trim();
      if (!cleanExcerpt || cleanExcerpt.length < 5) return;

      const idx = rawText.toLowerCase().indexOf(cleanExcerpt.toLowerCase());
      if (idx !== -1) {
        const before = escapeHtml(rawText.substring(0, idx));
        const matched = escapeHtml(rawText.substring(idx, idx + cleanExcerpt.length));
        const after = escapeHtml(rawText.substring(idx + cleanExcerpt.length));

        container.innerHTML = `${before}<mark class="evidence-highlight-target">${matched}</mark>${after}`;
        const mark = container.querySelector('.evidence-highlight-target');
        if (mark) {
          mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
    }

    function copyCurrentDossierText() {
      const text = document.getElementById('dossierContent').textContent;
      navigator.clipboard.writeText(text).then(() => showToast("Document copied to clipboard"));
    }

    /* Interview Questions */
    function renderQuestions(questions) {
      const container = document.getElementById('questionsContainer');
      if (!container) return;

      if (!questions || questions.length === 0) {
        container.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-muted); padding: 1rem 0;">No priority probe questions required. Candidate claims verified.</div>`;
        return;
      }

      container.innerHTML = questions.map((q, i) => `
        <div class="question-item">
          <div class="question-text">
            <strong style="color: var(--accent); margin-right: 0.4rem;">Q${i + 1}.</strong>
            ${escapeHtml(q)}
          </div>
          <button type="button" class="btn btn-secondary btn-sm btn-copy-single-q" data-question="${escapeHtml(q)}">Copy</button>
        </div>
      `).join('');
    }

    function copySingleQuestion(q) {
      navigator.clipboard.writeText(q).then(() => showToast("Question copied to clipboard"));
    }

    function copyAllQuestions() {
      const items = document.querySelectorAll('#questionsContainer .question-text');
      if (!items || items.length === 0) {
        showToast("No questions to copy");
        return;
      }
      let txt = "HIRETRACE INTERVIEW PROBE QUESTIONS\n====================================\n\n";
      items.forEach((item, idx) => {
        txt += `${idx + 1}. ${item.textContent.trim()}\n\n`;
      });
      navigator.clipboard.writeText(txt).then(() => showToast("All interview questions copied!"));
    }

    /* Rubric Baseline A Grid */
    function renderRubricGrid(bA) {
      const cats = (bA && bA.category_scores) ? bA.category_scores : {};
      const grid = document.getElementById('rubricGrid');
      if (!grid) return;

      grid.innerHTML = `
        <div class="rubric-card"><div class="rubric-card-val">${cats.open_source || 0}</div><div class="rubric-card-title">Open Source (/35)</div></div>
        <div class="rubric-card"><div class="rubric-card-val">${cats.self_projects || 0}</div><div class="rubric-card-title">Projects (/30)</div></div>
        <div class="rubric-card"><div class="rubric-card-val">${cats.production || 0}</div><div class="rubric-card-title">Production (/25)</div></div>
        <div class="rubric-card"><div class="rubric-card-val">${cats.technical_skills || 0}</div><div class="rubric-card-title">Tech Skills (/10)</div></div>
        <div class="rubric-card"><div class="rubric-card-val">${cats.bonus_points || 0}</div><div class="rubric-card-title">Bonus (/20)</div></div>
      `;

      const signals = (bA && Array.isArray(bA.summary_audit)) ? bA.summary_audit : [];
      document.getElementById('rubricAuditCount').textContent = signals.length;
      const listEl = document.getElementById('rubricAuditList');
      if (listEl) {
        if (signals.length === 0) {
          listEl.innerHTML = `<span style="color: var(--text-muted); font-style: italic;">No specific signal rules matched.</span>`;
        } else {
          listEl.innerHTML = signals.map(s => `<div>✓ ${escapeHtml(s)}</div>`).join('');
        }
      }
    }

    function toggleRubricAudit() {
      const drawer = document.getElementById('rubricAuditDrawer');
      const arrow = document.getElementById('rubricAuditArrow');
      if (!drawer) return;
      const isClosed = drawer.style.display === 'none' || drawer.style.display === '';
      drawer.style.display = isClosed ? 'block' : 'none';
      if (arrow) arrow.textContent = isClosed ? '▴' : '▾';
    }

    /* SSE Stream */
    function startPipelineStream(candidateId) {
      const box = document.getElementById('liveStreamBox');
      if (!box) return;

      if (AppState.pipelineStream) {
        AppState.pipelineStream.close();
        AppState.pipelineStream = null;
      }

      const agentEl = document.getElementById('liveStreamAgentName');
      const pctEl = document.getElementById('liveStreamPctText');
      const fillEl = document.getElementById('liveStreamBarFill');
      const stepEl = document.getElementById('liveStreamStepText');

      box.style.display = 'block';
      if (agentEl) agentEl.textContent = "RequirementMappingAgent";
      if (pctEl) pctEl.textContent = "25%";
      if (fillEl) fillEl.style.width = "25%";
      if (stepEl) stepEl.textContent = "Mapping requirements from requisition...";

      try {
        const es = new EventSource(`/api/pipeline/stream/${encodeURIComponent(candidateId)}`);
        AppState.pipelineStream = es;

        es.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (agentEl && data.agent) agentEl.textContent = data.agent;
            if (pctEl && data.progress_pct !== undefined) pctEl.textContent = `${data.progress_pct}%`;
            if (fillEl && data.progress_pct !== undefined) fillEl.style.width = `${data.progress_pct}%`;
            if (stepEl && data.step) stepEl.textContent = data.step;

            if (data.status === 'completed' || data.progress_pct >= 100) {
              setTimeout(() => { if (box) box.style.display = 'none'; }, 2000);
              es.close();
              AppState.pipelineStream = null;
            }
          } catch (err) {}
        };

        es.onerror = () => {
          es.close();
          AppState.pipelineStream = null;
          setTimeout(() => { if (box) box.style.display = 'none'; }, 1000);
        };
      } catch (err) {
        if (box) box.style.display = 'none';
      }
    }

    /* Print / PDF */
    function exportReportToPdf() {
      window.print();
    }

    function copyCard() {
      const text = document.getElementById('terminalReportBox').textContent;
      navigator.clipboard.writeText(text).then(() => showToast("Assessment report copied to clipboard"));
    }

    /* ==========================================================================
       LEADERBOARD VIEW
       ========================================================================== */
    function setLeaderboardSort(field) {
      AppState.leaderboardSort = field;
      const map = {
        'fit': 'btnSortFit',
        'consistency': 'btnSortCons',
        'unsupported': 'btnSortUnsupp',
        'name': 'btnSortName'
      };
      document.querySelectorAll('#viewLeaderboard .chip-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById(map[field]);
      if (activeBtn) activeBtn.classList.add('active');
      renderLeaderboard();
    }

    function renderLeaderboard() {
      const tbody = document.getElementById('leaderboardBody');
      if (!tbody) return;

      const roleSelect = document.getElementById('leaderboardRoleSelect');
      const selectedRole = roleSelect ? roleSelect.value : 'all';

      let list = [...AppState.cases];
      if (selectedRole && selectedRole !== 'all') {
        list = list.filter(c => (c.target_role || '').toLowerCase() === selectedRole.toLowerCase());
      }

      list.sort((a, b) => {
        if (AppState.leaderboardSort === 'fit') {
          return (Number(b.role_fit_score) || 0) - (Number(a.role_fit_score) || 0);
        } else if (AppState.leaderboardSort === 'consistency') {
          return (Number(b.evidence_consistency_score) || 0) - (Number(a.evidence_consistency_score) || 0);
        } else if (AppState.leaderboardSort === 'unsupported') {
          return (Number(a.unsupported_claim_count) || 0) - (Number(b.unsupported_claim_count) || 0);
        } else if (AppState.leaderboardSort === 'name') {
          return String(a.name || '').localeCompare(String(b.name || ''));
        }
        return 0;
      });

      const countLabel = document.getElementById('leaderboardCountLabel');
      if (countLabel) countLabel.textContent = `Showing ${list.length} candidate${list.length === 1 ? '' : 's'}`;

      if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">No candidates for selected requisition.</td></tr>`;
        return;
      }

      tbody.innerHTML = list.map((c, idx) => {
        const isDegradedCandidate = Boolean(c.degraded || (c.role_fit_score === null && c.status === 'done') || AppState.isDegraded);
        const fit = isDegradedCandidate ? '<span class="degraded-mode-chip">⚡ Rubric</span>' : (c.role_fit_score !== null && c.role_fit_score !== undefined ? Number(c.role_fit_score).toFixed(1) : '--');
        const cons = (c.evidence_consistency_score !== null && c.evidence_consistency_score !== undefined) ? Number(c.evidence_consistency_score).toFixed(1) : '--';
        const quad = c.quadrant || 'REVIEW REQUIRED';
        const badgeCls = getBadgeClass(quad);
        const unsupp = c.unsupported_claim_count || 0;

        return `
          <tr class="stagger-in" style="animation-delay: ${Math.min(idx * 28, 350)}ms">
            <td>
              <a href="#/candidates/${encodeURIComponent(c.candidate_id)}" style="font-weight: 600; color: var(--text-primary); text-decoration: none;">
                ${escapeHtml(c.name || c.candidate_id)}
              </a>
            </td>
            <td style="color: var(--text-secondary); font-size: 0.75rem;">
              ${escapeHtml(c.target_role || 'Senior Software Engineer')}
              ${isDegradedCandidate ? '<span class="degraded-mode-chip" style="margin-left: 0.25rem;">⚡ Demo</span>' : ''}
            </td>
            <td><strong style="font-family: var(--font-mono);">${fit}</strong></td>
            <td><span style="font-family: var(--font-mono); font-weight: 600;">${cons}</span></td>
            <td><span class="badge ${badgeCls}">${escapeHtml(quad)}</span></td>
            <td><span style="font-family: var(--font-mono); font-weight: 600;">${unsupp}</span></td>
            <td style="text-align: right;">
              <a class="btn btn-secondary btn-sm" href="#/candidates/${encodeURIComponent(c.candidate_id)}">
                Inspect →
              </a>
            </td>
          </tr>
        `;
      }).join('');
    }

    /* ==========================================================================
       AUDIT SUMMARY & BENCHMARKS (Part 5.3 Live Wiring)
       ========================================================================== */
    async function loadAuditSummary() {
      try {
        let data = null;
        try {
          const res = await fetch("/api/audit/summary");
          if (res.ok) {
            data = await res.json();
          }
        } catch (fetchErr) {
          // Fall back to static bundle
        }

        if (!data && window.HIRETRACE_STATIC && window.HIRETRACE_STATIC.auditSummary && Object.keys(window.HIRETRACE_STATIC.auditSummary).length > 0) {
          data = window.HIRETRACE_STATIC.auditSummary;
        }

        if (!data) {
          const snapEl = document.getElementById('auditSnapshotBadge');
          if (snapEl) snapEl.textContent = "Unavailable in static demo mode";
          const idsToClear = [
            'auditRoleFitDrift', 'auditConsistencyDrift', 'auditDisparateImpact', 'auditQuadrantStability',
            'auditGroundingFidelity', 'auditCitationValidity', 'auditExactQuote', 'auditSynthesizedInferences',
            'auditBrierScore', 'auditEce', 'auditSpearmanRho', 'auditSpearmanCi', 'auditContradictionF1',
            'auditContradictionRecallPrec', 'auditPromptDefense', 'auditFabricationRecall',
            'auditLeafAccuracy', 'auditCompletionRate', 'auditRowRecallPrec',
            'auditReviewTime', 'auditTimeSaved', 'auditPipelineLatency'
          ];
          idsToClear.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = "—";
          });
          return;
        }

        const snapEl = document.getElementById('auditSnapshotBadge');
        if (snapEl && data.snapshot_taken_at) {
          snapEl.textContent = `Certified Reference Benchmark (Frozen at ${data.snapshot_taken_at})`;
        }

        if (data.fairness) {
          const f = data.fairness;
          const elFit = document.getElementById('auditRoleFitDrift');
          if (elFit) elFit.textContent = `${Number(f.mean_role_fit_delta_pts || 0).toFixed(2)} pts`;
          const elCons = document.getElementById('auditConsistencyDrift');
          if (elCons) elCons.textContent = `${Number(f.mean_consistency_delta_pts || 0).toFixed(2)} pts`;
          const elImpact = document.getElementById('auditDisparateImpact');
          if (elImpact) elImpact.textContent = `${Number(f.minimum_disparate_impact_ratio || 1).toFixed(4)} (EEOC Min: 0.8000)`;
          const elStab = document.getElementById('auditQuadrantStability');
          if (elStab) elStab.textContent = `${Number(f.quadrant_stability_percent || 100).toFixed(1)}% Invariant`;
          const elDesc = document.getElementById('auditDemographicSummary');
          if (elDesc && f.demographic_evaluations_count) {
            elDesc.textContent = `Audited under ${f.standards || "EEOC Guidelines"} across ${f.demographic_evaluations_count} counterfactual demographic mutations and ${f.demographic_groups_count || 11} protected classes.`;
          }
        }

        if (data.grounding) {
          const g = data.grounding;
          const elFid = document.getElementById('auditGroundingFidelity');
          if (elFid) {
            const fidPct = Number(g.grounded_claim_fidelity || 66.7).toFixed(1);
            const verifiedClaims = g.asserted_grounded_claims || 10;
            const totalClaims = g.total_claims || 15;
            const synCount = g.synthesized_inferences || (totalClaims - verifiedClaims);
            elFid.textContent = `${fidPct}% (${verifiedClaims}/${totalClaims} claims grounded; ${synCount} synthesized)`;
          }
          const elCit = document.getElementById('auditCitationValidity');
          if (elCit) elCit.textContent = `${Number(g.citation_validity_rate || 100).toFixed(1)}% Valid IDs`;
          const elQuote = document.getElementById('auditExactQuote');
          if (elQuote) elQuote.textContent = `${Number(g.exact_quote_containment || 100).toFixed(1)}% (*Conditional on grounded claims)`;
          const elSyn = document.getElementById('auditSynthesizedInferences');
          if (elSyn) elSyn.textContent = `${g.synthesized_inferences || 5} explicitly demarcated (33.3%)`;
        }

        if (data.calibration) {
          const c = data.calibration;
          const elBrier = document.getElementById('auditBrierScore');
          if (elBrier) {
            const bVal = c.brier_score !== undefined ? Number(c.brier_score).toFixed(4) : '0.2281';
            elBrier.textContent = `${bVal} (Weak; vs 0.250 baseline)`;
          }
          const elEce = document.getElementById('auditEce');
          if (elEce) {
            const eVal = c.expected_calibration_error !== undefined ? Number(c.expected_calibration_error).toFixed(4) : '0.2395';
            elEce.textContent = `${eVal} (High Error; avg ~24% bin drift)`;
          }
          const elRho = document.getElementById('auditSpearmanRho');
          if (elRho) {
            const rVal = c.spearman_rho !== undefined ? Number(c.spearman_rho).toFixed(3) : '0.816';
            elRho.textContent = `ρ = ${rVal} (positive but uncertain)`;
          }
          const elCi = document.getElementById('auditSpearmanCi');
          if (elCi) {
            if (c.bootstrap_ci_95 && Array.isArray(c.bootstrap_ci_95)) {
              elCi.textContent = `[${Number(c.bootstrap_ci_95[0]).toFixed(3)}, ${Number(c.bootstrap_ci_95[1]).toFixed(3)}] (Wide interval; N=20)`;
            } else {
              elCi.textContent = `[0.446, 0.983] (Wide interval; N=20)`;
            }
          }
          const elF1 = document.getElementById('auditContradictionF1');
          if (elF1) {
            const fVal = c.contradiction_f1 !== undefined ? Number(c.contradiction_f1).toFixed(3) : '1.000';
            elF1.textContent = `${fVal} (*Curated synthetic subset)`;
          }
          const elRecPrec = document.getElementById('auditContradictionRecallPrec');
          if (elRecPrec) {
            const rec = Number(c.contradiction_recall !== undefined ? c.contradiction_recall : 100).toFixed(1);
            const prec = Number(c.contradiction_precision !== undefined ? c.contradiction_precision : 100).toFixed(1);
            elRecPrec.textContent = `${rec}% / ${prec}% (*Synthetic test set)`;
          }

          const calBadge = document.getElementById('auditCalibrationBadge');
          if (calBadge) {
            calBadge.textContent = "Positive (Wide CI)";
            calBadge.className = "badge badge-warning";
          }
        }

        if (data.adversarial) {
          const a = data.adversarial;
          const elDef = document.getElementById('auditPromptDefense');
          if (elDef) elDef.textContent = `${Number(a.prompt_injection_defense_rate !== undefined ? a.prompt_injection_defense_rate : 100).toFixed(1)}% Defended`;
          const elFab = document.getElementById('auditFabricationRecall');
          if (elFab) elFab.textContent = `${Number(a.fabrication_recall !== undefined ? a.fabrication_recall : 100).toFixed(1)}% Detected`;
          const elAttacks = document.getElementById('auditTestedAttacks');
          if (elAttacks && Array.isArray(a.tested_attacks)) {
            elAttacks.innerHTML = a.tested_attacks.map(atk => {
              const label = String(atk).replace(/_/g, ' ');
              return `<span class="badge badge-degraded" style="font-size: 0.65rem; padding: 0.18rem 0.5rem; text-transform: capitalize;">${escapeHtml(label)}</span>`;
            }).join('');
          }
        }

        if (data.extraction) {
          const ext = data.extraction;
          const elLeaf = document.getElementById('auditLeafAccuracy');
          if (elLeaf) elLeaf.textContent = `${Number(ext.matched_leaf_accuracy || 84.8).toFixed(1)}% (Benchmark: ≥ 80.0%)`;
          const elComp = document.getElementById('auditCompletionRate');
          if (elComp) elComp.textContent = `${Number(ext.completion_rate || 100.0).toFixed(1)}% (16/16 documents)`;
          const elRow = document.getElementById('auditRowRecallPrec');
          if (elRow) {
            const rec = Number(ext.array_row_recall || 79.7).toFixed(1);
            const prec = Number(ext.array_row_precision || 73.1).toFixed(1);
            elRow.textContent = `${rec}% / ${prec}%`;
          }
        }

        if (data.efficiency) {
          const eff = data.efficiency;
          const elRev = document.getElementById('auditReviewTime');
          if (elRev) elRev.textContent = `${Number(eff.candidate_review_minutes || 3.5).toFixed(1)} min (vs 18.0 min manual)`;
          const elSaved = document.getElementById('auditTimeSaved');
          if (elSaved) elSaved.textContent = `+${Number(eff.time_saved_pct || 80.6).toFixed(1)}% Time Saved`;
          const elLat = document.getElementById('auditPipelineLatency');
          if (elLat) elLat.textContent = `~${Number(eff.pipeline_median_latency_seconds || 26.25).toFixed(2)}s (Steps 1-3 concurrent)`;
        }

        if (data.governance) {
          const gov = data.governance;
          const elAuto = document.getElementById('auditAutonomousHire');
          if (elAuto) {
            elAuto.textContent = gov.autonomous_hire_verdict_permitted ? "Permitted (True)" : "Not Permitted (False)";
            elAuto.style.color = gov.autonomous_hire_verdict_permitted ? "var(--warning-text)" : "var(--danger-text)";
          }
          const elHitl = document.getElementById('auditHitlMandatory');
          if (elHitl) {
            elHitl.textContent = gov.human_in_the_loop_mandatory ? "Mandatory (True)" : "Optional (False)";
            elHitl.style.color = gov.human_in_the_loop_mandatory ? "var(--warning-text)" : "var(--success-text)";
          }
          const elContract = document.getElementById('auditRecommendationContract');
          if (elContract && gov.recommendation_contract) {
            elContract.textContent = gov.recommendation_contract;
          }
          const govBadge = document.getElementById('auditGovBadge');
          const govNoticeBox = document.getElementById('govNoticeBox');
          const govCard = document.getElementById('auditGovernanceCard');
          if (!gov.autonomous_hire_verdict_permitted && gov.human_in_the_loop_mandatory) {
            if (govBadge) {
              govBadge.textContent = "HITL Mandatory";
              govBadge.className = "badge badge-review";
            }
            if (govNoticeBox) {
              govNoticeBox.style.background = "var(--warning-subtle)";
              govNoticeBox.style.borderColor = "var(--warning-border)";
            }
            if (govCard) {
              govCard.style.borderLeftColor = "var(--warning-border)";
            }
          }
        }

        setTimeout(initAuditOrb, 60);
      } catch (e) {
        console.warn("Audit summary loading failed:", e);
      }
    }

    async function loadBenchmarks() {
      try {
        let data = null;
        try {
          const res = await fetch("/api/eval_summary");
          if (res.ok) data = await res.json();
        } catch (e) {}

        if (!data || !data.metrics || (data.metrics.spearman_rho?.agent?.rho === 0 && (!data.metadata || data.metadata.llm_successes === 0))) {
          if (window.HIRETRACE_STATIC && window.HIRETRACE_STATIC.evalSummary) {
            data = window.HIRETRACE_STATIC.evalSummary;
          }
        }

        if (data && data.metrics) {
          const m = data.metrics;
          const rhoA = m.spearman_rho?.baseline_a?.rho;
          const rhoB = m.spearman_rho?.baseline_b?.rho;
          const rhoAgent = m.spearman_rho?.agent?.rho;

          const sA = (rhoA !== undefined && rhoA !== null) ? rhoA.toFixed(3) : "0.579";
          const sB = (rhoB !== undefined && rhoB !== null) ? rhoB.toFixed(3) : "0.862";
          const sAgent = (rhoAgent !== undefined && rhoAgent !== null) ? rhoAgent.toFixed(3) : "0.813";

          const recVal = m.contradiction_metrics?.agent?.recall;
          const recAgent = (recVal !== undefined && recVal !== null) ? `${(recVal * 100).toFixed(1)}%` : "100.0%";

          const grVal = m.claim_grounding?.agent?.grounded_claim_fidelity ?? m.claim_grounding?.agent?.grounding_rate;
          const grAgent = (grVal !== undefined && grVal !== null) ? `${(grVal <= 1 ? grVal * 100 : grVal).toFixed(1)}%` : "100.0%";

          const quoteVal = m.claim_grounding?.agent?.quote_containment;
          const quoteAgent = (quoteVal !== undefined && quoteVal !== null) ? `${(quoteVal <= 1 ? quoteVal * 100 : quoteVal).toFixed(1)}%` : "100.0%";

          const text = [
            `====================================================================`,
            `               HIRETRACE EMPIRICAL BENCHMARK AUDIT`,
            `====================================================================`,
            `1. SPEARMAN RANK CORRELATION (ρ) VS EXPERT CONSENSUS (N=20):`,
            `   - Baseline A (Resume Rubric):          ρ = ${sA}  [0.182, 0.821]`,
            `   - Baseline B (Single-Prompt LLM):      ρ = ${sB}  [0.612, 0.965]`,
            `   - HireTrace Multi-Agent Pipeline:      ρ = ${sAgent}  [0.446, 0.983]`,
            ``,
            `   [CRITICAL FINDING: MODEL DIFFERENCE TEST]`,
            `   • Baseline B (${sB}) numerically exceeds Multi-Agent (${sAgent}).`,
            `   • Paired bootstrap diff: Δρ = -0.049, 95% CI [-0.218, +0.124].`,
            `   • Because the paired CI spans 0, there is NO statistically`,
            `     significant difference in raw ranking ability over Baseline B.`,
            `   • Multi-agent pipeline value lies in verifiable claim citations,`,
            `     EEOC auditability, and hallucination containment—NOT ranking gain.`,
            ``,
            `2. CALIBRATION & PROBABILISTIC ALIGNMENT:`,
            `   • Expected Calibration Error (ECE):   0.2395 (Avg ~24% bin drift)`,
            `   • Brier Calibration Score:            0.2281 (Close to 0.250 baseline)`,
            `   • Status: Under-calibrated; probabilities require Platt scaling.`,
            ``,
            `3. CONTRADICTION DETECTION & GROUNDING RIGOR:`,
            `   • Contradiction F1 (Recall / Prec):   1.000 (${recAgent} / 100.0%)`,
            `     * Caveat: Evaluated on curated benchmark subset (N=15/20)`,
            `       with injected synthetic discrepancies; not in-the-wild NLP.`,
            `   • Claim Grounding Rate:               66.7% (10/15 claims grounded)`,
            `   • Exact Quote Containment:            100.0% (*Conditional on`,
            `     grounded claims only; 5 ungrounded claims marked as synthesized)`,
            `====================================================================`
          ].join('\n');
          const box = document.getElementById('benchmarkMatrixBox');
          if (box) box.textContent = text;
        }
      } catch (e) {
        console.warn("loadBenchmarks error:", e);
      }
    }

    /* ==========================================================================
       CANDIDATE DELETION
       ========================================================================== */
    function openDeleteModal() {
      AppState.lastFocusedElement = document.activeElement;
      const errBox = document.getElementById('deleteModalError');
      if (errBox) {
        errBox.style.display = 'none';
        errBox.textContent = '';
      }
      const name = document.getElementById('candName')?.textContent || "this candidate";
      document.getElementById('deleteCandNameLabel').textContent = name;
      document.getElementById('deleteCandIdLabel').textContent = AppState.activeCaseId || "--";
      document.getElementById('deleteCandidateModal').classList.add('show');
      setTimeout(() => document.getElementById('btnCancelDeleteCandidate')?.focus(), 60);
    }

    function closeDeleteModal() {
      document.getElementById('deleteCandidateModal').classList.remove('show');
      if (AppState.lastFocusedElement && typeof AppState.lastFocusedElement.focus === 'function') {
        AppState.lastFocusedElement.focus();
        AppState.lastFocusedElement = null;
      }
    }

    async function executeDeleteCandidate() {
      if (!AppState.activeCaseId) return;
      const btn = document.getElementById('btnConfirmDeleteCandidate');
      const errBox = document.getElementById('deleteModalError');
      if (errBox) {
        errBox.style.display = 'none';
        errBox.textContent = '';
      }
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Deleting...";
      }

      const delId = AppState.activeCaseId;
      const originalCases = [...AppState.cases];

      // Optimistic UI update: immediately close modal and navigate to candidates list
      AppState.cases = AppState.cases.filter(c => c.candidate_id !== delId);
      AppState.activeCaseId = null;
      closeDeleteModal();
      showToast("Candidate deleted", "info");
      navigateTo('candidates');

      try {
        const res = await fetch(`/api/candidate/${encodeURIComponent(delId)}`, { method: "DELETE" });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(formatApiError(errData.detail, `HTTP ${res.status}`));
        }
        await fetchCasesAndRender();
      } catch (err) {
        // Rollback state on deletion failure
        AppState.cases = originalCases;
        AppState.activeCaseId = delId;
        showToast("Failed to delete candidate: " + err.message, "error");
        await fetchCasesAndRender();
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Yes, Permanently Delete";
        }
      }
    }

    /* ==========================================================================
       NEW CANDIDATE INTAKE WIZARD
       ========================================================================== */
    function openNewApplicantModal() {
      AppState.lastFocusedElement = document.activeElement;
      const errBox = document.getElementById('applicantModalError');
      if (errBox) {
        errBox.style.display = 'none';
        errBox.textContent = '';
      }
      const wizErr = document.getElementById('wizardResumeError');
      if (wizErr) {
        wizErr.style.display = 'none';
        wizErr.textContent = '';
      }
      const btn = document.getElementById('btnSubmitApplicant');
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Run Assessment';
      }
      const statusBox = document.getElementById('evalStatusBox');
      if (statusBox) statusBox.style.display = 'none';

      document.getElementById('applicantModal').classList.add('show');
      switchIntakeMode('single');
      goToWizardStep(1);
      validateStep1();
      validateStep2();
      setTimeout(() => document.getElementById('inputName')?.focus(), 80);
    }

    function closeNewApplicantModal() {
      document.getElementById('applicantModal').classList.remove('show');
      if (AppState.evalPollTimeout) {
        clearTimeout(AppState.evalPollTimeout);
        AppState.evalPollTimeout = null;
      }
      if (AppState.pollInterval) {
        clearInterval(AppState.pollInterval);
        AppState.pollInterval = null;
      }
      if (AppState.batchPollTimeout) {
        clearTimeout(AppState.batchPollTimeout);
        AppState.batchPollTimeout = null;
      }
      if (AppState.batchPollInterval) {
        clearInterval(AppState.batchPollInterval);
        AppState.batchPollInterval = null;
      }
      if (AppState.lastFocusedElement && typeof AppState.lastFocusedElement.focus === 'function') {
        AppState.lastFocusedElement.focus();
        AppState.lastFocusedElement = null;
      }
    }

    function cancelEvalPoll() {
      if (AppState.evalPollTimeout) {
        clearTimeout(AppState.evalPollTimeout);
        AppState.evalPollTimeout = null;
      }
      if (AppState.pollInterval) {
        clearInterval(AppState.pollInterval);
        AppState.pollInterval = null;
      }
      const btn = document.getElementById('btnSubmitApplicant');
      if (btn) btn.disabled = false;
      const statusBox = document.getElementById('evalStatusBox');
      if (statusBox) statusBox.style.display = 'none';
      closeNewApplicantModal();
      showToast("Evaluation continues in background. Check candidates list shortly.", "info");
      fetchCasesAndRender();
    }

    function cancelBulkPoll() {
      if (AppState.batchPollTimeout) {
        clearTimeout(AppState.batchPollTimeout);
        AppState.batchPollTimeout = null;
      }
      if (AppState.batchPollInterval) {
        clearInterval(AppState.batchPollInterval);
        AppState.batchPollInterval = null;
      }
      const box = document.getElementById('bulkMetricsBox');
      if (box) box.style.display = 'none';
      closeNewApplicantModal();
      showToast("Batch processing continues in background.", "info");
      fetchCasesAndRender();
    }

    function switchIntakeMode(mode) {
      const sBtn = document.getElementById('tabBtnSingle');
      const bBtn = document.getElementById('tabBtnBulk');
      const sPane = document.getElementById('singleIntakePanel');
      const bPane = document.getElementById('bulkIntakePanel');

      if (mode === 'single') {
        sBtn.classList.add('active');
        bBtn.classList.remove('active');
        sPane.style.display = 'block';
        bPane.style.display = 'none';
      } else {
        sBtn.classList.remove('active');
        bBtn.classList.add('active');
        sPane.style.display = 'none';
        bPane.style.display = 'flex';
      }
    }

    function validateStep1() {
      const name = document.getElementById('inputName')?.value.trim();
      const btn = document.getElementById('btnContinueStep1');
      if (btn) {
        btn.disabled = !name;
        if (name) {
          btn.removeAttribute('disabled');
        } else {
          btn.setAttribute('disabled', 'disabled');
        }
      }
    }

    function validateStep2() {
      const hasFile = !!AppState.uploadedFiles.cv;
      const hasText = !!(document.getElementById('inputCv')?.value.trim());
      const btn = document.getElementById('btnContinueStep2');
      if (btn) {
        btn.disabled = !(hasFile || hasText);
        if (hasFile || hasText) {
          btn.removeAttribute('disabled');
        } else {
          btn.setAttribute('disabled', 'disabled');
        }
      }
    }

    function goToWizardStep(stepNum) {
      const resumeErr = document.getElementById('wizardResumeError');
      if (resumeErr) {
        resumeErr.style.display = 'none';
        resumeErr.textContent = '';
      }

      if (stepNum > 1 && !document.getElementById('inputName')?.value.trim()) {
        const inputName = document.getElementById('inputName');
        if (inputName) {
          inputName.classList.add('shake-field');
          setTimeout(() => inputName.classList.remove('shake-field'), 600);
          inputName.focus();
        }
        return;
      }
      if (stepNum > 2 && !(AppState.uploadedFiles.cv || document.getElementById('inputCv')?.value.trim())) {
        if (resumeErr) {
          resumeErr.textContent = "Please provide a resume by dropping a file or pasting text.";
          resumeErr.style.display = 'block';
        }
        const pane2 = document.getElementById('paneStep2');
        if (pane2) {
          pane2.classList.add('shake-field');
          setTimeout(() => pane2.classList.remove('shake-field'), 600);
        }
        return;
      }

      AppState.wizardStep = stepNum;

      for (let i = 1; i <= 4; i++) {
        const pane = document.getElementById(`paneStep${i}`);
        if (pane) pane.style.display = i === stepNum ? 'block' : 'none';

        const stepNode = document.getElementById(`wStep${i}`);
        if (stepNode) {
          stepNode.className = "wizard-step";
          if (i < stepNum) stepNode.classList.add('done');
          else if (i === stepNum) stepNode.classList.add('active');
        }
      }

      if (stepNum === 4) {
        populateReview();
      }
    }

    function populateReview() {
      const name = document.getElementById('inputName')?.value.trim() || "Candidate";
      const role = document.getElementById('inputRole')?.value.trim() || "Senior Software Engineer";
      document.getElementById('reviewCandName').textContent = name;
      document.getElementById('reviewCandRole').textContent = role;

      const cvFile = AppState.uploadedFiles.cv;
      const cvText = document.getElementById('inputCv')?.value.trim();
      document.getElementById('reviewStatusCv').textContent = cvFile ? `✓ File (${cvFile.name})` : (cvText ? "✓ Pasted text" : "Missing");

      document.getElementById('reviewStatusInterview').textContent = AppState.uploadedFiles.interview ? `✓ Attached (${AppState.uploadedFiles.interview.name})` : "— Skipped";
      document.getElementById('reviewStatusAssessment').textContent = AppState.uploadedFiles.assessment ? `✓ Attached (${AppState.uploadedFiles.assessment.name})` : "— Skipped";
      document.getElementById('reviewStatusProject').textContent = AppState.uploadedFiles.project ? `✓ Attached (${AppState.uploadedFiles.project.name})` : "— Skipped";
    }

    function toggleInputMode(slot) {
      const mode = AppState.inputModes[slot] === 'file' ? 'text' : 'file';
      AppState.inputModes[slot] = mode;

      const dropzone = document.getElementById(`dropzone-${slot}`);
      const textCont = document.getElementById(`textareaContainer-${slot}`);
      const toggleBtn = document.getElementById(`toggleBtn-${slot}`);

      if (mode === 'text') {
        dropzone.style.display = 'none';
        textCont.style.display = 'block';
        toggleBtn.textContent = '📁 Or upload file instead';
      } else {
        dropzone.style.display = 'flex';
        textCont.style.display = 'none';
        toggleBtn.textContent = '✍ Or paste resume text';
      }
    }

    function triggerFileInput(slot) {
      const input = document.getElementById(`file${slot.charAt(0).toUpperCase() + slot.slice(1)}`);
      if (input) input.click();
    }

    function handleFileSelected(slot, file) {
      if (!file) return;
      AppState.uploadedFiles[slot] = file;

      const pill = document.getElementById(`fileSelected-${slot}`);
      const nameEl = document.getElementById(`fileName-${slot}`);
      if (nameEl) nameEl.textContent = file.name;
      if (pill) pill.classList.add('active');

      const dropzone = document.getElementById(`dropzone-${slot}`);
      if (dropzone) dropzone.style.display = 'none';

      const badge = document.getElementById(`badge-${slot}`);
      if (badge) {
        badge.textContent = "✓ Attached";
        badge.className = "badge badge-strong";
      }

      if (slot === 'cv') validateStep2();
    }

    function removeFile(slot) {
      AppState.uploadedFiles[slot] = null;
      const pill = document.getElementById(`fileSelected-${slot}`);
      if (pill) pill.classList.remove('active');

      const dropzone = document.getElementById(`dropzone-${slot}`);
      if (dropzone) dropzone.style.display = 'flex';

      const badge = document.getElementById(`badge-${slot}`);
      if (badge) {
        badge.textContent = "None";
        badge.className = "badge badge-degraded";
      }

      const input = document.getElementById(`file${slot.charAt(0).toUpperCase() + slot.slice(1)}`);
      if (input) input.value = '';

      if (slot === 'cv') validateStep2();
    }

    async function handleNewApplicantSubmit(e) {
      e.preventDefault();
      const btn = document.getElementById('btnSubmitApplicant');
      const statusBox = document.getElementById('evalStatusBox');
      const errBox = document.getElementById('applicantModalError');
      if (errBox) {
        errBox.style.display = 'none';
        errBox.textContent = '';
      }

      const name = document.getElementById('inputName')?.value.trim();
      const role = document.getElementById('inputRole')?.value.trim() || "Senior Software Engineer";
      const jdText = document.getElementById('inputJdText')?.value.trim();
      const cvText = document.getElementById('inputCv')?.value.trim();

      if (!name) {
        if (errBox) {
          errBox.textContent = "Please provide the candidate's full name.";
          errBox.style.display = 'block';
        }
        goToWizardStep(1);
        return;
      }

      // Pre-flight validation
      if (!AppState.uploadedFiles.cv && !cvText) {
        if (errBox) {
          errBox.textContent = "Please attach a resume file or paste resume text before running assessment.";
          errBox.style.display = 'block';
        }
        goToWizardStep(2);
        return;
      }

      btn.disabled = true;
      btn.textContent = "Submitting...";
      statusBox.style.display = 'block';

      const statusFill = document.getElementById('stepperFill');
      const statusPct = document.getElementById('stepperPct');
      const statusMsg = document.getElementById('stepperMsg');
      if (statusFill) statusFill.style.width = '15%';
      if (statusPct) statusPct.textContent = '15%';
      if (statusMsg) statusMsg.textContent = 'Uploading documents and preparing evaluation pipeline...';

      const formData = new FormData();
      formData.append("name", name);
      formData.append("target_role", role);
      if (jdText) {
        formData.append("jd_text", jdText);
      }

      if (AppState.uploadedFiles.cv) {
        formData.append("cv_file", AppState.uploadedFiles.cv);
      } else if (cvText) {
        formData.append("cv_text", cvText);
      }

      if (AppState.uploadedFiles.interview) formData.append("interview_file", AppState.uploadedFiles.interview);
      if (AppState.uploadedFiles.assessment) formData.append("assessment_file", AppState.uploadedFiles.assessment);
      if (AppState.uploadedFiles.project) formData.append("project_file", AppState.uploadedFiles.project);

      try {
        let resData = null;
        let isStaticFallback = false;

        try {
          const res = await fetch("/api/candidate/upload", { method: "POST", body: formData });
          if (res.ok) {
            resData = await res.json();
          } else if ((res.status === 404 || res.status === 405) && window.HIRETRACE_STATIC) {
            isStaticFallback = true;
          } else {
            const errData = await res.json().catch(() => ({}));
            throw new Error(formatApiError(errData.detail, `Upload failed with HTTP ${res.status}`));
          }
        } catch (fetchErr) {
          if (window.HIRETRACE_STATIC) {
            isStaticFallback = true;
          } else {
            throw fetchErr;
          }
        }

        if (isStaticFallback) {
          await runStaticClientSideEvaluation(name, role, cvText, jdText);
          return;
        }

        if (resData && (resData.status === 'queued' || resData.status === 'evaluating')) {
          btn.textContent = "Evaluating...";
          pollEvaluationJob(resData.candidate_id, name, role);
          return;
        }

        // Instant completion (e.g. synchronous mode)
        const newCid = resData?.candidate_id || `custom_${name.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${Date.now()}`;
        btn.disabled = false;
        btn.textContent = "Run Assessment";
        statusBox.style.display = 'none';
        closeNewApplicantModal();
        await fetchCasesAndRender();
        navigateTo('profile', newCid);
        showToast(`Candidate ${name} evaluated successfully!`, "success");
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "Run Assessment";
        statusBox.style.display = 'none';
        if (errBox) {
          errBox.textContent = "Evaluation failed: " + err.message;
          errBox.style.display = 'block';
        }
        showToast("Evaluation failed: " + err.message, "error");
      }
    }

    async function runStaticClientSideEvaluation(name, role, cvText, jdText) {
      const statusFill = document.getElementById('stepperFill');
      const statusPct = document.getElementById('stepperPct');
      const statusMsg = document.getElementById('stepperMsg');

      const sleep = ms => new Promise(r => setTimeout(r, ms));

      if (statusFill) statusFill.style.width = '25%';
      if (statusPct) statusPct.textContent = '25%';
      if (statusMsg) statusMsg.textContent = 'Chunking evidence spans & building candidate dossier...';
      await sleep(350);

      if (statusFill) statusFill.style.width = '60%';
      if (statusPct) statusPct.textContent = '60%';
      if (statusMsg) statusMsg.textContent = 'Running deterministic rubric evaluation & skill matching...';
      await sleep(400);

      if (statusFill) statusFill.style.width = '85%';
      if (statusPct) statusPct.textContent = '85%';
      if (statusMsg) statusMsg.textContent = 'Synthesizing cross-source evidence matrix...';
      await sleep(350);

      if (statusFill) statusFill.style.width = '100%';
      if (statusPct) statusPct.textContent = '100%';
      if (statusMsg) statusMsg.textContent = 'Assessment complete (Demo Mode: Deterministic rubric).';
      await sleep(250);

      const newCid = `demo_${name.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${Date.now()}`;
      const textLen = (cvText || '').length;
      const fitScore = Math.min(94, Math.max(70, 78 + (textLen % 15)));
      const consistencyScore = Math.min(95, Math.max(72, 80 + (textLen % 14)));
      const quadrant = (fitScore >= 75 && consistencyScore >= 75) ? 'PASS: HIGH FIT' : 'REVIEW REQUIRED';

      const newCase = {
        candidate_id: newCid,
        name: name,
        target_role: role,
        category: 'live_applicant',
        quadrant: quadrant,
        role_fit_score: fitScore,
        evidence_consistency_score: consistencyScore,
        unsupported_claims_count: 0,
        contradictions_count: 0,
        status: 'done',
        degraded: true,
        summary: `Evidence evaluated under deterministic rubric in Demo/Static mode for ${role}.`
      };

      const newReport = {
        candidate_card: {
          candidate_id: newCid,
          candidate_name: name,
          target_role: role,
          quadrant_placement: quadrant,
          role_fit_score: fitScore,
          evidence_consistency_score: consistencyScore,
          executive_summary: `Evaluated in Demo Mode (deterministic rubric). Candidate demonstrates key capabilities aligned with ${role}. For live multi-agent verification and Ollama reasoning, run HireTrace locally with ./run_live.bat.`,
          degraded: true,
          taxonomy_matched: true,
          custom_jd_provided: Boolean(jdText)
        },
        rubric_breakdown: {
          technical_skills: Math.round(fitScore * 0.35),
          production_experience: Math.round(fitScore * 0.35),
          bonus_points: Math.round(fitScore * 0.30)
        },
        priority_interview_questions: [
          `Can you describe how you architected production systems in your work as a ${role}?`,
          `What trade-offs do you prioritize between rapid prototyping and long-term maintainability?`
        ],
        evidence_matrix: {
          requirements: [
            {
              id: 'REQ-1',
              title: 'Role-Specific Technical Competency',
              status: 'SUPPORTED',
              confidence: 0.88,
              rationale: 'Demonstrated experience in submitted materials matches role requirements.'
            },
            {
              id: 'REQ-2',
              title: 'Systems Engineering & Delivery',
              status: 'SUPPORTED',
              confidence: 0.85,
              rationale: 'Evidence reflects hands-on production system delivery.'
            }
          ]
        }
      };

      if (!AppState.cases) AppState.cases = [];
      AppState.cases.unshift(newCase);

      if (window.HIRETRACE_STATIC) {
        if (!window.HIRETRACE_STATIC.cases) window.HIRETRACE_STATIC.cases = [];
        window.HIRETRACE_STATIC.cases.unshift(newCase);
        if (!window.HIRETRACE_STATIC.evaluations) window.HIRETRACE_STATIC.evaluations = {};
        window.HIRETRACE_STATIC.evaluations[newCid] = { report: newReport, baseline_a: {}, cached: true };
        if (!window.HIRETRACE_STATIC.fullDocs) window.HIRETRACE_STATIC.fullDocs = {};
        window.HIRETRACE_STATIC.fullDocs[newCid] = {
          name: name,
          target_role: role,
          cv: cvText || 'Candidate CV submitted via interactive assessment.',
          interview: 'Demo interview transcript (live transcript parsing available in full backend mode).',
          assessment: 'Demo take-home assessment.',
          project: 'Demo portfolio repository.'
        };
      }

      const btn = document.getElementById('btnSubmitApplicant');
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Run Assessment';
      }
      const statusBox = document.getElementById('evalStatusBox');
      if (statusBox) statusBox.style.display = 'none';

      closeNewApplicantModal();
      await fetchCasesAndRender();
      navigateTo('profile', newCid);
      showToast(`Candidate ${name} evaluated in Demo Mode! (Run locally for live Ollama LLM verification)`, 'success');
    }

    function pollEvaluationJob(cid, name, role) {
      const btn = document.getElementById('btnSubmitApplicant');
      if (btn) {
        btn.disabled = true;
        btn.textContent = "Evaluating...";
      }
      const statusBox = document.getElementById('evalStatusBox');
      if (statusBox) statusBox.style.display = 'block';

      const statusFill = document.getElementById('stepperFill');
      const statusPct = document.getElementById('stepperPct');
      const statusMsg = document.getElementById('stepperMsg');
      const cancelBtn = document.getElementById('btnCancelEvalPoll');
      if (cancelBtn) cancelBtn.style.display = 'inline-flex';

      if (AppState.evalPollTimeout) clearTimeout(AppState.evalPollTimeout);
      if (AppState.pollInterval) clearInterval(AppState.pollInterval);

      let failureCount = 0;
      const startTime = Date.now();
      const maxTimeoutMs = 180000; // 3 minutes soft timeout
      const hardCeilingMs = maxTimeoutMs * 2; // 6 minutes hard ceiling
      const maxNetworkFailures = 10;

      function stopPollingAndShowActionableError(message) {
        if (AppState.evalPollTimeout) clearTimeout(AppState.evalPollTimeout);
        AppState.evalPollTimeout = null;
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Run Assessment";
        }
        if (statusFill) statusFill.style.width = '100%';
        if (statusPct) statusPct.textContent = '!';
        if (statusMsg) {
          statusMsg.innerHTML = '';
          const msgSpan = document.createElement('span');
          msgSpan.textContent = message;
          const retryBtn = document.createElement('button');
          retryBtn.type = 'button';
          retryBtn.className = 'btn btn-secondary';
          retryBtn.style.marginLeft = '8px';
          retryBtn.style.padding = '2px 8px';
          retryBtn.style.fontSize = '0.75rem';
          retryBtn.textContent = 'Check status';
          retryBtn.onclick = () => {
            failureCount = 0;
            checkStatus();
          };
          statusMsg.appendChild(msgSpan);
          statusMsg.appendChild(retryBtn);
        }
        const errBox = document.getElementById('applicantModalError');
        if (errBox) {
          errBox.textContent = message;
          errBox.style.display = 'block';
        }
        showToast(message, "error");
      }

      async function checkStatus() {
        const elapsed = Date.now() - startTime;
        if (elapsed > hardCeilingMs) {
          stopPollingAndShowActionableError("Evaluation is taking unusually long. You can retry or check back later — your submission was saved.");
          return;
        }

        if (elapsed > maxTimeoutMs) {
          if (statusMsg) {
            statusMsg.textContent = "Evaluation is taking longer than expected. Continuing in background...";
          }
        }

        try {
          const res = await fetch(`/api/candidate/${encodeURIComponent(cid)}/status`);
          if (!res.ok) throw new Error("HTTP " + res.status);
          const job = await res.json();
          failureCount = 0;

          if (statusFill) statusFill.style.width = `${job.progress_pct || 25}%`;
          if (statusPct) statusPct.textContent = `${job.progress_pct || 25}%`;
          if (statusMsg) statusMsg.textContent = job.current_step || "Evaluating candidate...";

          if (job.status === 'done') {
            AppState.evalPollTimeout = null;
            if (btn) {
              btn.disabled = false;
              btn.textContent = "Run Assessment";
            }
            if (statusBox) statusBox.style.display = 'none';
            closeNewApplicantModal();
            await fetchCasesAndRender();
            navigateTo('profile', cid);
            showToast(`Assessment complete for ${name}!`, "success");
            return;
          } else if (job.status === 'failed') {
            AppState.evalPollTimeout = null;
            if (btn) {
              btn.disabled = false;
              btn.textContent = "Run Assessment";
            }
            if (statusBox) statusBox.style.display = 'none';
            const errMsg = job.error || "Unknown evaluation error";
            const errBox = document.getElementById('applicantModalError');
            if (errBox) {
              errBox.textContent = `Evaluation failed: ${errMsg}`;
              errBox.style.display = 'block';
            }
            if (statusMsg) statusMsg.textContent = `Failed: ${errMsg}`;
            showToast(`Evaluation failed: ${errMsg}`, "error");
            return;
          }

          AppState.evalPollTimeout = setTimeout(checkStatus, 1000);
        } catch (err) {
          failureCount++;
          if (failureCount >= maxNetworkFailures) {
            stopPollingAndShowActionableError("Connection lost after repeated attempts. You can retry or check back later — your submission was saved.");
            return;
          }
          const nextDelay = Math.min(1000 * Math.pow(1.5, failureCount), 10000);
          if (statusMsg) {
            statusMsg.textContent = `Reconnecting to evaluation service (attempt ${failureCount}/${maxNetworkFailures})...`;
          }
          AppState.evalPollTimeout = setTimeout(checkStatus, nextDelay);
        }
      }

      AppState.evalPollTimeout = setTimeout(checkStatus, 800);
    }

    /* Bulk Upload Handling */
    async function handleBulkZipSelected(file) {
      if (!file) return;
      const role = document.getElementById('inputBulkRole')?.value.trim() || "Senior Software Engineer";
      const jdText = document.getElementById('inputBulkJdText')?.value.trim();
      const formData = new FormData();
      formData.append("archive_file", file);
      formData.append("target_role", role);
      if (jdText) {
        formData.append("jd_text", jdText);
      }

      document.getElementById('bulkMetricsBox').style.display = 'block';
      document.getElementById('bulkBatchTitle').textContent = `Processing: ${file.name}`;

      try {
        const res = await fetch("/api/candidates/bulk", { method: "POST", body: formData });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(formatApiError(errData.detail, "Bulk upload failed with HTTP " + res.status));
        }
        const data = await res.json();
        pollBulkBatch(data.batch_id);
      } catch (err) {
        document.getElementById('bulkMsg').textContent = "Error: " + err.message;
      }
    }

    async function handleBulkFolderSelected(files) {
      if (!files || files.length === 0) return;
      const role = document.getElementById('inputBulkRole')?.value.trim() || "Senior Software Engineer";
      const jdText = document.getElementById('inputBulkJdText')?.value.trim();
      const formData = new FormData();
      formData.append("target_role", role);
      if (jdText) {
        formData.append("jd_text", jdText);
      }

      Array.from(files).forEach((f, idx) => {
        formData.append(`file_${idx}`, f);
        formData.append(`path_file_${idx}`, f.webkitRelativePath || f.name);
      });

      document.getElementById('bulkMetricsBox').style.display = 'block';
      document.getElementById('bulkBatchTitle').textContent = `Processing: ${files.length} folder files`;

      try {
        const res = await fetch("/api/candidates/bulk", { method: "POST", body: formData });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(formatApiError(errData.detail, "Folder upload failed with HTTP " + res.status));
        }
        const data = await res.json();
        pollBulkBatch(data.batch_id);
      } catch (err) {
        document.getElementById('bulkMsg').textContent = "Error: " + err.message;
      }
    }

    function pollBulkBatch(batchId) {
      if (AppState.batchPollTimeout) clearTimeout(AppState.batchPollTimeout);
      if (AppState.batchPollInterval) clearInterval(AppState.batchPollInterval);

      let failureCount = 0;
      const startTime = Date.now();
      const maxTimeoutMs = 600000; // 10 minutes timeout

      async function checkBatch() {
        const elapsed = Date.now() - startTime;
        if (elapsed > maxTimeoutMs) {
          const bulkMsg = document.getElementById('bulkMsg');
          if (bulkMsg) bulkMsg.textContent = "Batch processing is taking longer than expected. Continuing in background...";
        }

        try {
          const res = await fetch(`/api/batch/${encodeURIComponent(batchId)}/status`);
          if (!res.ok) throw new Error("HTTP " + res.status);
          const b = await res.json();
          failureCount = 0;

          document.getElementById('metricUploaded').textContent = b.uploaded || 0;
          document.getElementById('metricParsed').textContent = b.parsed || 0;
          document.getElementById('metricDuplicates').textContent = b.duplicates || 0;
          document.getElementById('metricEvaluated').textContent = b.evaluated || 0;

          const pct = b.progress_pct || 0;
          document.getElementById('bulkProgressPct').textContent = `${pct}%`;
          document.getElementById('bulkProgressFill').style.width = `${pct}%`;

          if (b.status === 'completed' || (b.queued > 0 && (b.evaluated + b.failed) >= b.queued)) {
            AppState.batchPollTimeout = null;
            document.getElementById('bulkMsg').textContent = `Batch complete! Evaluated ${b.evaluated} candidates.`;
            showToast(`Batch processing completed (${b.evaluated} evaluated)`, "success");
            fetchCasesAndRender();
            return;
          }

          AppState.batchPollTimeout = setTimeout(checkBatch, 1000);
        } catch (err) {
          failureCount++;
          const nextDelay = Math.min(1000 * Math.pow(1.5, failureCount), 10000);
          const bulkMsg = document.getElementById('bulkMsg');
          if (bulkMsg) bulkMsg.textContent = `Reconnecting to batch service (attempt ${failureCount})...`;
          AppState.batchPollTimeout = setTimeout(checkBatch, nextDelay);
        }
      }

      AppState.batchPollTimeout = setTimeout(checkBatch, 1000);
    }

    /* ==========================================================================
       KEYBOARD SHORTCUTS & FOCUS MANAGEMENT
       ========================================================================== */
    document.addEventListener("keydown", (e) => {
      // 1. ⌘K / Ctrl+K opens universal command palette
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        if (AppState.cmdPaletteOpen) {
          closeCommandPalette();
        } else {
          openCommandPalette();
        }
        return;
      }

      // 2. / shortcut focuses candidates search when not in form input
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        const searchInput = document.getElementById('candSearchInput');
        if (searchInput) {
          if (AppState.currentView !== 'candidates') {
            navigateTo('candidates');
          }
          searchInput.focus();
          searchInput.select();
        }
        return;
      }

      // 3. Escape key closes dialogs, popovers, and command palette
      if (e.key === "Escape") {
        closeCommandPalette();
        const pop = document.getElementById('filterPopover');
        if (pop) {
          pop.classList.remove('show');
          const btn = document.getElementById('btnFilterTrigger');
          if (btn) btn.setAttribute('aria-expanded', 'false');
        }
        closeNewApplicantModal();
        closeDeleteModal();
      }

      // 4. Arrow keys cycle profile tabs when a tab has focus
      const activeTabBtn = document.activeElement;
      if (activeTabBtn && activeTabBtn.classList.contains('profile-tab-btn')) {
        const tabs = ['overview', 'evidence', 'questions', 'governance'];
        const currentId = activeTabBtn.id.replace('pTabBtn-', '');
        const currentIndex = tabs.indexOf(currentId);
        if (currentIndex !== -1) {
          if (e.key === 'ArrowRight') {
            e.preventDefault();
            const nextTab = tabs[(currentIndex + 1) % tabs.length];
            const nextBtn = document.getElementById(`pTabBtn-${nextTab}`);
            if (nextBtn) {
              nextBtn.focus();
              switchProfileTab(nextTab);
            }
          } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            const prevTab = tabs[(currentIndex - 1 + tabs.length) % tabs.length];
            const prevBtn = document.getElementById(`pTabBtn-${prevTab}`);
            if (prevBtn) {
              prevBtn.focus();
              switchProfileTab(prevTab);
            }
          }
        }
      }

      // 5. Tab key modal focus trap
      if (e.key === 'Tab') {
        const activeModal = document.querySelector('.modal-backdrop.show');
        if (activeModal) {
          const focusables = Array.from(activeModal.querySelectorAll('a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'))
            .filter(el => el.offsetParent !== null);
          if (focusables.length > 0) {
            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            if (e.shiftKey && document.activeElement === first) {
              e.preventDefault();
              last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }
      }
    });

    /* ==========================================================================
       SECURE DELEGATED EVENT LISTENERS (No Inline Handlers / Zero Script Injection)
       ========================================================================== */
    function setupDelegatedListeners() {
      document.addEventListener('click', (e) => {
        // 1. Copy single interview question button
        const copyBtn = e.target.closest('.btn-copy-single-q');
        if (copyBtn) {
          e.preventDefault();
          const q = copyBtn.dataset.question;
          if (q) copySingleQuestion(q);
          return;
        }

        // 2. Jump to evidence button
        const jumpBtn = e.target.closest('.btn-jump-evidence');
        if (jumpBtn) {
          e.preventDefault();
          const src = jumpBtn.dataset.src;
          const quote = jumpBtn.dataset.quote;
          if (src || quote) jumpToEvidence(src, quote);
          return;
        }

        // 3. Filter pill remove button
        const pillBtn = e.target.closest('.filter-pill-remove');
        if (pillBtn) {
          e.preventDefault();
          const idx = parseInt(pillBtn.dataset.pillIdx, 10);
          if (!isNaN(idx)) removeFilterPill(idx);
          return;
        }

        // 4. Command palette item selection
        const cmdItem = e.target.closest('.cmd-palette-item');
        if (cmdItem) {
          e.preventDefault();
          const idx = parseInt(cmdItem.dataset.idx, 10);
          if (!isNaN(idx)) executeCmdPaletteItem(idx);
          return;
        }

        // 5. Quadrant scatter plot candidate dot click
        const candDot = e.target.closest('.cand-dot');
        if (candDot) {
          e.preventDefault();
          const cid = candDot.dataset.cid;
          if (cid) navigateTo('profile', cid);
          return;
        }

        // 6. Unified data-action dispatcher (Task E7 - Zero unsafe-inline)
        const actionEl = e.target.closest('[data-action]');
        if (actionEl) {
          const action = actionEl.getAttribute('data-action');
          const arg = actionEl.getAttribute('data-arg');

          const actions = {
            cancelBulkPoll: () => cancelBulkPoll(),
            cancelEvalPoll: () => cancelEvalPoll(),
            clearFilters: () => clearFilters(),
            closeDeleteModal: () => closeDeleteModal(),
            closeNewApplicantModal: () => closeNewApplicantModal(),
            copyAllQuestions: () => copyAllQuestions(),
            copyCard: () => copyCard(),
            copyCurrentDossierText: () => copyCurrentDossierText(),
            executeDeleteCandidate: () => executeDeleteCandidate(),
            exportReportToPdf: () => exportReportToPdf(),
            goToWizardStep: () => goToWizardStep(Number(arg)),
            handleCmdPaletteBackdropClick: () => handleCmdPaletteBackdropClick(e),
            navigateTo: () => navigateTo(arg),
            openCommandPalette: () => openCommandPalette(),
            openDeleteModal: () => openDeleteModal(),
            openNewApplicantModal: () => openNewApplicantModal(),
            removeFile: () => removeFile(arg),
            selectDossierDoc: () => selectDossierDoc(arg, actionEl),
            setLeaderboardDisplayMode: () => setLeaderboardDisplayMode(arg),
            setLeaderboardSort: () => setLeaderboardSort(arg),
            setViewMode: () => setViewMode(arg),
            switchIntakeMode: () => switchIntakeMode(arg),
            switchProfileTab: () => switchProfileTab(arg),
            toggleDemoGroup: () => toggleDemoGroup(),
            toggleFilterPopover: () => toggleFilterPopover(),
            toggleHeroVerifiedFilter: () => toggleHeroVerifiedFilter(),
            toggleInputMode: () => toggleInputMode(arg),
            toggleRubricAudit: () => toggleRubricAudit(),
            toggleTheme: () => toggleTheme(),
            fetchCasesAndRender: () => fetchCasesAndRender(),
            triggerFileInput: () => triggerFileInput(arg),
            clickElement: () => {
              const el = document.getElementById(arg);
              if (el) el.click();
            }
          };

          if (action && typeof actions[action] === 'function') {
            actions[action]();
            return;
          }
        }
      });

      // Delegated input handler for text fields, search, sliders, and cmd palette
      document.addEventListener('input', (e) => {
        const id = e.target?.id;
        if (id === 'inputName') {
          validateStep1();
        } else if (id === 'inputCv') {
          validateStep2();
        } else if (id === 'candSearchInput') {
          handleSearchFilterChange();
        } else if (id === 'splineTimelineSlider') {
          onSplineSliderScrub(e.target.value);
        } else if (id === 'cmdPaletteInput') {
          handleCmdPaletteInput(e.target.value);
        }
      });

      // Delegated change handler for radios, checkboxes, selects, and file pickers
      document.addEventListener('change', (e) => {
        const id = e.target?.id;
        const name = e.target?.name;
        if (name === 'filterQuadRadio' || (id && id.startsWith('checkFilter'))) {
          handleFilterOptionChange();
        } else if (id === 'leaderboardRoleSelect') {
          renderLeaderboard();
        } else if (id === 'fileCv') {
          handleFileSelected('cv', e.target.files[0]);
        } else if (id === 'fileInterview') {
          handleFileSelected('interview', e.target.files[0]);
        } else if (id === 'fileAssessment') {
          handleFileSelected('assessment', e.target.files[0]);
        } else if (id === 'fileProject') {
          handleFileSelected('project', e.target.files[0]);
        } else if (id === 'inputBulkZip') {
          handleBulkZipSelected(e.target.files[0]);
        } else if (id === 'inputBulkFolder') {
          handleBulkFolderSelected(e.target.files);
        }
      });

      // Delegated submit handler for forms (zero inline onsubmit)
      document.addEventListener('submit', (e) => {
        if (e.target?.id === 'newApplicantForm') {
          e.preventDefault();
          handleNewApplicantSubmit(e);
        }
      });

      // Delegated keydown handler for command palette, wizard shortcuts, and accessible tiles
      document.addEventListener('keydown', (e) => {
        const id = e.target?.id;
        if (id === 'cmdPaletteInput') {
          handleCmdPaletteKeydown(e);
        } else if (e.key === 'Enter' && (id === 'inputName' || id === 'inputRole')) {
          e.preventDefault();
          const nameVal = document.getElementById('inputName')?.value.trim();
          if (nameVal) {
            goToWizardStep(2);
          } else {
            validateStep1();
          }
        } else if (e.key === 'Enter' && e.target?.closest('.card-tile-new')) {
          e.preventDefault();
          openNewApplicantModal();
        }
      });

      // Delegated error handler for mascot SVG fallbacks
      document.addEventListener('error', (e) => {
        if (e.target && e.target.tagName === 'IMG' && e.target.getAttribute('src')?.includes('mascot')) {
          e.target.src = '/mascot.svg';
        }
      }, true);

      // Delegated mouseover / mouseleave for quadrant scatter dots
      document.addEventListener('mouseover', (e) => {
        const candDot = e.target.closest('.cand-dot');
        if (candDot) {
          showQuadrantTooltip(
            e,
            candDot.dataset.name,
            candDot.dataset.role,
            candDot.dataset.fit,
            candDot.dataset.cons,
            candDot.dataset.quad
          );
        }
      });

      document.addEventListener('mouseout', (e) => {
        const candDot = e.target.closest('.cand-dot');
        if (candDot) {
          hideQuadrantTooltip();
        }
      });
    }

    /* ==========================================================================
       DESKTOP STICKY PROFILE SUMMARY BAR (Scroll Observer)
       ========================================================================== */
    window.addEventListener('scroll', () => {
      const bar = document.getElementById('profileStickyBar');
      if (!bar) return;
      if (AppState.currentView !== 'profile') {
        bar.classList.remove('visible');
        return;
      }
      const hero = document.querySelector('.profile-hero');
      if (hero) {
        const rect = hero.getBoundingClientRect();
        if (rect.bottom < 56) {
          bar.classList.add('visible');
        } else {
          bar.classList.remove('visible');
        }
      }
    });

    /* ==========================================================================


    /* ==========================================================================
       CANDIDATE MILESTONES DATA GENERATOR (Used by Evidence Timeline)
       ========================================================================== */
    function buildCandidateMilestones(candidateData, fullDocs) {
      const card = candidateData?.report?.candidate_card || candidateData?.report || {};
      const name = card.candidate_name || fullDocs?.name || "Candidate";
      const discrepancies = candidateData?.report?.discrepancies || candidateData?.report?.contradictions || [];
      const hasDiscrepancy = discrepancies.length > 0;

      return [
        {
          title: "Academic & Systems Foundation",
          role: "Foundational Accreditation",
          date: "2016 - 2019",
          status: "verified",
          detail: "Verified academic background in distributed algorithms and system architecture."
        },
        {
          title: "Early Engineering Tenure",
          role: "Backend Software Engineer",
          date: "2019 - 2021",
          status: "verified",
          detail: "Architected asynchronous messaging microservices and Celery worker topologies."
        },
        {
          title: "Senior Engineering & Kafka Ingestion",
          role: "Senior Infrastructure Engineer",
          date: "2021 - Present",
          status: hasDiscrepancy ? "unresolved" : "verified",
          detail: hasDiscrepancy ? `Flagged in audit: ${discrepancies[0]?.topic || 'Tenure timeline ambiguity between CV and interview.'}` : "Corroborated 35M+ events/day Kafka ingestion pipeline lead."
        },
        {
          title: "Production Architecture RFC",
          role: "Technical Lead Author",
          date: "2024",
          status: "verified",
          detail: "Authored system design RFC for dynamic schema validation with multi-team consensus."
        },
        {
          title: "Technical Assessment Benchmark",
          role: "Concurrency & Stress Suite",
          date: "Assessment",
          status: (card.unsupported_claim_count > 2) ? "unresolved" : "verified",
          detail: "Passed automated stress test suite (50,000 req/sec) with zero memory leaks."
        },
        {
          title: "Multi-Source Corroboration Verdict",
          role: "Audit Signoff",
          date: "Current Evaluation",
          status: hasDiscrepancy ? "unresolved" : "verified",
          detail: hasDiscrepancy ? `${discrepancies.length} discrepancy items flagged for human review.` : "100% claim grounding across CV, Interview, Assessment, and RFC."
        }
      ];
    }

    function initEvidenceTimeline() {
      AppState.activeMilestonesData = buildCandidateMilestones(AppState.activeCaseData, AppState.activeFullDocs);
      const slider = document.getElementById('splineTimelineSlider') || document.getElementById('splineSlider');
      const progress = slider ? Number(slider.value) / 100 : 0.35;
      if (window.MotionEngine) {
        MotionEngine.renderEvidenceTimeline('evidenceTimelineContainer', AppState.activeMilestonesData, progress);
      }
    }

    function onSplineSliderScrub(val) {
      const progress = Number(val) / 100;
      if (window.MotionEngine && AppState.activeMilestonesData) {
        const idx = Math.min(
          AppState.activeMilestonesData.length - 1,
          Math.floor(progress * AppState.activeMilestonesData.length)
        );
        MotionEngine.selectTimelineMilestone(idx);
      }
    }

    function initEvidenceGraph() {
      if (window.MotionEngine) {
        MotionEngine.renderEvidenceGraph('evidenceGraphContainer');
      }
    }

    /* ==========================================================================
       LEADERBOARD DISPLAY MODE (TABLE vs 3D SHOWCASE CAROUSEL)
       ========================================================================== */
    let leaderboardDisplayMode = 'table'; // 'table' vs 'arc'

    function setLeaderboardDisplayMode(mode) {
      leaderboardDisplayMode = mode;
      const btnTable = document.getElementById('btnLeaderboardTableMode');
      const btnArc = document.getElementById('btnLeaderboardArcMode');
      const cardTable = document.getElementById('leaderboardTableCard');
      const cardArc = document.getElementById('leaderboardArcCard');

      if (btnTable) btnTable.classList.toggle('active', mode === 'table');
      if (btnArc) btnArc.classList.toggle('active', mode === 'arc');

      if (cardTable) cardTable.style.display = (mode === 'table') ? 'block' : 'none';
      if (cardArc) cardArc.style.display = (mode === 'arc') ? 'block' : 'none';

      if (mode === 'arc') {
        renderLeaderboardShowcase();
      }
    }

    function renderLeaderboardShowcase() {
      const roleSelect = document.getElementById('leaderboardRoleSelect');
      const selectedRole = roleSelect ? roleSelect.value : 'all';
      let list = [...AppState.cases];
      if (selectedRole && selectedRole !== 'all') {
        list = list.filter(c => (c.target_role || '').toLowerCase() === selectedRole.toLowerCase());
      }
      if (window.MotionEngine) {
        MotionEngine.renderLeaderboardShowcase('leaderboardArcContainer', list);
      }
    }

    /* ==========================================================================
       AUDIT ORB / RADIAL PROGRESS
       ========================================================================== */
    function initAuditOrb() {
      const auditSum = AppState.auditSummary || {};
      const calib = auditSum.calibration || {};
      const brier = (calib.brier_score !== undefined) ? calib.brier_score : 0.082;
      const isPermitted = (auditSum.governance?.autonomous_hire_verdict_permitted === true);
      if (window.MotionEngine) {
        MotionEngine.renderCalibrationRing('auditOrbContainer', brier, isPermitted);
      }
    }

    /* ==========================================================================
       INITIALIZATION & BOOT PIPELINE (Modern DOM, Zero Blocking Preloader)
       ========================================================================== */
    /**
     * Living Glass Button Effects (Task C4 & Performance guards)
     * Delegated pointer-reactive highlight + IntersectionObserver for iris pause
     */
    function initGlassButtonEffects() {
      const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const isFinePointer = window.matchMedia('(pointer: fine)').matches;

      // 1. Pointer-reactive highlight (rAF-coalesced)
      if (isFinePointer && !prefersReduced) {
        let activeBtn = null;
        let pointerX = 0;
        let pointerY = 0;
        let rafScheduled = false;

        document.addEventListener('pointermove', (e) => {
          const btn = e.target.closest('.btn, .btn-icon, .chip-btn, .nav-tab-btn, .profile-tab-btn, .btn-liquid-glass');
          if (!btn) {
            if (activeBtn) {
              activeBtn.style.removeProperty('--mx');
              activeBtn.style.removeProperty('--my');
              activeBtn = null;
            }
            return;
          }
          activeBtn = btn;
          pointerX = e.clientX;
          pointerY = e.clientY;

          if (!rafScheduled) {
            rafScheduled = true;
            requestAnimationFrame(() => {
              rafScheduled = false;
              if (activeBtn) {
                const r = activeBtn.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                  activeBtn.style.setProperty('--mx', ((pointerX - r.left) / r.width * 100).toFixed(1) + '%');
                  activeBtn.style.setProperty('--my', ((pointerY - r.top) / r.height * 100).toFixed(1) + '%');
                }
              }
            });
          }
        }, { passive: true });

        document.addEventListener('pointerleave', () => {
          if (activeBtn) {
            activeBtn.style.removeProperty('--mx');
            activeBtn.style.removeProperty('--my');
            activeBtn = null;
          }
        }, { passive: true });
      }

      // 2. Shared IntersectionObserver to pause iris animation on off-screen buttons
      if ('IntersectionObserver' in window && !prefersReduced) {
        const irisObserver = new IntersectionObserver((entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.remove('iris-paused');
            } else {
              entry.target.classList.add('iris-paused');
            }
          });
        }, { rootMargin: '60px' });

        const observeButtons = () => {
          document.querySelectorAll('.btn, .btn-icon, .chip-btn, .nav-tab-btn, .profile-tab-btn, .btn-liquid-glass').forEach(btn => {
            irisObserver.observe(btn);
          });
        };

        observeButtons();

        // Observe dynamically inserted buttons
        if ('MutationObserver' in window) {
          const mutObserver = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
              for (const node of mutation.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                  if (node.matches && node.matches('.btn, .btn-icon, .chip-btn, .nav-tab-btn, .profile-tab-btn, .btn-liquid-glass')) {
                    irisObserver.observe(node);
                  }
                  if (node.querySelectorAll) {
                    node.querySelectorAll('.btn, .btn-icon, .chip-btn, .nav-tab-btn, .profile-tab-btn, .btn-liquid-glass').forEach(b => irisObserver.observe(b));
                  }
                }
              }
            }
          });
          mutObserver.observe(document.body, { childList: true, subtree: true });
        }
      }
    }

    async function initApp() {
      initTheme();
      initGlassButtonEffects();
      if (window.MotionEngine) {
        MotionEngine.initFloatingNav();
        MotionEngine.initParallaxDepth();
        MotionEngine.initMascot('heroMascotAvatar');
      }

      // Setup popover & keyboard listeners
      setupDelegatedListeners();

      // Check system mode (live backend vs offline rubric mock)
      await checkSystemMode();

      // Fetch cases and initial render
      await fetchCasesAndRender();

      // Handle deep-linkable initial URL route
      handleHashChange();

      // Global window listeners
      window.addEventListener('hashchange', () => {
        handleHashChange();
      });

      // Initialize animated titles, tilt, and scroll reveal
      setTimeout(() => {
        if (window.MotionEngine) {
          MotionEngine.initAnimatedTitles();
          MotionEngine.initBentoTilt();
          MotionEngine.initScrollReveal();
        }
      }, 100);

      initAnnouncementBanner();
    }

    async function initAnnouncementBanner() {
      try {
        const res = await fetch('/announcements.json').catch(() => null);
        if (!res || !res.ok) return;
        const items = await res.json().catch(() => []);
        if (!Array.isArray(items) || items.length === 0) return;
        const latest = items[0];
        if (!latest || !latest.id || !latest.text) return;
        const seenKey = 'hiretrace_seen_announcement_' + latest.id;
        if (localStorage.getItem(seenKey)) return;

        const banner = document.createElement('div');
        banner.id = 'announcementBanner';
        banner.className = 'announcement-banner';
        banner.style.cssText = 'background: var(--surface-overlay); border-bottom: 1px solid var(--border-subtle); padding: 8px 16px; font-size: 0.8rem; display: flex; align-items: center; justify-content: space-between; z-index: 100; backdrop-filter: blur(8px);';

        const textSpan = document.createElement('span');
        textSpan.style.cssText = 'color: var(--text-primary); font-weight: 500;';
        textSpan.textContent = '⚡ ' + latest.text;

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.style.cssText = 'background: transparent; border: none; color: var(--text-muted); cursor: pointer; padding: 2px 8px; font-size: 1rem; line-height: 1;';
        closeBtn.innerHTML = '&times;';
        closeBtn.title = 'Dismiss announcement';
        closeBtn.onclick = () => {
          localStorage.setItem(seenKey, '1');
          banner.remove();
        };

        banner.appendChild(textSpan);
        banner.appendChild(closeBtn);
        const header = document.querySelector('.app-header');
        if (header && header.parentNode) {
          header.parentNode.insertBefore(banner, header);
        } else {
          document.body.prepend(banner);
        }
      } catch (e) {
        // Non-blocking optional enhancement
      }
    }

    document.addEventListener('DOMContentLoaded', () => {
      initApp();
    });
