import numpy as np
from PIL import Image, ImageDraw
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.generate_mascot_system import measure_gaze_metrics, verify_mascot_sprite_integrity

def generate_cell(direction="NW",
                  p_shift_x=-24, p_shift_y=-20,
                  p_radius=15, sclera_r=28,
                  rot_deg=-26,
                  eye_y_ratio=0.36,
                  eye_dist_ratio=0.28):
    scale = 4
    W, H = 300 * scale, 300 * scale
    
    C_BODY = (45, 36, 30, 255)
    C_CHEST = (204, 106, 66, 255)
    C_FRAME = (204, 106, 66, 255)
    C_DARK = (45, 36, 30, 255)
    C_WHITE = (255, 255, 255, 255)
    
    is_nw = (direction == "NW")
    
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # Body base
    body_box = [int(W * 0.18), int(H * 0.22), int(W * 0.82), int(H * 0.94)]
    draw.rounded_rectangle(body_box, radius=int(W * 0.30), fill=C_BODY)
    
    # Wings
    draw.rounded_rectangle([int(W * 0.12), int(H * 0.45), int(W * 0.25), int(H * 0.88)], radius=int(W * 0.08), fill=(38, 30, 25, 255))
    draw.rounded_rectangle([int(W * 0.75), int(H * 0.45), int(W * 0.88), int(H * 0.88)], radius=int(W * 0.08), fill=(38, 30, 25, 255))
    
    # Chest
    bx0, by0 = int(W * 0.26) + (-20 if is_nw else +20), int(H * 0.52)
    bx1, by1 = int(W * 0.74) + (-20 if is_nw else +20), int(H * 0.94)
    draw.ellipse([bx0, by0, bx1, by1], fill=C_CHEST)
    
    # Head layer
    head = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(head)
    
    # Head dome
    hdraw.ellipse([int(W * 0.20), int(H * 0.15), int(W * 0.80), int(H * 0.65)], fill=C_BODY)
    
    ec_y = int(H * eye_y_ratio)
    ec_lx = int(W * (0.50 - eye_dist_ratio / 2.0))
    ec_rx = int(W * (0.50 + eye_dist_ratio / 2.0))
    
    r_frame = int(sclera_r * 1.35 * scale)
    r_sc = int(sclera_r * scale)
    
    # Frames
    hdraw.ellipse([ec_lx - r_frame, ec_y - r_frame, ec_lx + r_frame, ec_y + r_frame], fill=C_FRAME)
    hdraw.ellipse([ec_rx - r_frame, ec_y - r_frame, ec_rx + r_frame, ec_y + r_frame], fill=C_FRAME)
    
    # Scleras
    hdraw.ellipse([ec_lx - r_sc, ec_y - r_sc, ec_lx + r_sc, ec_y + r_sc], fill=C_WHITE)
    hdraw.ellipse([ec_rx - r_sc, ec_y - r_sc, ec_rx + r_sc, ec_y + r_sc], fill=C_WHITE)
    
    # Pupil positions
    sx = p_shift_x * scale if is_nw else -p_shift_x * scale
    sy = p_shift_y * scale
    pr = int(p_radius * scale)
    cr = int(pr * 0.32)
    
    # Left eye pupil
    pl_x = ec_lx + sx
    pl_y = ec_y + sy
    hdraw.ellipse([pl_x - pr, pl_y - pr, pl_x + pr, pl_y + pr], fill=C_DARK)
    hdraw.ellipse([pl_x - int(pr*0.35) - cr, pl_y - int(pr*0.35) - cr, pl_x - int(pr*0.35) + cr, pl_y - int(pr*0.35) + cr], fill=C_WHITE)
    
    # Right eye pupil
    pr_x = ec_rx + sx
    pr_y = ec_y + sy
    hdraw.ellipse([pr_x - pr, pr_y - pr, pr_x + pr, pr_y + pr], fill=C_DARK)
    hdraw.ellipse([pr_x - int(pr*0.35) - cr, pr_y - int(pr*0.35) - cr, pr_x - int(pr*0.35) + cr, pr_y - int(pr*0.35) + cr], fill=C_WHITE)
    
    # Bridge & Beak
    bridge_y = ec_y + int(r_frame * 0.05)
    hdraw.arc([int(W * 0.44), bridge_y - 20, int(W * 0.56), bridge_y + 25], start=180, end=360, fill=C_FRAME, width=28)
    
    bk_cx = int(W * 0.50)
    bk_top = ec_y + int(r_frame * 0.15)
    bk_tip = bk_top + int(W * 0.085)
    bk_hw = int(W * 0.045)
    hdraw.polygon([(bk_cx - bk_hw, bk_top), (bk_cx + bk_hw, bk_top), (bk_cx, bk_tip)], fill=C_FRAME)
    
    rot_angle = rot_deg if is_nw else -rot_deg
    head_center = (int(W * 0.50), int(H * 0.45))
    rotated_head = head.rotate(rot_angle, resample=Image.BICUBIC, center=head_center)
    
    canvas.alpha_composite(rotated_head)
    cell_300 = canvas.resize((300, 300), resample=Image.LANCZOS)
    
    arr = np.array(cell_300)
    nz = np.nonzero(arr[..., 3] > 10)
    ymin, ymax = nz[0].min(), nz[0].max()
    xmin, xmax = nz[1].min(), nz[1].max()
    h = ymax - ymin + 1
    if h < 230 or h > 246:
        scale_f = 238.0 / float(h)
        nw_size = int(round(300 * scale_f))
        scaled = cell_300.resize((nw_size, nw_size), resample=Image.LANCZOS)
        padded = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        ox = (300 - nw_size) // 2
        oy = (300 - nw_size) // 2
        padded.paste(scaled, (ox, oy))
        cell_300 = padded
        arr = np.array(cell_300)
        nz = np.nonzero(arr[..., 3] > 10)
        ymin, ymax = nz[0].min(), nz[0].max()
        xmin, xmax = nz[1].min(), nz[1].max()
        
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    sx = int(round(150.0 - cx))
    sy = int(round(150.0 - cy))
    if sx != 0 or sy != 0:
        shifted = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        shifted.paste(cell_300, (sx, sy))
        cell_300 = shifted
        
    return cell_300

