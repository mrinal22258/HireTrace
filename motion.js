/**
 * HireTrace Motion Engine
 * Modern, robust GSAP + DOM + SVG micro-interactions.
 * Zero Three.js / raw canvas set-pieces.
 */

const MotionEngine = (() => {
  // Check prefers-reduced-motion once at init (Task D6)
  const prefersReduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let lastScrollY = 0;
  let isNavVisible = true;
  let ticking = false;

  /**
   * Floating Nav Pill Controller (navbar.tsx pattern)
   * Header alpha interpolates 0.55 -> 0.92 across first 120px of scroll (Task D4)
   */
  function initFloatingNav() {
    const header = document.querySelector('.app-header');
    if (!header) return;

    window.addEventListener('scroll', () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          const currentScrollY = window.scrollY;

          // Header depth alpha interpolation (Task D4)
          const alpha = 0.55 + Math.min(1, currentScrollY / 120) * (0.92 - 0.55);
          header.style.setProperty('--header-alpha', alpha.toFixed(3));

          if (currentScrollY <= 15) {
            header.classList.remove('floating-nav');
            header.classList.remove('nav-hidden');
          } else if (currentScrollY > lastScrollY && currentScrollY > 70) {
            // Scrolling down
            header.classList.add('floating-nav');
            header.classList.add('nav-hidden');
          } else if (currentScrollY < lastScrollY) {
            // Scrolling up
            header.classList.add('floating-nav');
            header.classList.remove('nav-hidden');
          }

          lastScrollY = Math.max(0, currentScrollY);
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  /**
   * Parallax Depth Planes (Task D1)
   */
  function initParallaxDepth() {
    if (prefersReduced) {
      document.documentElement.style.setProperty('--scroll-y', '0px');
      return;
    }
    let scrollTicking = false;
    window.addEventListener('scroll', () => {
      if (!scrollTicking) {
        window.requestAnimationFrame(() => {
          document.documentElement.style.setProperty('--scroll-y', window.scrollY + 'px');
          scrollTicking = false;
        });
        scrollTicking = true;
      }
    }, { passive: true });
    document.documentElement.style.setProperty('--scroll-y', window.scrollY + 'px');
  }

  /**
   * Word-by-word 3D Animated Headings (animated-title.tsx pattern)
   */
  function animateTitle(element) {
    if (!element || element.dataset.animated === 'true') return;
    element.dataset.animated = 'true';

    const text = element.textContent.trim();
    if (!text) return;

    const words = text.split(/\s+/);
    element.innerHTML = words.map(word => 
      `<span class="animated-word-wrap"><span class="animated-word">${escapeHtml(word)}</span></span>`
    ).join(' ');

    const wordEls = element.querySelectorAll('.animated-word');
    if (!prefersReduced && window.gsap && wordEls.length > 0) {
      gsap.to(wordEls, {
        opacity: 1,
        transform: 'translate3d(0, 0, 0) rotateY(0deg) rotateX(0deg)',
        ease: 'power2.out',
        duration: 0.6,
        stagger: 0.03
      });
    } else {
      wordEls.forEach(el => {
        el.style.opacity = '1';
        el.style.transform = 'none';
      });
    }
  }

  function initAnimatedTitles() {
    document.querySelectorAll('.animated-title').forEach(el => {
      animateTitle(el);
    });
  }

  /**
   * Bento Parallax Tilt on Cards (features.tsx BentoTilt pattern, Task D2)
   * Extended to .card, .candidate-tile, .timeline-milestone-card, .modal-dialog
   */
  function initBentoTilt(selector = '.bento-tilt, .card, .candidate-tile, .timeline-milestone-card, .modal-dialog') {
    if (prefersReduced) return;

    document.querySelectorAll(selector).forEach(card => {
      if (card.dataset.tiltInit === 'true') return;
      card.dataset.tiltInit = 'true';

      let rafId = null;
      let targetX = 0;
      let targetY = 0;

      card.addEventListener('pointermove', (e) => {
        const rect = card.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;
        const relativeX = (e.clientX - rect.left) / rect.width;
        const relativeY = (e.clientY - rect.top) / rect.height;

        // rotateX/rotateY up to +-6deg
        targetX = (relativeY - 0.5) * -12;
        targetY = (relativeX - 0.5) * 12;

        if (!rafId) {
          rafId = window.requestAnimationFrame(() => {
            rafId = null;
            card.style.transform = `perspective(1200px) rotateX(${targetX.toFixed(2)}deg) rotateY(${targetY.toFixed(2)}deg) translateZ(20px)`;
          });
        }
      }, { passive: true });

      card.addEventListener('pointerleave', () => {
        if (rafId) {
          window.cancelAnimationFrame(rafId);
          rafId = null;
        }
        card.style.transform = 'perspective(1200px) rotateX(0deg) rotateY(0deg) translateZ(0px)';
      });
    });
  }

  /**
   * Scroll-reveal with ScrollTrigger / IntersectionObserver (Task D3)
   */
  function initScrollReveal() {
    if (prefersReduced) return;

    if (window.gsap && window.ScrollTrigger) {
      gsap.registerPlugin(ScrollTrigger);
      ScrollTrigger.batch('.reveal-on-scroll, section, .card', {
        onEnter: batch => gsap.to(batch, {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.6,
          stagger: 0.06,
          ease: 'power2.out',
          overwrite: true
        }),
        start: 'top 85%',
        once: true
      });
    }
  }

  /**
   * Animated Number Counter
   */
  function animateNumber(elementId, targetValue, duration = 1.0) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const target = Number(targetValue) || 0;
    if (window.gsap) {
      const obj = { val: 0 };
      gsap.to(obj, {
        val: target,
        duration: duration,
        ease: 'power2.out',
        onUpdate: () => {
          el.textContent = Math.round(obj.val).toLocaleString();
        }
      });
    } else {
      el.textContent = target.toLocaleString();
    }
  }

  /**
   * Contained Mascot Avatar Entrance & Playful Replay
   */
  function initMascot(avatarId = 'heroMascotAvatar') {
    const avatar = document.getElementById(avatarId);
    if (!avatar) return;

    if (window.gsap) {
      gsap.fromTo(avatar, 
        { scale: 0.8, opacity: 0, y: 10 },
        { scale: 1, opacity: 1, y: 0, duration: 0.45, ease: 'back.out(1.7)' }
      );
    }

    avatar.addEventListener('click', () => {
      if (window.gsap) {
        gsap.timeline()
          .to(avatar, { scale: 1.15, rotate: 6, duration: 0.15, ease: 'power1.out' })
          .to(avatar, { rotate: -6, duration: 0.15, ease: 'power1.inOut' })
          .to(avatar, { scale: 1, rotate: 0, duration: 0.2, ease: 'back.out(2)' });
      }
    });
  }

  /**
   * SVG Evidence & Career Timeline (replaces 3D Spline Canvas)
   */
  function renderEvidenceTimeline(containerId, milestones, currentProgress = 0.35) {
    const container = document.getElementById(containerId);
    if (!container || !milestones || milestones.length === 0) return;

    const activeIndex = Math.min(
      milestones.length - 1,
      Math.floor(currentProgress * milestones.length)
    );

    let html = `
      <div class="evidence-timeline-container">
        <div class="timeline-milestones-track">
    `;

    milestones.forEach((m, idx) => {
      const isActive = idx === activeIndex;
      const isPast = idx <= activeIndex;
      const statusBadge = m.status === 'verified'
        ? '<span class="badge badge-strong">Corroborated</span>'
        : '<span class="badge badge-warning">Attention Required</span>';

      html += `
        <div class="timeline-milestone-card bento-tilt ${isActive ? 'active' : ''}" data-index="${idx}" onclick="MotionEngine.selectTimelineMilestone(${idx})">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.4rem;">
            <span style="font-size: 0.72rem; font-weight: 700; color: var(--accent); font-family: var(--font-mono);">${escapeHtml(m.date || '')}</span>
            ${statusBadge}
          </div>
          <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-primary); margin-bottom: 0.25rem;">${escapeHtml(m.title || '')}</div>
          <div style="font-size: 0.76rem; color: var(--text-secondary); margin-bottom: 0.4rem;">${escapeHtml(m.role || '')}</div>
          <div style="font-size: 0.73rem; color: var(--text-muted); line-height: 1.35;">${escapeHtml(m.detail || '')}</div>
        </div>
      `;
    });

    html += `
        </div>
      </div>
    `;

    container.innerHTML = html;
    initBentoTilt('.timeline-milestone-card');

    // Update active label and badge if present
    const label = document.getElementById('splineMilestoneLabel');
    const badge = document.getElementById('splineStatusBadge');
    const m = milestones[activeIndex];
    if (label && m) label.textContent = `${m.title} (${m.date})`;
    if (badge && m) {
      badge.textContent = m.status === 'verified' ? "Corroborated" : "Attention Required";
      badge.className = m.status === 'verified' ? "badge badge-strong" : "badge badge-warning";
    }
  }

  function selectTimelineMilestone(index) {
    const slider = document.getElementById('splineSlider') || document.getElementById('splineTimelineSlider');
    const cards = document.querySelectorAll('.timeline-milestone-card');
    cards.forEach((c, idx) => {
      c.classList.toggle('active', idx === index);
      if (idx === index) {
        c.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
    });

    if (window.AppState && window.AppState.activeMilestonesData) {
      const m = window.AppState.activeMilestonesData[index];
      const label = document.getElementById('splineMilestoneLabel');
      const badge = document.getElementById('splineStatusBadge');
      if (label && m) label.textContent = `${m.title} (${m.date})`;
      if (badge && m) {
        badge.textContent = m.status === 'verified' ? "Corroborated" : "Attention Required";
        badge.className = m.status === 'verified' ? "badge badge-strong" : "badge badge-warning";
      }
      if (slider) {
        slider.value = Math.round((index / Math.max(1, window.AppState.activeMilestonesData.length - 1)) * 100);
      }
    }
  }

  /**
   * Lightweight SVG Evidence Cross-Source Verification Graph (replaces Force Canvas)
   */
  function renderEvidenceGraph(containerId, sources = null) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const defaultSources = [
      { id: "cv", label: "Curriculum Vitae", color: "var(--accent)", status: "verified", angle: -Math.PI / 2 },
      { id: "transcript", label: "Interview Transcript", color: "var(--warning)", status: "unresolved", angle: -Math.PI / 6 },
      { id: "assessment", label: "Code Assessment", color: "var(--success)", status: "verified", angle: (Math.PI * 2) / 5 },
      { id: "rfc", label: "Architecture RFC", color: "var(--success)", status: "verified", angle: (Math.PI * 4) / 5 },
      { id: "jd", label: "Target Requisition", color: "var(--text-secondary)", status: "verified", angle: (Math.PI * 7) / 6 }
    ];

    const sourceList = sources || defaultSources;
    const width = 640;
    const height = 240;
    const cx = width / 2;
    const cy = height / 2;
    const rx = 230;
    const ry = 85;

    let svgHtml = `
      <svg class="evidence-svg-graph" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id="nodeGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
    `;

    // Connecting lines
    sourceList.forEach(s => {
      const nx = cx + Math.cos(s.angle) * rx;
      const ny = cy + Math.sin(s.angle) * ry;
      const strokeColor = s.status === 'verified' ? 'var(--success)' : 'var(--warning)';
      svgHtml += `
        <line class="svg-edge-line" x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" 
              stroke="${strokeColor}" stroke-width="2" stroke-opacity="0.65" />
      `;
    });

    // Central candidate node
    svgHtml += `
      <g class="svg-node-group" transform="translate(${cx}, ${cy})">
        <circle r="22" fill="var(--bg-surface)" stroke="var(--accent)" stroke-width="3" filter="url(#nodeGlow)" />
        <circle r="14" fill="var(--accent)" />
        <text y="34" text-anchor="middle" fill="var(--text-primary)" font-size="11" font-weight="700" font-family="var(--font-display)">
          Assessment Core
        </text>
      </g>
    `;

    // Perimeter source nodes
    sourceList.forEach((s, idx) => {
      const nx = cx + Math.cos(s.angle) * rx;
      const ny = cy + Math.sin(s.angle) * ry;
      const nodeFill = s.status === 'verified' ? 'var(--success)' : 'var(--warning)';

      svgHtml += `
        <g class="svg-node-group" transform="translate(${nx}, ${cy + Math.sin(s.angle) * ry})" 
           onmouseenter="MotionEngine.showGraphTooltip(event, '${escapeHtml(s.label)}', '${s.status}')"
           onmouseleave="MotionEngine.hideGraphTooltip()">
          <circle r="18" fill="var(--bg-surface)" stroke="${nodeFill}" stroke-width="2.5" filter="url(#nodeGlow)" />
          <circle r="9" fill="${nodeFill}" />
          <text y="${ny > cy ? 26 : -22}" text-anchor="middle" fill="var(--text-primary)" font-size="11" font-weight="600" font-family="var(--font-sans)">
            ${escapeHtml(s.label)}
          </text>
        </g>
      `;
    });

    svgHtml += `</svg>`;
    container.innerHTML = svgHtml;
  }

  function showGraphTooltip(e, label, status) {
    const tip = document.getElementById('graphTooltip');
    if (!tip) return;
    tip.style.display = 'block';
    tip.innerHTML = `<strong>${escapeHtml(label)}</strong>: ${status === 'verified' ? '✓ Corroborated' : '⚠ Discrepancy detected'}`;
    const rect = tip.parentElement.getBoundingClientRect();
    tip.style.left = `${Math.min(rect.width - 200, Math.max(10, e.clientX - rect.left + 10))}px`;
    tip.style.top = `${Math.min(rect.height - 40, Math.max(10, e.clientY - rect.top - 30))}px`;
  }

  function hideGraphTooltip() {
    const tip = document.getElementById('graphTooltip');
    if (tip) tip.style.display = 'none';
  }

  /**
   * Leaderboard 3D Showcase Carousel (replaces Cylindrical Arc Canvas)
   */
  function renderLeaderboardShowcase(containerId, candidates = []) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!candidates || candidates.length === 0) {
      container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 3rem;">No candidates available for showcase.</div>`;
      return;
    }

    let cardsHtml = `
      <div class="leaderboard-showcase-container">
        <div class="leaderboard-carousel-track" id="leaderboardCarouselTrack">
    `;

    candidates.forEach((c, idx) => {
      const quad = c.quadrant || 'REVIEW REQUIRED';
      const badgeCls = getBadgeClass(quad);
      const fit = c.role_fit_score !== null && c.role_fit_score !== undefined ? Number(c.role_fit_score).toFixed(1) : '--';
      const cons = c.evidence_consistency_score !== null && c.evidence_consistency_score !== undefined ? Number(c.evidence_consistency_score).toFixed(1) : '--';
      const initials = (c.name || 'C').split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase();

      cardsHtml += `
        <div class="leaderboard-carousel-card bento-tilt" data-index="${idx}">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <div style="width: 44px; height: 44px; border-radius: 50%; background: var(--accent); color: var(--bg-surface); display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1rem; font-family: var(--font-display);">
              ${initials}
            </div>
            <span class="badge ${badgeCls}">${escapeHtml(quad)}</span>
          </div>
          <div style="font-weight: 700; font-size: 1.1rem; color: var(--text-primary); margin-bottom: 0.2rem;">
            ${escapeHtml(c.name || c.candidate_id)}
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 1rem;">
            ${escapeHtml(c.target_role || 'Senior Software Engineer')}
          </div>
          <div style="background: var(--bg-surface-subtle); border-radius: var(--radius-sm); padding: 0.75rem; display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 1rem;">
            <div>
              <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Role Fit</div>
              <div style="font-family: var(--font-mono); font-weight: 700; font-size: 1.15rem; color: var(--text-primary);">${fit}</div>
            </div>
            <div>
              <div style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">Consistency</div>
              <div style="font-family: var(--font-mono); font-weight: 700; font-size: 1.15rem; color: var(--text-primary);">${cons}</div>
            </div>
          </div>
          <a class="btn btn-secondary btn-sm" href="#/candidates/${encodeURIComponent(c.candidate_id)}" style="width: 100%; justify-content: center;">
            Inspect Dossier →
          </a>
        </div>
      `;
    });

    cardsHtml += `
        </div>
      </div>
    `;

    container.innerHTML = cardsHtml;
    initBentoTilt('.leaderboard-carousel-card');

    // Drag-to-scroll interaction
    const track = document.getElementById('leaderboardCarouselTrack');
    if (track) {
      let isDown = false;
      let startX;
      let scrollLeft;

      track.addEventListener('mousedown', (e) => {
        isDown = true;
        startX = e.pageX - track.offsetLeft;
        scrollLeft = track.scrollLeft;
      });

      track.addEventListener('mouseleave', () => { isDown = false; });
      track.addEventListener('mouseup', () => { isDown = false; });

      track.addEventListener('mousemove', (e) => {
        if (!isDown) return;
        e.preventDefault();
        const x = e.pageX - track.offsetLeft;
        const walk = (x - startX) * 1.5;
        track.scrollLeft = scrollLeft - walk;
      });
    }
  }

  /**
   * SVG Radial Progress Ring for Calibration Orb (Honest ECE error representation)
   */
  function renderCalibrationRing(containerId, eceValue = 0.2395, isPermitted = false) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Expected Calibration Error (ECE ~24%)
    const errorPct = Number(eceValue || 0.2395) <= 1 ? Math.round(Number(eceValue || 0.2395) * 100) : Math.round(Number(eceValue));
    const radius = 54;
    const circumference = 2 * Math.PI * radius; // ~339.29
    const offset = circumference * (1 - errorPct / 100);
    const strokeColor = 'var(--warning)';

    container.innerHTML = `
      <div class="calibration-ring-container" title="Expected Calibration Error: ${errorPct}% bin deviation (Weakly Calibrated)">
        <svg class="calibration-ring-svg" viewBox="0 0 124 124">
          <circle class="calibration-ring-bg" cx="62" cy="62" r="${radius}" />
          <circle class="calibration-ring-progress" id="calibrationRingProgress" 
                  cx="62" cy="62" r="${radius}" 
                  stroke="${strokeColor}" 
                  style="stroke-dasharray: ${circumference}; stroke-dashoffset: ${circumference};" />
        </svg>
        <div class="calibration-ring-center">
          <div class="calibration-ring-val" id="calibrationRingVal" style="color: var(--warning-text); font-size: 1.15rem;">0%</div>
          <div class="calibration-ring-lbl" style="color: var(--warning-text); font-size: 0.58rem; letter-spacing: 0.02em;">ECE Error</div>
        </div>
      </div>
    `;

    // Animate stroke and number
    setTimeout(() => {
      const ring = document.getElementById('calibrationRingProgress');
      if (ring) {
        ring.style.strokeDashoffset = offset.toFixed(2);
      }
      animateNumber('calibrationRingVal', errorPct, 1.2);
      const valEl = document.getElementById('calibrationRingVal');
      if (valEl) {
        setTimeout(() => {
          valEl.textContent = `${errorPct}%`;
        }, 1250);
      }
    }, 50);
  }

  function getBadgeClass(quadrant) {
    const q = (quadrant || '').toUpperCase();
    if (q === 'LEAD CANDIDATE' || q === 'STRONG MATCH') return 'badge-strong';
    if (q === 'POTENTIAL / PROBE GAPS') return 'badge-neutral';
    if (q === 'HIGH RISK / CONTRADICTIONS') return 'badge-danger';
    return 'badge-warning';
  }

  const escapeHtml = (typeof window !== 'undefined' && window.escapeHtml) ? window.escapeHtml : function(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  };

  return {
    initFloatingNav,
    initParallaxDepth,
    initScrollReveal,
    initAnimatedTitles,
    animateTitle,
    initBentoTilt,
    animateNumber,
    initMascot,
    renderEvidenceTimeline,
    selectTimelineMilestone,
    renderEvidenceGraph,
    showGraphTooltip,
    hideGraphTooltip,
    renderLeaderboardShowcase,
    renderCalibrationRing
  };
})();

window.MotionEngine = MotionEngine;
