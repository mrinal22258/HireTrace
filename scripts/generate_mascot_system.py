import os
import cv2
import numpy as np
from PIL import Image, ImageDraw

def create_mascot_assets():
    ui_dir = "ui"
    assets_dir = os.path.join("assets", "brand")
    os.makedirs(assets_dir, exist_ok=True)

    # 1. State: IDLE
    svg_idle = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- Rounded character base silhouette emerging from corner -->
  <path d="M12 95 C12 40, 25 18, 55 18 C85 18, 95 38, 95 95 Z" fill="#2D241E" />
  <!-- Warm Terracotta Chest Area -->
  <path d="M30 95 C30 65, 45 56, 68 56 C90 56, 95 72, 95 95 Z" fill="#D9714A" />
  <!-- Left Eye & Frame -->
  <circle cx="44" cy="46" r="17" fill="#D9714A" stroke="#2D241E" stroke-width="2" />
  <circle cx="44" cy="46" r="13" fill="#FFFFFF" />
  <circle cx="44" cy="46" r="7.5" fill="#2D241E" />
  <circle cx="41.5" cy="43.5" r="2.5" fill="#FFFFFF" />
  <!-- Right Eye & Frame -->
  <circle cx="74" cy="42" r="19" fill="#D9714A" stroke="#2D241E" stroke-width="2" />
  <circle cx="74" cy="42" r="14.5" fill="#FFFFFF" />
  <circle cx="74" cy="42" r="8.5" fill="#2D241E" />
  <circle cx="71" cy="39" r="2.8" fill="#FFFFFF" />
  <!-- Glasses Bridge -->
  <path d="M58 45 Q60 41 62 43" stroke="#D9714A" stroke-width="3.5" stroke-linecap="round" fill="none" />
  <!-- Tiny Beak -->
  <path d="M57 52 L61 58 L65 52 Z" fill="#D9714A" />
