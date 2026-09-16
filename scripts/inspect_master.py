from PIL import Image

img = Image.open('assets/brand/hiretrace_mascot_master.png')
print("Master image format:", img.format, "size:", img.size, "mode:", img.mode)
img.save("scratch/master_preview.png")
