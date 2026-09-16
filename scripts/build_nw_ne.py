import cv2
import numpy as np
from PIL import Image, ImageDraw
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.generate_mascot_system import measure_gaze_metrics, verify_mascot_sprite_integrity

def generate_corner_cell(direction="NW"):
    """
    Renders high-fidelity corner sprite cell at 4x (1200x1200) then downsamples
    to 300x300 with LANCZOS for razor-sharp vector quality:
    - Head tilted back (like N cell) and rotated 30 deg to side
    - Pupils displaced up-and-outward (dx <= -0.30 for NW, dx >= +0.30 for NE; dy <= -0.30)
    - Completely clean sclera fill (no ghost pupils)
    - Perfectly symmetrical lenses with clean bridge and beak layered on top
    - Consistent body shading and belly highlight
    - Alpha bbox centered at (150, 150) +- 2px, height 230-246px
    """
    scale = 4
    W = 300 * scale # 1200
    H = 300 * scale # 1200
    
    # Palette
    C_BODY = (45, 36, 30, 255)       # #2D241E Dark brown body
    C_CHEST = (204, 106, 66, 255)    # #CC6A42 Warm terracotta chest
    C_FRAME = (204, 106, 66, 255)    # Frame terracotta
    C_DARK = (45, 36, 30, 255)       # Frame stroke & pupils
    C_WHITE = (255, 255, 255, 255)   # Sclera & catchlight
    
    is_nw = (direction == "NW")
    # Rotation angle: NW turns left (-28 deg), NE turns right (+28 deg)
    rot_angle = -28.0 if is_nw else +28.0
    
    # Create canvas
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # 1. Torso Base (drawn centered, tilted back like N cell)
    # The body is an upright rounded capsule
    # Body base bounds at 4x:
    body_x0, body_y0 = int(W * 0.18), int(H * 0.22)
    body_x1, body_y1 = int(W * 0.82), int(H * 0.94)
    draw.rounded_rectangle([body_x0, body_y0, body_x1, body_y1], radius=int(W * 0.30), fill=C_BODY)
    
    # Lateral wings
    wing_l = [int(W * 0.12), int(H * 0.45), int(W * 0.25), int(H * 0.88)]
    wing_r = [int(W * 0.75), int(H * 0.45), int(W * 0.88), int(H * 0.88)]
    draw.rounded_rectangle(wing_l, radius=int(W * 0.08), fill=(38, 30, 25, 255))
    draw.rounded_rectangle(wing_r, radius=int(W * 0.08), fill=(38, 30, 25, 255))
    
    # Belly highlight (slightly shifted to reflect 3/4 light angle)
    belly_shift = -20 if is_nw else +20
    bx0, by0 = int(W * 0.26) + belly_shift, int(H * 0.52)
    bx1, by1 = int(W * 0.74) + belly_shift, int(H * 0.94)
    draw.ellipse([bx0, by0, bx1, by1], fill=C_CHEST)
    
    # 2. Head group (eyes, frames, bridge, beak) rendered on separate layer so it tilts/rotates
    head = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(head)
    
    # Head dome
    hx0, hy0 = int(W * 0.20), int(H * 0.15)
    hx1, hy1 = int(W * 0.80), int(H * 0.65)
    hdraw.ellipse([hx0, hy0, hx1, hy1], fill=C_BODY)
    
    # Lens geometry derived from C cell at 4x
    # Eye centers in head coords
    # Lens radius
    r_frame = int(W * 0.140)   # 168px
    r_sclera = int(W * 0.108)  # 130px
    r_pupil = int(r_sclera * 0.52) # 68px
    r_catch = int(r_pupil * 0.32)  # 22px
    
    # Left eye center & Right eye center
    ec_y = int(H * 0.36)
    ec_lx = int(W * 0.36)
    ec_rx = int(W * 0.64)
    
    # Identical lens geometry derived from C cell at 4x
    # Sclera radius 126px, Frame radius 162px, Pupil radius 68px
    r_sclera = int(W * 0.105)  # 126px at 4x (31.5px at 300px)
    r_frame = int(W * 0.138)   # 165px at 4x (41px at 300px)
    r_pupil = int(r_sclera * 0.52) # 65px
    r_catch = int(r_pupil * 0.32)  # 21px
    
    # Draw Outer frames (Terracotta with clean anti-aliasing)
    hdraw.ellipse([ec_lx - r_frame, ec_y - r_frame, ec_lx + r_frame, ec_y + r_frame], fill=C_FRAME)
    hdraw.ellipse([ec_rx - r_frame, ec_y - r_frame, ec_rx + r_frame, ec_y + r_frame], fill=C_FRAME)
    
    # Sclera (pure white interior, completely erasing any old pupil)
    hdraw.ellipse([ec_lx - r_sclera, ec_y - r_sclera, ec_lx + r_sclera, ec_y + r_sclera], fill=C_WHITE)
    hdraw.ellipse([ec_rx - r_sclera, ec_y - r_sclera, ec_rx + r_sclera, ec_y + r_sclera], fill=C_WHITE)
    
    # Gaze offset:
    # NW: pupils displaced strongly up-and-left
    # NE: pupils displaced strongly up-and-right
    p_shift_x = -int(r_sclera * 0.62) if is_nw else +int(r_sclera * 0.62)
    p_shift_y = -int(r_sclera * 0.58)
    
    # Left pupil & catchlight
    pl_x = ec_lx + p_shift_x
    pl_y = ec_y + p_shift_y
    hdraw.ellipse([pl_x - r_pupil, pl_y - r_pupil, pl_x + r_pupil, pl_y + r_pupil], fill=C_DARK)
    cl_x = pl_x - int(r_pupil * 0.35)
    cl_y = pl_y - int(r_pupil * 0.35)
    hdraw.ellipse([cl_x - r_catch, cl_y - r_catch, cl_x + r_catch, cl_y + r_catch], fill=C_WHITE)
    
    # Right pupil & catchlight
    pr_x = ec_rx + p_shift_x
    pr_y = ec_y + p_shift_y
    hdraw.ellipse([pr_x - r_pupil, pr_y - r_pupil, pr_x + r_pupil, pr_y + r_pupil], fill=C_DARK)
    cr_x = pr_x - int(r_pupil * 0.35)
    cr_y = pr_y - int(r_pupil * 0.35)
    hdraw.ellipse([cr_x - r_catch, cr_y - r_catch, cr_x + r_catch, cr_y + r_catch], fill=C_WHITE)
    
    # Glasses Bridge (drawn cleanly OVER the frames)
    bridge_y = ec_y + int(r_frame * 0.05)
    hdraw.arc([int(W * 0.44), bridge_y - 20, int(W * 0.56), bridge_y + 25], start=180, end=360, fill=C_FRAME, width=28)
    hdraw.arc([int(W * 0.44) - 2, bridge_y - 22, int(W * 0.56) + 2, bridge_y + 27], start=180, end=360, fill=C_DARK, width=6)
    
    # Beak (Terracotta triangle drawn cleanly OVER the bridge & lenses)
    bk_cx = int(W * 0.50)
    bk_top = ec_y + int(r_frame * 0.15)
    bk_tip = bk_top + int(W * 0.085)
    bk_hw = int(W * 0.045)
    beak_pts = [(bk_cx - bk_hw, bk_top), (bk_cx + bk_hw, bk_top), (bk_cx, bk_tip)]
    hdraw.polygon(beak_pts, fill=C_FRAME, outline=C_DARK)
    
    # Rotate head by rot_angle around head center
    head_center = (int(W * 0.50), int(H * 0.45))
    rotated_head = head.rotate(rot_angle, resample=Image.BICUBIC, center=head_center)
    
    # Composite rotated head onto body
    canvas.alpha_composite(rotated_head)
    
    # Downsample from 1200x1200 to 300x300 with high-quality LANCZOS filter
    cell_300 = canvas.resize((300, 300), resample=Image.LANCZOS)
    
    # Center bbox to (150, 150) +- 2px and ensure height in [230, 246]
    arr = np.array(cell_300)
    alpha = arr[..., 3]
    nz = np.nonzero(alpha > 10)
    ymin, ymax = nz[0].min(), nz[0].max()
    xmin, xmax = nz[1].min(), nz[1].max()
    h = ymax - ymin + 1
    
    # Normalize height to 238px if out of bounds
    target_h = 238
    if h < 230 or h > 246:
        scale_factor = target_h / float(h)
        new_w = int(round(300 * scale_factor))
        new_h = int(round(300 * scale_factor))
        scaled = cell_300.resize((new_w, new_h), resample=Image.LANCZOS)
        padded = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        ox = (300 - new_w) // 2
        oy = (300 - new_h) // 2
        padded.paste(scaled, (ox, oy))
        cell_300 = padded
        
        arr = np.array(cell_300)
        nz = np.nonzero(arr[..., 3] > 10)
        ymin, ymax = nz[0].min(), nz[0].max()
        xmin, xmax = nz[1].min(), nz[1].max()
        h = ymax - ymin + 1
        
    # Re-center cx, cy
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    shift_x = int(round(150.0 - cx))
    shift_y = int(round(150.0 - cy))
    if shift_x != 0 or shift_y != 0:
        shifted = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
        shifted.paste(cell_300, (shift_x, shift_y))
        cell_300 = shifted
        
    return cell_300

