import os
import shutil
from PIL import Image

src_dir = r"C:\Users\krmri\.gemini\antigravity-ide\brain\f1f1f45a-1a85-459c-8c0a-0957ebf2e3b5"
dst_dir = os.path.join("assets", "brand")
os.makedirs(dst_dir, exist_ok=True)

# Copy all candidates
for fname in os.listdir(src_dir):
    if fname.startswith("hiretrace_mascot_") and fname.endswith(".jpg"):
        shutil.copy(os.path.join(src_dir, fname), os.path.join(dst_dir, fname))
        print("Copied candidate:", fname)

# Process A2 as the selected master brand mark
candidates = [os.path.join(src_dir, f) for f in os.listdir(src_dir) if "mascot_a2" in f]
if candidates:
    a2_path = candidates[0]
    img = Image.open(a2_path).convert("RGBA")

    # 512x512 master
    master = img.resize((512, 512), Image.Resampling.LANCZOS)
    master.save(os.path.join(dst_dir, "hiretrace_mascot_master.png"), "PNG")
    print("Saved master 512x512")

    # 32x32 favicon-ready
    img32 = master.resize((32, 32), Image.Resampling.LANCZOS)
    img32.save(os.path.join(dst_dir, "hiretrace_mascot_32.png"), "PNG")
    print("Saved 32x32")

    # 16x16 favicon-ready
    img16 = master.resize((16, 16), Image.Resampling.LANCZOS)
    img16.save(os.path.join(dst_dir, "hiretrace_mascot_16.png"), "PNG")
    print("Saved 16x16")

    # Multi-resolution favicon.ico
    master.save(os.path.join(dst_dir, "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    master.save(os.path.join("ui", "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print("Saved ui/favicon.ico")