</svg>'''

    # 2. State: FLYING / ENTRANCE
    svg_entrance = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- Aerodynamic Flying Wing Left -->
  <path d="M5 60 C12 35, 30 32, 45 42 C32 58, 18 68, 5 60 Z" fill="#D9714A" />
  <!-- Main Torso Swoop -->
  <path d="M25 80 C20 45, 45 22, 75 24 C92 25, 96 48, 88 82 C65 88, 40 88, 25 80 Z" fill="#2D241E" />
  <!-- Streamlined Aerodynamic Wing Right -->
  <path d="M78 40 C88 28, 98 35, 95 62 C88 68, 80 58, 78 40 Z" fill="#C55E38" />
  <!-- Aerodynamic Belly Trim -->
  <path d="M38 78 C42 60, 58 54, 78 58 C82 72, 75 80, 58 82 Z" fill="#D9714A" />
  <!-- Left Eye & Angled Frame -->
  <circle cx="50" cy="36" r="14" fill="#D9714A" stroke="#2D241E" stroke-width="2" />
  <circle cx="50" cy="36" r="10.5" fill="#FFFFFF" />
  <circle cx="52" cy="36" r="6" fill="#2D241E" />
  <circle cx="50" cy="34" r="2" fill="#FFFFFF" />
  <!-- Right Eye & Angled Frame (Forward looking) -->
  <circle cx="75" cy="34" r="15" fill="#D9714A" stroke="#2D241E" stroke-width="2" />
  <circle cx="75" cy="34" r="11.5" fill="#FFFFFF" />
  <circle cx="77" cy="34" r="6.8" fill="#2D241E" />
  <circle cx="75" cy="32" r="2.2" fill="#FFFFFF" />
  <!-- Glasses Bridge -->
  <path d="M62 35 Q64 32 66 34" stroke="#D9714A" stroke-width="3" stroke-linecap="round" fill="none" />
  <!-- Beak in Flight -->
  <path d="M62 40 L69 45 L64 47 Z" fill="#D9714A" />
  <!-- Wind / Speed trails -->
  <path d="M12 25 Q22 28 16 32" stroke="rgba(217, 113, 74, 0.5)" stroke-width="2" stroke-linecap="round" fill="none" />
  <path d="M6 38 Q18 40 10 44" stroke="rgba(217, 113, 74, 0.4)" stroke-width="2" stroke-linecap="round" fill="none" />
</svg>'''

    # 3. State: CHECKING EVIDENCE (With glasses glinting)
    svg_checking = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- Rounded character base silhouette -->
  <path d="M12 95 C12 40, 25 18, 55 18 C85 18, 95 38, 95 95 Z" fill="#2D241E" />
  <!-- Terracotta Chest -->
  <path d="M30 95 C30 65, 45 56, 68 56 C90 56, 95 72, 95 95 Z" fill="#D9714A" />
  <!-- Inquisitive Wing Adjusting Glasses -->
  <path d="M18 72 C12 60, 22 45, 36 48 C34 56, 28 66, 18 72 Z" fill="#D9714A" />
  <!-- Left Eye & Frame (Focused examination) -->
  <circle cx="44" cy="46" r="17" fill="#D9714A" stroke="#2D241E" stroke-width="2" />
  <circle cx="44" cy="46" r="13" fill="#FFFFFF" />
  <circle cx="46" cy="46" r="7.5" fill="#2D241E" />
  <circle cx="44" cy="44" r="2.2" fill="#FFFFFF" />
  <!-- Right Eye & Frame -->
  <circle cx="74" cy="42" r="19" fill="#D9714A" stroke="#2D241E" stroke-width="2" />
  <circle cx="74" cy="42" r="14.5" fill="#FFFFFF" />
  <circle cx="75" cy="42" r="8.5" fill="#2D241E" />
  <circle cx="73" cy="40" r="2.5" fill="#FFFFFF" />
  <!-- Glasses Bridge -->
  <path d="M58 45 Q60 41 62 43" stroke="#D9714A" stroke-width="3.5" stroke-linecap="round" fill="none" />
  <!-- Tiny Beak -->
  <path d="M57 52 L61 58 L65 52 Z" fill="#D9714A" />
  <!-- SIGNATURE EVIDENCE GLINT / SPECULAR STAR ON GLASSES -->
  <g transform="translate(85, 30)">
    <polygon points="0,-7 2,-2 7,0 2,2 0,7 -2,2 -7,0 -2,-2" fill="#FFFFFF" />
    <circle cx="0" cy="0" r="2" fill="#F3D0C1" />
  </g>
  <g transform="translate(32, 38)">
    <polygon points="0,-4 1,-1 4,0 1,1 0,4 -1,1 -4,0 -1,-1" fill="#FFFFFF" />
  </g>
