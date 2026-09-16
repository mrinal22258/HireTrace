import numpy as np
from PIL import Image, ImageDraw

def test_nw_eye_gaze(shift_x=-25, shift_y=-22, far_eye_weight=0.7):
    cell = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
    head = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(head)
    
    # Left eye (facing screen left in 3/4 turn)
    lcx, lcy = 100, 115
    lr = 36
    
    # Right eye (perspective foreshortened in 3/4 turn looking left)
    rcx, rcy = 175, 115
    rr = int(32 * far_eye_weight)
    
    # White sclera
    draw.ellipse([lcx - lr, lcy - lr, lcx + lr, lcy + lr], fill=(255, 255, 255, 255))
    if rr > 0:
        draw.ellipse([rcx - rr, rcy - rr, rcx + rr, rcy + rr], fill=(255, 255, 255, 255))
        
    # Pupils (dark) displaced up and left
    pr_l = int(lr * 0.48)
    pr_r = int(rr * 0.48)
    
    # Shift pupil in left eye
    draw.ellipse([lcx + shift_x - pr_l, lcy + shift_y - pr_l, lcx + shift_x + pr_l, lcy + shift_y + pr_l], fill=(45, 36, 30, 255))
    if rr > 0:
        draw.ellipse([rcx + shift_x - pr_r, rcy + shift_y - pr_r, rcx + shift_x + pr_r, rcy + shift_y + pr_r], fill=(45, 36, 30, 255))
        
    arr = np.array(head).astype(int)
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
    dx = (px.mean() - qx.mean()) / half_w
    dy = (py.mean() - qy.mean()) / half_h
    print(f"shift=({shift_x}, {shift_y}), far_wt={far_eye_weight}: dx={dx:+.3f}, dy={dy:+.3f}, mag={(dx**2+dy**2)**0.5:.3f}")

test_nw_eye_gaze(-28, -22, far_eye_weight=0.6)
test_nw_eye_gaze(-32, -22, far_eye_weight=0.5)
test_nw_eye_gaze(-35, -24, far_eye_weight=0.4)
test_nw_eye_gaze(-30, -25, far_eye_weight=0.3)


