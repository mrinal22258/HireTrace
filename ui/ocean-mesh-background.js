/**
 * ocean-mesh-background.js
 *
 * Site-wide WebGL2 living surface mesh background for HireTrace.
 * Dual uniform palettes (Ocean Light <-> Abyssal Pure Black), 600ms smooth theme tween,
 * context loss resilience, auto-pausing on background/off-screen, and reduced motion safety.
 */
(function (global) {
  "use strict";

  const ZOOM_FACTOR = 0.3;
  const BASE_WAVE_AMPLITUDE = 0.2;
  const RANDOM_WAVE_FACTOR = 0.15;
  const WAVE_FREQUENCY = 4.0;
  const TIME_FACTOR = 0.22;
  const BASE_SWIRL_STRENGTH = 0.9;
  const SWIRL_TIME_MULT = 5.0;
  const NOISE_SWIRL_FACTOR = 0.18;

  // 10 key stops for light and dark ramps
  const lightHexes = ['#04262F', '#063A4C', '#084C63', '#0A6580', '#0E7C9B', '#2E90B4', '#5FAECB', '#9FCBDE', '#D8E8F0', '#F2F7FA'];
  const darkHexes = ['#000000', '#020609', '#041018', '#061C29', '#082C3E', '#0A4055', '#0E5F7C', '#1789AE', '#23AACF', '#35C6E8'];

  function hexToRgb(h) {
    h = h.replace(/^#/, '');
    const num = parseInt(h, 16);
    return [(num >> 16 & 255) / 255, (num >> 8 & 255) / 255, (num & 255) / 255];
  }

  function createPaletteArray(hexList, count) {
    const rgbStops = hexList.map(hexToRgb);
    const nSeg = rgbStops.length - 1;
    const out = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const t = i / (count - 1);
      const seg = Math.min(Math.floor(t * nSeg), nSeg - 1);
      const subT = (t * nSeg) - seg;
      const c0 = rgbStops[seg];
      const c1 = rgbStops[seg + 1];
      out[i * 3 + 0] = c0[0] + (c1[0] - c0[0]) * subT;
      out[i * 3 + 1] = c0[1] + (c1[1] - c0[1]) * subT;
      out[i * 3 + 2] = c0[2] + (c1[2] - c0[2]) * subT;
    }
    return out;
  }

  const palLightData = createPaletteArray(lightHexes, 20);
  const palDarkData = createPaletteArray(darkHexes, 20);

  const vertexShaderSource = `#version 300 es
precision mediump float;
in vec2 aPosition;
void main() { gl_Position = vec4(aPosition, 0.0, 1.0); }`;

  function buildFragmentShader(octaves) {
    return `#version 300 es
precision highp float;
out vec4 outColor;

uniform vec2 uResolution;
uniform float uTime;
uniform vec3 uPalA[20];
uniform vec3 uPalB[20];
uniform float uMix;

vec3 permute(vec3 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }

float noise2D(vec2 v) {
  const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
  vec2 i = floor(v + dot(v, C.yy));
  vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
  vec4 x12 = x0.xyxy + C.xxzz;
  x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
  m = m * m; m = m * m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0;
  vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5);
  vec3 a0 = x - ox;
  m *= 1.792843 - 0.853734 * (a0 * a0 + h * h);
  vec3 g;
  g.x  = a0.x  * x0.x + h.x  * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}

float fbm(vec2 st) {
  float value = 0.0;
  float amplitude = 0.5;
  float freq = 1.0;
  for (int i = 0; i < ${octaves}; i++) {
    value += amplitude * noise2D(st * freq);
    freq *= 2.0;
    amplitude *= 0.5;
  }
  return value;
}

void main() {
  vec2 uv = (gl_FragCoord.xy / uResolution.xy) * 2.0 - 1.0;
  uv.x *= uResolution.x / uResolution.y;
  uv *= float(${ZOOM_FACTOR});

  float t = uTime * float(${TIME_FACTOR});
  float waveAmp = float(${BASE_WAVE_AMPLITUDE}) + float(${RANDOM_WAVE_FACTOR}) * noise2D(vec2(t, 27.7));
  float waveX = waveAmp * sin(uv.y * float(${WAVE_FREQUENCY}) + t);
  float waveY = waveAmp * sin(uv.x * float(${WAVE_FREQUENCY}) - t);
  uv.x += waveX;
  uv.y += waveY;

  float r = length(uv);
  float angle = atan(uv.y, uv.x);
  float swirlStrength = float(${BASE_SWIRL_STRENGTH}) * (1.0 - smoothstep(0.0, 1.0, r));
  angle += swirlStrength * sin(uTime + r * float(${SWIRL_TIME_MULT}));
  uv = vec2(cos(angle), sin(angle)) * r;

  float n = fbm(uv);
  float swirlEffect = float(${NOISE_SWIRL_FACTOR}) * sin(t + n * 3.0);
  n += swirlEffect;

  float noiseVal = 0.5 * (n + 1.0);
  float idx = clamp(noiseVal, 0.0, 1.0) * 19.0;
  int iLow = int(floor(idx));
  int iHigh = int(min(float(iLow + 1), 19.0));
  float f = fract(idx);

  vec3 colLow = mix(uPalA[iLow], uPalB[iLow], uMix);
  vec3 colHigh = mix(uPalA[iHigh], uPalB[iHigh], uMix);
  vec3 color = mix(colLow, colHigh, f);

  if (iLow == 0 && iHigh == 0) {
    outColor = vec4(color, 0.0);
  } else {
    outColor = vec4(color, 1.0);
  }
}
`;
  }

  function createShaderProgram(gl, vsSource, fsSource) {
    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, vsSource);
    gl.compileShader(vs);
    if (!gl.getShaderParameter(vs, gl.COMPILE_STATUS)) {
      console.error("Vertex shader compile error:", gl.getShaderInfoLog(vs));
      return null;
    }
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, fsSource);
    gl.compileShader(fs);
    if (!gl.getShaderParameter(fs, gl.COMPILE_STATUS)) {
      console.error("Fragment shader compile error:", gl.getShaderInfoLog(fs));
      return null;
    }
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.error("Shader program link error:", gl.getProgramInfoLog(program));
      return null;
    }
    return program;
  }

  function isDarkThemeActive() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  function mount(canvas, options) {
    if (!canvas) return null;
    const opts = Object.assign({ quality: "standard" }, options || {});
    const octaves = opts.quality === "high" ? 10 : 6;
    const maxDpr = opts.quality === "high" ? 2.0 : 1.5;

    let gl = canvas.getContext("webgl2", { alpha: true });
    if (!gl) {
      console.warn("OceanMeshBackground: WebGL2 unavailable. Activating CSS fallback.");
      canvas.style.backgroundImage = "var(--mesh-gradient)";
      canvas.style.backgroundSize = "200% 200%";
      canvas.style.animation = "meshDrift 20s ease-in-out infinite alternate";
      return {
        destroy() {}
      };
    }

    let program, vao, vbo;
    let uResolutionLoc, uTimeLoc, uPalALoc, uPalBLoc, uMixLoc;
    let rafId = null;
    let isPaused = false;
    let destroyed = false;
    const startTime = performance.now();

    // Theme mix animation state
    let currentMix = isDarkThemeActive() ? 1.0 : 0.0;
    let targetMix = currentMix;
    let mixStartTime = 0;
    let mixFrom = currentMix;
    const MIX_DURATION_MS = 600;

    function initGL() {
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.clearColor(0, 0, 0, 0);

      program = createShaderProgram(gl, vertexShaderSource, buildFragmentShader(octaves));
      if (!program) return false;
      gl.useProgram(program);

      const quad = new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]);
      vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      vbo = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
      gl.bufferData(gl.ARRAY_BUFFER, quad, gl.STATIC_DRAW);

      const aPosition = gl.getAttribLocation(program, "aPosition");
      gl.enableVertexAttribArray(aPosition);
      gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0);

      uResolutionLoc = gl.getUniformLocation(program, "uResolution");
      uTimeLoc = gl.getUniformLocation(program, "uTime");
      uPalALoc = gl.getUniformLocation(program, "uPalA");
      uPalBLoc = gl.getUniformLocation(program, "uPalB");
      uMixLoc = gl.getUniformLocation(program, "uMix");

      gl.uniform3fv(uPalALoc, palLightData);
      gl.uniform3fv(uPalBLoc, palDarkData);
      gl.uniform1f(uMixLoc, currentMix);
      return true;
    }

    if (!initGL()) return null;

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
      const w = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      const h = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
    }

    function updateThemeMix(now) {
      if (currentMix !== targetMix) {
        const progress = Math.min(1.0, (now - mixStartTime) / MIX_DURATION_MS);
        // ease-in-out cubic
        const ease = progress < 0.5
          ? 4 * progress * progress * progress
          : 1 - Math.pow(-2 * progress + 2, 3) / 2;
        currentMix = mixFrom + (targetMix - mixFrom) * ease;
        if (progress >= 1.0) currentMix = targetMix;
      }
    }

    function draw(elapsedSeconds, now) {
      if (!gl || gl.isContextLost()) return;
      resize();
      updateThemeMix(now || performance.now());

      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.bindVertexArray(vao);
      gl.uniform2f(uResolutionLoc, canvas.width, canvas.height);
      gl.uniform1f(uTimeLoc, elapsedSeconds);
      gl.uniform1f(uMixLoc, currentMix);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function frame(now) {
      if (destroyed || isPaused) return;
      draw((now - startTime) * 0.001, now);
      if (!reduceMotion) {
        rafId = requestAnimationFrame(frame);
      }
    }

    function startLoop() {
      if (destroyed || isPaused || reduceMotion) return;
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(frame);
    }

    function stopLoop() {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
    }

    if (reduceMotion) {
      resize();
      draw(6.0, performance.now());
    } else {
      startLoop();
    }

    // Theme MutationObserver
    function setTargetTheme(isDark) {
      const newTarget = isDark ? 1.0 : 0.0;
      if (targetMix !== newTarget) {
        targetMix = newTarget;
        mixFrom = currentMix;
        mixStartTime = performance.now();
        if (reduceMotion) {
          currentMix = targetMix;
          draw(6.0, performance.now());
        }
      }
    }

    const themeObserver = new MutationObserver(() => {
      setTargetTheme(isDarkThemeActive());
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"]
    });

    const onCustomThemeChange = (e) => {
      const isDark = e && e.detail && e.detail.theme === "dark";
      setTargetTheme(isDark !== undefined ? isDark : isDarkThemeActive());
    };
    document.addEventListener("hiretrace:themechange", onCustomThemeChange);

    // Auto-pause when page hidden
    const onVisibilityChange = () => {
      if (document.hidden) {
        stopLoop();
      } else if (!isPaused) {
        startLoop();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    // IntersectionObserver to pause when off-screen
    const intersectionObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry && !entry.isIntersecting) {
        isPaused = true;
        stopLoop();
      } else {
        isPaused = false;
        if (!document.hidden) startLoop();
      }
    }, { threshold: 0.01 });
    intersectionObserver.observe(canvas);

    // Context loss handlers
    const onContextLost = (e) => {
      e.preventDefault();
      console.warn("OceanMeshBackground: WebGL context lost. Pausing.");
      stopLoop();
    };

    const onContextRestored = () => {
      console.info("OceanMeshBackground: WebGL context restored. Rebuilding.");
      if (initGL()) {
        resize();
        if (!reduceMotion && !isPaused && !document.hidden) {
          startLoop();
        } else {
          draw(6.0, performance.now());
        }
      }
    };

    canvas.addEventListener("webglcontextlost", onContextLost);
    canvas.addEventListener("webglcontextrestored", onContextRestored);

    const onResize = () => resize();
    window.addEventListener("resize", onResize, { passive: true });

    return {
      destroy() {
        destroyed = true;
        stopLoop();
        themeObserver.disconnect();
        intersectionObserver.disconnect();
        document.removeEventListener("hiretrace:themechange", onCustomThemeChange);
        document.removeEventListener("visibilitychange", onVisibilityChange);
        window.removeEventListener("resize", onResize);
        canvas.removeEventListener("webglcontextlost", onContextLost);
        canvas.removeEventListener("webglcontextrestored", onContextRestored);
        if (gl && !gl.isContextLost()) {
          gl.deleteProgram(program);
          gl.deleteBuffer(vbo);
          gl.deleteVertexArray(vao);
        }
      }
    };
  }

  global.OceanMeshBackground = { mount: mount };
})(typeof window !== "undefined" ? window : globalThis);
