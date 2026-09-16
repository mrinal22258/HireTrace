from PIL import Image
import numpy as np

img = Image.open('C:/Users/krmri/.gemini/antigravity-ide/brain/d9f78e5e-6e2c-4dc8-a003-5a9cb046dd65/mascot_directions_test_1789462379661.jpg').convert('RGBA')
print("Image size:", img.size)

# The image is 1024x1024 with 3x3 grid
cell_w = img.width / 3.0
cell_h = img.height / 3.0

labels = [["NW", "N", "NE"], ["W", "C", "E"], ["SW", "S", "SE"]]
arr = np.array(img).astype(int)

for r in range(3):
    for c in range(3):
        name = labels[r][c]
        box = (int(c * cell_w), int(r * cell_h), int((c + 1) * cell_w), int((r + 1) * cell_h))
        cell = arr[box[1]:box[3], box[0]:box[2]]
        R, G, B, A = cell[..., 0], cell[..., 1], cell[..., 2], cell[..., 3]
        sclera = (R > 225) & (G > 225) & (B > 225)
        # remove background white (assume outer border is background)
        # find non-background
        sy, sx = np.nonzero(sclera)
        print(f"{name}: sclera count={len(sx)}")
