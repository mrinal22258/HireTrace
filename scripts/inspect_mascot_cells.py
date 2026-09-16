from PIL import Image
import numpy as np

img = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
arr = np.array(img)

# Labels:
# NW (0,0)  N (0,1)  NE (0,2)
# W  (1,0)  C (1,1)  E  (1,2)
# SW (2,0)  S (2,1)  SE (2,2)

c_cell = arr[300:600, 300:600]
n_cell = arr[0:300, 300:600]
w_cell = arr[300:600, 0:300]
e_cell = arr[300:600, 600:900]

def analyze_cell(cell, name):
    alpha = cell[..., 3]
    R, G, B, A = cell[..., 0], cell[..., 1], cell[..., 2], cell[..., 3]
    sclera = (A > 200) & (R > 225) & (G > 225) & (B > 225)
    sy, sx = np.nonzero(sclera)
    sub = cell[sy.min():sy.max() + 1, sx.min():sx.max() + 1]
    subR, subG, subB, subA = sub[..., 0], sub[..., 1], sub[..., 2], sub[..., 3]
    pupil = (subA > 200) & (subR < 70) & (subG < 70) & (subB < 70)
    scl = (subA > 200) & (subR > 225) & (subG > 225) & (subB > 225)
    py, px = np.nonzero(pupil)
    qy, qx = np.nonzero(scl)
    half_w = max((qx.max() - qx.min()) / 2.0, 1.0)
    half_h = max((qy.max() - qy.min()) / 2.0, 1.0)
    dx = (px.mean() - qx.mean()) / half_w
    dy = (py.mean() - qy.mean()) / half_h
    print(f"{name}: sub_x=[{sx.min()},{sx.max()}], sub_y=[{sy.min()},{sy.max()}], half_w={half_w:.1f}, half_h={half_h:.1f}, dx={dx:+.3f}, dy={dy:+.3f}, px_mean={px.mean():.1f}, qx_mean={qx.mean():.1f}, py_mean={py.mean():.1f}, qy_mean={qy.mean():.1f}")

# Save individual cells as PNG to inspect visually
for name, (r, c) in [('NW', (0,0)), ('N', (0,1)), ('NE', (0,2)), ('W', (1,0)), ('C', (1,1)), ('E', (1,2))]:
    cell = img.crop((c*300, r*300, (c+1)*300, (r+1)*300))
    cell.save(f"scratch/cell_{name}.png")
print("Saved cells to scratch/")

