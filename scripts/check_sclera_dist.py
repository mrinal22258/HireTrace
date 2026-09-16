from PIL import Image
import numpy as np

img = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
arr = np.array(img).astype(int)

for name, (r, c) in [('N', (0, 1)), ('NW', (0, 0)), ('C', (1, 1)), ('W', (1, 0))]:
    cell = arr[r*300:(r+1)*300, c*300:(c+1)*300]
    R, G, B, A = cell[..., 0], cell[..., 1], cell[..., 2], cell[..., 3]
    sclera = (A > 200) & (R > 225) & (G > 225) & (B > 225)
    sy, sx = np.nonzero(sclera)
    print(f"{name}: total sclera pixels={len(sx)}")
    # check where they are:
    for y_thresh in [0, 50, 100, 150, 200, 250]:
        count = np.sum((sy >= y_thresh) & (sy < y_thresh + 50))
        if count > 0:
            print(f"  y in [{y_thresh}, {y_thresh+50}): count={count}, xs=[{sx[sy>=y_thresh].min()}, {sx[sy>=y_thresh].max()}]")
