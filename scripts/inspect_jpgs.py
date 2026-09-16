from PIL import Image
import glob
import os

for f in sorted(glob.glob('assets/brand/*.jpg')):
    im = Image.open(f)
    print(f, im.size, im.format)
    # Save a small preview
    base = os.path.basename(f)
    im.resize((300, 300)).save(f"scratch/prev_{base}.png")