# Sweep test
master = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')

best = None
for shift_x in [-20, -25, -28]:
    for shift_y in [-18, -22, -26]:
        for rot in [-20, -25, -30]:
            nw = generate_cell("NW", p_shift_x=shift_x, p_shift_y=shift_y, rot_deg=rot)
            ne = generate_cell("NE", p_shift_x=shift_x, p_shift_y=shift_y, rot_deg=rot)
            test_sheet = master.copy()
            test_sheet.paste(nw, (0, 0))
            test_sheet.paste(ne, (600, 0))
            try:
                m = measure_gaze_metrics(test_sheet)
                nw_dx, nw_dy = m['NW']['dx'], m['NW']['dy']
                ne_dx, ne_dy = m['NE']['dx'], m['NE']['dy']
                nw_mag, ne_mag = m['NW']['mag'], m['NE']['mag']
                print(f"sx={shift_x}, sy={shift_y}, rot={rot} -> NW(dx={nw_dx:+.3f}, dy={nw_dy:+.3f}, mag={nw_mag:.3f}) NE(dx={ne_dx:+.3f}, dy={ne_dy:+.3f}, mag={ne_mag:.3f})")
                if nw_dx <= -0.30 and nw_dy <= -0.30 and ne_dx >= 0.30 and ne_dy <= -0.30:
                    print(f"*** FOUND PASSING CONFIG: sx={shift_x}, sy={shift_y}, rot={rot} ***")
                    best = (shift_x, shift_y, rot)
                    break
            except Exception as e:
                pass
        if best:
            break
    if best:
        break