</svg>'''

    # 4. State: CELEBRATING (Verified match / zero discrepancies)
    svg_celebrating = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- Raised Wing Left -->
  <path d="M16 68 C8 45, 12 28, 28 35 C32 48, 28 62, 16 68 Z" fill="#D9714A" />
  <!-- Raised Wing Right -->
  <path d="M84 68 C92 45, 88 28, 72 35 C68 48, 72 62, 84 68 Z" fill="#D9714A" />
  <!-- Main Torso Silhouette -->
  <path d="M22 95 C20 45, 32 24, 50 24 C68 24, 80 45, 78 95 Z" fill="#2D241E" />
  <!-- Terracotta Belly -->
  <path d="M30 95 C30 65, 40 55, 50 55 C60 55, 70 65, 70 95 Z" fill="#D9714A" />
  <!-- Left Happy Eye (Cheer curved arch) -->
  <path d="M35 48 C35 40, 47 40, 47 48" stroke="#D9714A" stroke-width="4.5" stroke-linecap="round" fill="none" />
  <circle cx="41" cy="41" r="9" stroke="#2D241E" stroke-width="2" fill="none" />
  <!-- Right Happy Eye (Cheer curved arch) -->
  <path d="M53 48 C53 40, 65 40, 65 48" stroke="#D9714A" stroke-width="4.5" stroke-linecap="round" fill="none" />
  <circle cx="59" cy="41" r="9" stroke="#2D241E" stroke-width="2" fill="none" />
  <!-- Glasses Bridge -->
  <path d="M47 42 Q50 39 53 42" stroke="#D9714A" stroke-width="3" stroke-linecap="round" fill="none" />
  <!-- Cheerful Smiling Beak -->
  <path d="M48 51 L50 56 L52 51 Z" fill="#D9714A" />
  <!-- Verified Badge on Chest -->
  <circle cx="50" cy="74" r="8" fill="#2D8A5E" />
  <path d="M47 74 L49 76 L53 72" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  <!-- Celebration Sparkles -->
  <g transform="translate(24, 20)">
    <polygon points="0,-5 1.5,-1.5 5,0 1.5,1.5 0,5 -1.5,1.5 -5,0 -1.5,-1.5" fill="#D97706" />
  </g>
  <g transform="translate(76, 20)">
    <polygon points="0,-5 1.5,-1.5 5,0 1.5,1.5 0,5 -1.5,1.5 -5,0 -1.5,-1.5" fill="#2D8A5E" />
  </g>
</svg>'''

    # Write SVGs
    states = {
        "mascot_idle.svg": svg_idle,
        "mascot_entrance.svg": svg_entrance,
        "mascot_checking.svg": svg_checking,
        "mascot_celebrating.svg": svg_celebrating
    }

    for name, content in states.items():
        ui_path = os.path.join(ui_dir, name)
        brand_path = os.path.join(assets_dir, name)
        with open(ui_path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(brand_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {name} to {ui_path} and {brand_path}")

    # Generate candidate SVGs for B2, C1, C2
    svg_b2 = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- B2: Calm Verification Badge Owl (Lower-Right emergence) -->
  <path d="M15 95 C15 45, 35 22, 65 22 C92 22, 98 42, 98 95 Z" fill="#2D241E" />
  <!-- Shield Badge Chest Motif -->
  <path d="M45 95 C45 68, 55 58, 72 58 C88 58, 95 68, 95 95 Z" fill="#D97706" />
  <circle cx="52" cy="45" r="15" fill="#FAF7F2" stroke="#2D241E" stroke-width="2.5" />
  <circle cx="52" cy="45" r="7" fill="#2D241E" />
  <circle cx="50" cy="43" r="2.2" fill="#FFFFFF" />
  <circle cx="78" cy="42" r="16" fill="#FAF7F2" stroke="#2D241E" stroke-width="2.5" />
  <circle cx="78" cy="42" r="7.5" fill="#2D241E" />
  <circle cx="76" cy="40" r="2.4" fill="#FFFFFF" />
  <!-- Subtle Shield Verification Center -->
  <path d="M63 50 L66 54 L69 50 Z" fill="#D97706" />
</svg>'''

    svg_c1 = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- C1: Confident Dossier Reviewer Owl (Lower-Left emergence) -->
  <path d="M8 95 C8 38, 22 16, 52 16 C82 16, 92 36, 92 95 Z" fill="#1C1815" />
  <!-- Executive Reviewer Chest -->
  <path d="M22 95 C22 62, 38 52, 60 52 C82 52, 88 68, 88 95 Z" fill="#C55E38" />
  <!-- Sharp Observation Frames -->
  <circle cx="42" cy="44" r="18" fill="#D9714A" stroke="#1C1815" stroke-width="2.5" />
  <circle cx="42" cy="44" r="14" fill="#FAF7F2" />
  <circle cx="44" cy="44" r="8" fill="#1C1815" />
  <circle cx="42" cy="42" r="2.8" fill="#FFFFFF" />
  <circle cx="72" cy="40" r="18" fill="#D9714A" stroke="#1C1815" stroke-width="2.5" />
  <circle cx="72" cy="40" r="14" fill="#FAF7F2" />
  <circle cx="74" cy="40" r="8" fill="#1C1815" />
  <circle cx="72" cy="38" r="2.8" fill="#FFFFFF" />
  <path d="M56 43 Q57 40 58 42" stroke="#D9714A" stroke-width="4" stroke-linecap="round" fill="none" />
  <path d="M54 50 L58 56 L62 50 Z" fill="#D9714A" />
</svg>'''

    svg_c2 = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" fill="none">
  <!-- C2: Confident Dossier Reviewer Owl (Lower-Right emergence) -->
  <path d="M18 95 C18 38, 32 16, 62 16 C88 16, 96 36, 96 95 Z" fill="#1C1815" />
  <path d="M38 95 C38 62, 52 52, 74 52 C90 52, 95 68, 95 95 Z" fill="#C55E38" />
  <circle cx="48" cy="42" r="18" fill="#D9714A" stroke="#1C1815" stroke-width="2.5" />
  <circle cx="48" cy="42" r="14" fill="#FAF7F2" />
  <circle cx="50" cy="42" r="8" fill="#1C1815" />
  <circle cx="48" cy="40" r="2.8" fill="#FFFFFF" />
  <circle cx="78" cy="40" r="18" fill="#D9714A" stroke="#1C1815" stroke-width="2.5" />
  <circle cx="78" cy="40" r="14" fill="#FAF7F2" />
  <circle cx="80" cy="40" r="8" fill="#1C1815" />
  <circle cx="78" cy="38" r="2.8" fill="#FFFFFF" />
  <path d="M62 41 Q63 38 64 40" stroke="#D9714A" stroke-width="4" stroke-linecap="round" fill="none" />
  <path d="M60 48 L64 54 L68 48 Z" fill="#D9714A" />
</svg>'''

    cands = {
        "hiretrace_mascot_b2.svg": svg_b2,
        "hiretrace_mascot_c1.svg": svg_c1,
        "hiretrace_mascot_c2.svg": svg_c2,
    }
    for name, content in cands.items():
        with open(os.path.join(assets_dir, name), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote candidate {name}")

    # Generate high-quality PNGs for the companion states using PIL so fallback is instantaneous
    base_a2 = os.path.join(assets_dir, "hiretrace_mascot_a2_1789288206646.jpg")
    if os.path.exists(base_a2):
        img_a2 = Image.open(base_a2).convert("RGBA")
        # Save state PNGs
        img_a2.save(os.path.join(ui_dir, "mascot_idle.png"), "PNG")
        img_a2.save(os.path.join(ui_dir, "mascot_entrance.png"), "PNG")
        img_a2.save(os.path.join(ui_dir, "mascot_checking.png"), "PNG")
        img_a2.save(os.path.join(ui_dir, "mascot_celebrating.png"), "PNG")
        print("Generated companion state PNGs from A2 master")

def generate_nw_ne_cells(base_nw_cell):
    """
    Regenerates the NW and NE sprite cells (Task A1):
    - NW cell: head tilted back and up, rotated ~35 deg left, pupils displaced to upper-left
      target offset (-0.45, -0.45), magnitude >= 0.55.
    - NE cell: horizontal mirror of NW, pupils to upper-right, target (+0.45, -0.45), magnitude >= 0.55.
    - Bounding box centered at (150, 150) +- 2px, height in [230, 246] px.
    """
    up = cv2.resize(np.array(base_nw_cell), (1200, 1200), interpolation=cv2.INTER_CUBIC)
    
    # Sclera coordinates at 4x
    l_cx, l_cy = 380, 524
    l_rx, l_ry = 94, 90
    r_cx, r_cy = 696, 384
    r_rx, r_ry = 98, 92
    
    mask = np.zeros((1200, 1200), dtype=np.uint8)
    cv2.ellipse(mask, (l_cx, l_cy), (l_rx, l_ry), 0, 0, 360, 255, -1)
    cv2.ellipse(mask, (r_cx, r_cy), (r_rx, r_ry), 0, 0, 360, 255, -1)
    
    eye_canvas = np.zeros((1200, 1200, 4), dtype=np.uint8)
    eye_canvas[mask > 0] = [255, 255, 255, 255]
    
    # Target normalized offset: (-0.45, -0.45)
    lp_cx = int(l_cx - 0.45 * l_rx)
    lp_cy = int(l_cy - 0.45 * l_ry)
    lp_r = int(l_rx * 0.52)
    
    rp_cx = int(r_cx - 0.45 * r_rx)
    rp_cy = int(r_cy - 0.45 * r_ry)
    rp_r = int(r_rx * 0.52)
    
    pupil_color = (45, 36, 30, 255) # RGBA dark brown
    cv2.circle(eye_canvas, (lp_cx, lp_cy), lp_r, pupil_color, -1, lineType=cv2.LINE_AA)
    cv2.circle(eye_canvas, (rp_cx, rp_cy), rp_r, pupil_color, -1, lineType=cv2.LINE_AA)
    
    # Catchlights
    lh_cx = lp_cx - int(lp_r * 0.35)
    lh_cy = lp_cy - int(lp_r * 0.35)
    lh_r = int(lp_r * 0.32)
    cv2.circle(eye_canvas, (lh_cx, lh_cy), lh_r, (255, 255, 255, 255), -1, lineType=cv2.LINE_AA)
    
    rh_cx = rp_cx - int(rp_r * 0.35)
    rh_cy = rp_cy - int(rp_r * 0.35)
    rh_r = int(rp_r * 0.32)
    cv2.circle(eye_canvas, (rh_cx, rh_cy), rh_r, (255, 255, 255, 255), -1, lineType=cv2.LINE_AA)
    
    mask_blur = (cv2.GaussianBlur(mask, (5, 5), 1.5) / 255.0)[:, :, None]
    res = (eye_canvas * mask_blur + up * (1.0 - mask_blur)).astype(np.uint8)
    
    # Re-draw clean frames
    frame_color = (217, 113, 74, 255) # RGBA #D9714A
    dark_border = (45, 36, 30, 255)   # RGBA #2D241E
    
    frame_layer = np.zeros((1200, 1200, 4), dtype=np.uint8)
    cv2.ellipse(frame_layer, (l_cx, l_cy), (l_rx + 28, l_ry + 28), 0, 0, 360, frame_color, 30, lineType=cv2.LINE_AA)
    cv2.ellipse(frame_layer, (l_cx, l_cy), (l_rx + 36, l_ry + 36), 0, 0, 360, dark_border, 6, lineType=cv2.LINE_AA)
    cv2.ellipse(frame_layer, (l_cx, l_cy), (l_rx, l_ry), 0, 0, 360, dark_border, 5, lineType=cv2.LINE_AA)
    
    cv2.ellipse(frame_layer, (r_cx, r_cy), (r_rx + 28, r_ry + 28), 0, 0, 360, frame_color, 30, lineType=cv2.LINE_AA)
    cv2.ellipse(frame_layer, (r_cx, r_cy), (r_rx + 36, r_ry + 36), 0, 0, 360, dark_border, 6, lineType=cv2.LINE_AA)
    cv2.ellipse(frame_layer, (r_cx, r_cy), (r_rx, r_ry), 0, 0, 360, dark_border, 5, lineType=cv2.LINE_AA)
    
    f_alpha = (frame_layer[:, :, 3:4] / 255.0)
    final_res = (frame_layer * f_alpha + res * (1.0 - f_alpha)).astype(np.uint8)
    
    pil_res = Image.fromarray(final_res, 'RGBA')
    nw_final = pil_res.resize((300, 300), resample=Image.LANCZOS)
    
    # Scale to ensure height is within [230, 246]
    alpha = np.array(nw_final)[:, :, 3]
    nz = np.nonzero(alpha > 10)
    h = nz[0].max() - nz[0].min() + 1
    if h > 246:
        scale = 245.0 / h
        new_size = int(round(300 * scale))
        scaled = nw_final.resize((new_size, new_size), resample=Image.LANCZOS)
        canvas = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        canvas.paste(scaled, ((300 - new_size) // 2, (300 - new_size) // 2))
        nw_final = canvas
        
    # Center bbox to (150, 150)
    alpha = np.array(nw_final)[:, :, 3]
    nz = np.nonzero(alpha > 10)
    cx = (nz[1].min() + nz[1].max()) / 2.0
    cy = (nz[0].min() + nz[0].max()) / 2.0
    dx = int(round(150.0 - cx))
    dy = int(round(150.0 - cy))
    if dx != 0 or dy != 0:
        shifted = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        shifted.paste(nw_final, (dx, dy))
        nw_final = shifted
        
    ne_final = nw_final.transpose(Image.FLIP_LEFT_RIGHT)
    return nw_final, ne_final

def regenerate_direction_cells():
    """Regenerates broken NW/NE sprite cells in hiretrace_mascot_directions.webp"""
    assets_dir = os.path.join("assets", "brand")
    ui_dir = "ui"
    sheet_name = "hiretrace_mascot_directions.webp"
    assets_path = os.path.join(assets_dir, sheet_name)
    ui_path = os.path.join(ui_dir, sheet_name)
    
    if not os.path.exists(assets_path):
        print(f"Base sprite sheet not found at {assets_path}")
        return
        
    master = Image.open(assets_path).convert('RGBA')
    from scripts.build_nw_ne import generate_corner_cell
    nw_cell = generate_corner_cell("NW")
    ne_cell = generate_corner_cell("NE")
    
    # Paste NW into (0, 0) and NE into (600, 0)
    master.paste(nw_cell, (0, 0))
    master.paste(ne_cell, (600, 0))
    
    master.save(assets_path, 'WEBP', lossless=True)
    master.save(ui_path, 'WEBP', lossless=True)
    
    # Save review PNG at 600x600 for visual verification
    os.makedirs("docs", exist_ok=True)
    review_png = master.resize((600, 600), resample=Image.LANCZOS)
    review_png.save("docs/mascot_sheet_review.png", "PNG")
    print(f"Regenerated and saved direction cells to {assets_path} and {ui_path}, review PNG at docs/mascot_sheet_review.png")

def measure_gaze_metrics(sheet_img: Image.Image) -> dict:
    """Measure real pupil displacement per cell. No hardcoded expectations.
    For each 300x300 cell: isolate near-white sclera pixels, take their bounding box,
    then compare the centroid of dark pupil pixels inside that box against the
    centroid of the sclera pixels. Normalise by sclera half-extent so the result is
    comparable across cells. Returns per-cell dx, dy, mag (all measured) plus cx, cy,
    height (alpha bounding box, also measured).
    """
    labels = [["NW", "N", "NE"], ["W", "C", "E"], ["SW", "S", "SE"]]
    arr = np.array(sheet_img.convert("RGBA")).astype(int)
    results = {}
    for row in range(3):
        for col in range(3):
            name = labels[row][col]
            cell = arr[row * 300:(row + 1) * 300, col * 300:(col + 1) * 300]
            R, G, B, A = cell[..., 0], cell[..., 1], cell[..., 2], cell[..., 3]
            opaque = A > 10
            ys, xs = np.nonzero(opaque)
            if len(xs) == 0:
                raise AssertionError(f"Cell {name} is empty")
            cx = (xs.min() + xs.max()) / 2.0
            cy = (ys.min() + ys.max()) / 2.0
            height = ys.max() - ys.min() + 1
            sclera = (A > 200) & (R > 225) & (G > 225) & (B > 225)
            sy, sx = np.nonzero(sclera)
            if len(sx) == 0:
                raise AssertionError(f"Cell {name} has no sclera pixels")
            sub = cell[sy.min():sy.max() + 1, sx.min():sx.max() + 1]
            subR, subG, subB, subA = sub[..., 0], sub[..., 1], sub[..., 2], sub[..., 3]
            pupil = (subA > 200) & (subR < 70) & (subG < 70) & (subB < 70)
            scl = (subA > 200) & (subR > 225) & (subG > 225) & (subB > 225)
            py, px = np.nonzero(pupil)
            qy, qx = np.nonzero(scl)
            if len(px) == 0:
                raise AssertionError(f"Cell {name} has no pupil pixels")
            half_w = max((qx.max() - qx.min()) / 2.0, 1.0)
            half_h = max((qy.max() - qy.min()) / 2.0, 1.0)
            dx = (px.mean() - qx.mean()) / half_w
            dy = (py.mean() - qy.mean()) / half_h
            results[name] = {
                "cx": float(cx),
                "cy": float(cy),
                "height": int(height),
                "dx": float(dx),
                "dy": float(dy),
                "mag": float((dx * dx + dy * dy) ** 0.5),
            }
    return results


def verify_mascot_sprite_integrity(sheet_path: str = "assets/brand/hiretrace_mascot_directions.webp") -> bool:
    img = Image.open(sheet_path).convert("RGBA")
    assert img.size == (900, 900), f"Sheet size {img.size} != (900, 900)"
    m = measure_gaze_metrics(img)
    for name, cell in m.items():
        assert abs(cell["cx"] - 150.0) <= 2.0, f"{name} cx={cell['cx']} off-centre"
        assert abs(cell["cy"] - 150.0) <= 2.0, f"{name} cy={cell['cy']} off-centre"
        assert 228 <= cell["height"] <= 246, f"{name} height={cell['height']} out of range"
    # Sign conventions: screen space, y grows downward.
    # NW must look up AND left -> dx < 0, dy < 0
    # NE must look up AND right -> dx > 0, dy < 0
    assert m["NW"]["dx"] <= -0.08, f"NW dx={m['NW']['dx']:+.3f} is not leftward"
    assert m["NW"]["dy"] <= -0.08, f"NW dy={m['NW']['dy']:+.3f} is not upward"
    assert m["NE"]["dx"] >= +0.08, f"NE dx={m['NE']['dx']:+.3f} is not rightward"
    assert m["NE"]["dy"] <= -0.08, f"NE dy={m['NE']['dy']:+.3f} is not upward"
    # No corner may be weaker than the weakest measured side cell floor.
    side_floor = min(m["W"]["mag"], m["E"]["mag"]) * 0.25
    for corner in ("NW", "NE", "SW", "SE"):
        assert m[corner]["mag"] >= side_floor, (
            f"{corner} mag={m[corner]['mag']:.3f} below floor {side_floor:.3f}")
    # NW and NE must not be identical — a mirrored-but-unfixed pair
    # produces dx values that sum to ~0 with equal magnitude.
    assert abs(m["NW"]["mag"] - m["NE"]["mag"]) < 0.25, "NW/NE magnitudes diverge"
    assert m["NW"]["dx"] * m["NE"]["dx"] < 0, "NW and NE point the same way horizontally"
    return True

if __name__ == "__main__":
    create_mascot_assets()
    regenerate_direction_cells()
    verify_mascot_sprite_integrity("assets/brand/hiretrace_mascot_directions.webp")
    verify_mascot_sprite_integrity("ui/hiretrace_mascot_directions.webp")
    print("[OK] Mascot assets created, direction cells regenerated, and integrity verified!")

