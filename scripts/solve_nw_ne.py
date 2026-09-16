from PIL import Image, ImageDraw
import numpy as np

master = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
c_cell = master.crop((300, 300, 600, 600))

# 4x scale for crisp drawing
c_4x = c_cell.resize((1200, 1200), resample=Image.LANCZOS)
draw = ImageDraw.Draw(c_4x)

# Eye centers at 4x
ec_lx, ec_ly = int(108.5 * 4), int(164.5 * 4)
ec_rx, ec_ry = int(188.8 * 4), int(163.5 * 4)
r_sc = int(31.5 * 4)

c_dark = (30, 25, 22, 255)
# Let's test varying the left vs right sclera exposed area or shifting pupils

for r_left in [31.5, 25.0, 20.0, 15.0]:
    for p_shift in [15, 18, 22]:
        c_4x = c_cell.resize((1200, 1200), resample=Image.LANCZOS)
        draw = ImageDraw.Draw(c_4x)
        
        # Left eye sclera (smaller if turned)
        r_sc_l = int(r_left * 4)
        r_sc_r = int(31.5 * 4)
        draw.ellipse([ec_lx - r_sc_l, ec_ly - r_sc_l, ec_lx + r_sc_l, ec_ly + r_sc_l], fill=(255, 255, 255, 255))
        draw.ellipse([ec_rx - r_sc_r, ec_ry - r_sc_r, ec_rx + r_sc_r, ec_ry + r_sc_r], fill=(255, 255, 255, 255))
        
        # Pupils
        sx, sy = int(p_shift * 4), int(16 * 4)
        p_r = int(14 * 4)
        draw.ellipse([ec_lx - sx - p_r, ec_ly - sy - p_r, ec_lx - sx + p_r, ec_ly - sy + p_r], fill=c_dark)
        draw.ellipse([ec_rx - sx - p_r, ec_ry - sy - p_r, ec_rx - sx + p_r, ec_ry - sy + p_r], fill=c_dark)
        
        res = c_4x.resize((300, 300), resample=Image.LANCZOS)
        arr = np.array(res)
        A, R, G, B = arr[..., 3], arr[..., 0], arr[..., 1], arr[..., 2]
        sclera = (A > 200) & (R > 225) & (G > 225) & (B > 225)
        sy_nz, sx_nz = np.nonzero(sclera)
        sub = arr[sy_nz.min():sy_nz.max() + 1, sx_nz.min():sx_nz.max() + 1]
        subR, subG, subB, subA = sub[..., 0], sub[..., 1], sub[..., 2], sub[..., 3]
        pupil = (subA > 200) & (subR < 70) & (subG < 70) & (subB < 70)
        scl = (subA > 200) & (subR > 225) & (subG > 225) & (subB > 225)
        py, px = np.nonzero(pupil)
        qy, qx = np.nonzero(scl)
        half_w = max((qx.max() - qx.min()) / 2.0, 1.0)
        half_h = max((qy.max() - qy.min()) / 2.0, 1.0)
        dx = (px.mean() - qx.mean()) / half_w
        dy = (py.mean() - qy.mean()) / half_h
        print(f"r_left={r_left:.1f}, p_shift={p_shift}: dx={dx:+.3f}, dy={dy:+.3f}")