if __name__ == "__main__":
    nw = generate_corner_cell("NW")
    ne = generate_corner_cell("NE")
    nw.save("scratch/test_nw.png")
    ne.save("scratch/test_ne.png")
    print("Saved test_nw.png and test_ne.png")
    
    # Test on full sheet
    master = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
    test_sheet = master.copy()
    test_sheet.paste(nw, (0, 0))
    test_sheet.paste(ne, (600, 0))
    m = measure_gaze_metrics(test_sheet)
    for name, cell_im in [("NW", nw), ("NE", ne)]:
        arr = np.array(cell_im).astype(int)
        R, G, B, A = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
        sclera = (A > 200) & (R > 225) & (G > 225) & (B > 225)
        sy, sx = np.nonzero(sclera)
        sub = arr[sy.min():sy.max() + 1, sx.min():sx.max() + 1]
        subR, subG, subB, subA = sub[..., 0], sub[..., 1], sub[..., 2], sub[..., 3]
        pupil = (subA > 200) & (subR < 70) & (subG < 70) & (subB < 70)
        scl = (subA > 200) & (subR > 225) & (subG > 225) & (subB > 225)
        py, px = np.nonzero(pupil)
        qy, qx = np.nonzero(scl)
        half_w = max((qx.max() - qx.min()) / 2.0, 1.0)
        half_h = max((qy.max() - qy.min()) / 2.0, 1.0)
        print(f"{name} details: sx=[{sx.min()}, {sx.max()}], sy=[{sy.min()}, {sy.max()}], px_count={len(px)}, qx_count={len(qx)}, px_range=[{px.min()},{px.max()}], qx_range=[{qx.min()},{qx.max()}], px_mean={px.mean():.1f}, qx_mean={qx.mean():.1f}, py_mean={py.mean():.1f}, qy_mean={qy.mean():.1f}")



