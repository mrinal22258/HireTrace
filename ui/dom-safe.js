/**
 * dom-safe.js
 * Canonical DOM sanitization and safe HTML injection primitives for HireTrace.
 * Shared across app.js, motion.js, and all view renderers.
 */
(function (global) {
  "use strict";

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Tagged template that escapes every interpolated value.
   * Usage:  el.innerHTML = safeHTML`<span>${userValue}</span>`;
   * The literal parts are trusted (they are in your source); every ${...}
   * is escaped. There is no way to pass unescaped user input through it.
   */
  function safeHTML(strings, ...values) {
    return strings.reduce(
      (out, str, i) => out + str + (i < values.length ? escapeHtml(values[i]) : ''),
      ''
    );
  }

  global.DOMSafe = {
    escapeHtml: escapeHtml,
    safeHTML: safeHTML
  };

  // Expose on global scope for direct call sites
  global.escapeHtml = escapeHtml;
  global.safeHTML = safeHTML;
})(typeof window !== "undefined" ? window : globalThis);
