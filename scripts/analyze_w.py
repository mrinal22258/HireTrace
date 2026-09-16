from PIL import Image
import numpy as np

img = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
arr = np.array(img).astype(int)

# Cell W is at row 1, col 0 (300:600, 0:300)
cell = arr[300:600, 0:300]
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
print("Cell W:")
print(f"sx: [{sx.min()}, {sx.max()}], sy: [{sy.min()}, {sy.max()}]")
print(f"px.mean()={px.mean():.2f}, qx.mean()={qx.mean():.2f}, half_w={half_w:.2f}, dx={dx:+.3f}")
print(f"py.mean()={py.mean():.2f}, qy.mean()={qy.mean():.2f}, half_h={half_h:.2f}, dy={dy:+.3f}")
print(f"Number of sclera pixels in W: {len(qx)}")
print(f"Number of pupil pixels in W: {len(px)}")
