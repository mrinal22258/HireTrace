/**
 * HireTrace Boot Script (ui/boot.js)
 * Mounts living surface mesh background and interactive mascot tracker.
 */
document.addEventListener("DOMContentLoaded", function () {
  // 1. Mount site-wide Ocean WebGL2 animated living surface mesh
  var canvas = document.getElementById("oceanMeshCanvas");
  if (canvas && window.OceanMeshBackground) {
    window.OceanMeshBackground.mount(canvas);
  }

  // 2. Mount interactive 3x3 cursor tracking & poke reaction mascot
  var mount = document.getElementById("heroMascotSprite");
  if (mount && window.MascotCursorTracker) {
    window.MascotCursorTracker.mount(mount, {
      directions: "/assets/brand/hiretrace_mascot_directions.webp",
      reactions: "/assets/brand/hiretrace_mascot_reactions.webp",
      size: 84,
      label: "HireTrace verification mascot"
    });
  }
});
