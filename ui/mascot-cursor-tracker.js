/**
 * mascot-cursor-tracker.js
 *
 * Dependency-free interactive mascot cursor tracker for HireTrace.
 * Supports:
 * - rAF-coalesced pointer tracking with cached bounding box
 * - 28-degree sector hysteresis preventing boundary flicker
 * - Dual-layer 110ms cross-fading cell swaps
 * - Sub-pixel parallax lean (max +-3px)
 * - Window exit, blur, and tab visibility reset to center (220ms ease)
 * - 5s idle behavior cycle (C -> N -> C -> W -> C)
 * - Touch & keyboard accessibility (tabindex="0", Arrow keys, Enter/Space poke)
 * - Full prefers-reduced-motion support
 */
(function (global) {
  "use strict";

  const CELL_ORDER = ["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"];
  const CELL_POSITION = {
    NW: "0% 0%",   N: "50% 0%",   NE: "100% 0%",
    W:  "0% 50%",  C: "50% 50%",  E: "100% 50%",
    SW: "0% 100%", S: "50% 100%", SE: "100% 100%"
  };

  const CELL_ANGLES = {
    E: 0, SE: 45, S: 90, SW: 135, W: 180, NW: 225, N: 270, NE: 315
  };

  const REACTION_DURATION_MS = 500;
  const IDLE_DELAY_MS = 5000;
  const IDLE_STEP_MS = 2500;
  const IDLE_CYCLE = ["C", "N", "C", "W", "C"];

  function buildLayer(sheetUrl, size, label) {
    const layer = document.createElement("div");
    layer.style.position = "absolute";
    layer.style.inset = "0";
    layer.style.width = size + "px";
    layer.style.height = size + "px";
    layer.style.backgroundImage = 'url("' + sheetUrl + '")';
    layer.style.backgroundSize = "300% 300%";
    layer.style.backgroundRepeat = "no-repeat";
    layer.style.backgroundPosition = CELL_POSITION.C;
    layer.style.pointerEvents = "none";
    if (label) layer.setAttribute("aria-hidden", "true");
    return layer;
  }

  function mount(container, options) {
    if (!container) return null;
    const opts = Object.assign(
      { size: 104, label: "mascot", className: "" },
      options || {}
    );
    if (!opts.directions || !opts.reactions) {
      console.error("MascotCursorTracker.mount: 'directions' and 'reactions' sheet URLs are required.");
      return null;
    }

    const deadZone = Math.max(20, opts.size * 0.3);
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const finePointer = window.matchMedia("(pointer: fine)").matches;

    container.innerHTML = "";
    container.style.position = "relative";
    container.style.width = opts.size + "px";
    container.style.height = opts.size + "px";
    container.style.cursor = "pointer";
    container.setAttribute("role", "img");
    container.setAttribute("tabindex", "0");
    container.setAttribute("aria-label", opts.label);
    if (opts.className) container.className += " " + opts.className;

    // Sprite wrapper layer for sub-pixel parallax lean
    const spriteWrap = document.createElement("div");
    spriteWrap.style.position = "absolute";
    spriteWrap.style.inset = "0";
    spriteWrap.style.width = "100%";
    spriteWrap.style.height = "100%";
    spriteWrap.style.pointerEvents = "none";
    spriteWrap.style.willChange = reduceMotion ? "auto" : "transform";
    container.appendChild(spriteWrap);

    // Dual stacked direction layers for cross-fading cell swaps
    const dirLayerA = buildLayer(opts.directions, opts.size, opts.label);
    const dirLayerB = buildLayer(opts.directions, opts.size, opts.label);
    dirLayerA.style.opacity = "1";
    dirLayerB.style.opacity = "0";
    spriteWrap.appendChild(dirLayerA);
    spriteWrap.appendChild(dirLayerB);

    let currentDirLayer = dirLayerA;
    let incomingDirLayer = dirLayerB;

    // Reaction layer (poke)
    const reactionsLayer = buildLayer(opts.reactions, opts.size, opts.label);
    reactionsLayer.style.opacity = "0";
    reactionsLayer.style.transition = "opacity 120ms ease";
    reactionsLayer.style.zIndex = "2";
    spriteWrap.appendChild(reactionsLayer);

    // Cached geometry (Task A2.2)
    let cachedRect = null;
    let cachedCenterX = 0;
    let cachedCenterY = 0;

    function updateRect() {
      cachedRect = container.getBoundingClientRect();
      cachedCenterX = cachedRect.left + cachedRect.width / 2;
      cachedCenterY = cachedRect.top + cachedRect.height / 2;
    }
    updateRect();

    let resizeObserver = null;
    if ("ResizeObserver" in window) {
      resizeObserver = new ResizeObserver(() => {
        updateRect();
      });
      resizeObserver.observe(container);
    }

    // State tracking
    let activeCell = "C";
    let isIdle = false;
    let idleIndex = 0;
    let idleTimer = null;
    let idleStepTimer = null;
    let reactionTimer = null;

    // Set active cell with dual-layer cross-fade (Task A2.4)
    function setActiveCell(newCell, immediate) {
      if (newCell === activeCell && !immediate) return;
      activeCell = newCell;

      if (reduceMotion || immediate) {
        currentDirLayer.style.transition = "none";
        incomingDirLayer.style.transition = "none";
        currentDirLayer.style.backgroundPosition = CELL_POSITION[newCell];
        currentDirLayer.style.opacity = "1";
        incomingDirLayer.style.opacity = "0";
        return;
      }

      incomingDirLayer.style.backgroundPosition = CELL_POSITION[newCell];
      incomingDirLayer.style.transition = "opacity 110ms cubic-bezier(0.4, 0, 0.2, 1)";
      currentDirLayer.style.transition = "opacity 110ms cubic-bezier(0.4, 0, 0.2, 1)";
      incomingDirLayer.style.opacity = "1";
      currentDirLayer.style.opacity = "0";

      // Swap active layer reference
      const temp = currentDirLayer;
      currentDirLayer = incomingDirLayer;
      incomingDirLayer = temp;
    }

    // Sub-pixel lean (Task A2.5)
    function applyLean(dx, dy, smooth) {
      if (reduceMotion) {
        spriteWrap.style.transform = "none";
        return;
      }
      const leanX = Math.max(-1, Math.min(1, dx / 260)) * 3;
      const leanY = Math.max(-1, Math.min(1, dy / 260)) * 3;
      if (smooth) {
        spriteWrap.style.transition = "transform 220ms cubic-bezier(0.4, 0, 0.2, 1)";
      } else {
        spriteWrap.style.transition = "none";
      }
      spriteWrap.style.transform = "translate3d(" + leanX.toFixed(2) + "px, " + leanY.toFixed(2) + "px, 0)";
    }

    // Angle to cell with 28-degree hysteresis (Task A2.3)
    function computeTargetCell(dx, dy) {
      const dist = Math.hypot(dx, dy);
      if (dist < deadZone) {
        if (activeCell !== "C" && dist < deadZone * 0.85) {
          return "C";
        }
        return activeCell === "C" ? "C" : activeCell;
      }

      const deg = (Math.atan2(dy, dx) * 180) / Math.PI;
      const normDeg = (deg + 360) % 360;
      const bucket = Math.round(normDeg / 45) % 8;
      const candidate = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"][bucket];

      if (activeCell === "C") {
        return candidate;
      }

      if (candidate !== activeCell) {
        const centerDeg = CELL_ANGLES[activeCell] !== undefined ? CELL_ANGLES[activeCell] : 0;
        const angDist = Math.abs(((normDeg - centerDeg + 540) % 360) - 180);
        // Require angular distance past boundary to exceed 28 degrees
        if (angDist > 28) {
          return candidate;
        }
      }
      return activeCell;
    }

    // Pointer input rAF coalescence (Task A2.1)
    let lastX = 0;
    let lastY = 0;
    let rafScheduled = false;

    function onPointerMove(e) {
      lastX = e.clientX;
      lastY = e.clientY;
      cancelIdleCycle();

      if (!rafScheduled) {
        rafScheduled = true;
        requestAnimationFrame(() => {
          rafScheduled = false;
          if (!cachedRect) updateRect();
          const dx = lastX - cachedCenterX;
          const dy = lastY - cachedCenterY;
          const target = computeTargetCell(dx, dy);
          setActiveCell(target);
          applyLean(dx, dy, false);
        });
      }
    }

    // Exit state reset (Task A2.6)
    function resetToCenter() {
      cancelIdleCycle();
      setActiveCell("C");
      applyLean(0, 0, true);
    }

    // Idle cycle (Task A2.7)
    function scheduleIdleCycle() {
      if (reduceMotion) return;
      clearTimeout(idleTimer);
      clearInterval(idleStepTimer);
      idleTimer = setTimeout(() => {
        isIdle = true;
        idleIndex = 0;
        idleStepTimer = setInterval(() => {
          idleIndex = (idleIndex + 1) % IDLE_CYCLE.length;
          setActiveCell(IDLE_CYCLE[idleIndex]);
        }, IDLE_STEP_MS);
      }, IDLE_DELAY_MS);
    }

    function cancelIdleCycle() {
      clearTimeout(idleTimer);
      clearInterval(idleStepTimer);
      if (isIdle) {
        isIdle = false;
        setActiveCell("C");
      }
      scheduleIdleCycle();
    }

    // Poke reaction
    function onPoke() {
      const randomCell = CELL_ORDER[Math.floor(Math.random() * CELL_ORDER.length)];
      reactionsLayer.style.backgroundPosition = CELL_POSITION[randomCell];
      reactionsLayer.style.opacity = "1";

      if (!reduceMotion) {
        container.style.transition = "transform 90ms cubic-bezier(0.34, 1.56, 0.64, 1)";
        container.style.transform = "scale(0.94)";
        requestAnimationFrame(() => {
          container.style.transform = "scale(1)";
        });
      }

      clearTimeout(reactionTimer);
      reactionTimer = setTimeout(() => {
        reactionsLayer.style.opacity = "0";
      }, REACTION_DURATION_MS);
    }

    // Keyboard controls (Task A2.8)
    function onKeyDown(e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onPoke();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        cancelIdleCycle();
        setActiveCell("N");
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        cancelIdleCycle();
        setActiveCell("S");
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        cancelIdleCycle();
        setActiveCell("W");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        cancelIdleCycle();
        setActiveCell("E");
      }
    }

    // Bind listeners
    if (finePointer) {
      window.addEventListener("pointermove", onPointerMove, { passive: true });
    }
    window.addEventListener("resize", updateRect, { passive: true });
    window.addEventListener("scroll", updateRect, { passive: true });
    document.addEventListener("pointerleave", resetToCenter, { passive: true });
    window.addEventListener("blur", resetToCenter);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) resetToCenter();
    });

    container.addEventListener("click", onPoke);
    container.addEventListener("keydown", onKeyDown);
    container.addEventListener("touchstart", onPoke, { passive: true });

    scheduleIdleCycle();

    return {
      destroy() {
        if (finePointer) {
          window.removeEventListener("pointermove", onPointerMove);
        }
        window.removeEventListener("resize", updateRect);
        window.removeEventListener("scroll", updateRect);
        document.removeEventListener("pointerleave", resetToCenter);
        window.removeEventListener("blur", resetToCenter);
        container.removeEventListener("click", onPoke);
        container.removeEventListener("keydown", onKeyDown);
        container.removeEventListener("touchstart", onPoke);

        if (resizeObserver) resizeObserver.disconnect();
        clearTimeout(reactionTimer);
        clearTimeout(idleTimer);
        clearInterval(idleStepTimer);
      }
    };
  }

  global.MascotCursorTracker = { mount: mount };
})(window);
