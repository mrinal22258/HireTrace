import cv2
import numpy as np
from PIL import Image, ImageDraw

# Load C, N, and original NW
master = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
arr_master = np.array(master)

cell_c = Image.fromarray(arr_master[300:600, 300:600])
cell_n = Image.fromarray(arr_master[0:300, 300:600])
cell_w = Image.fromarray(arr_master[300:600, 0:300])
cell_e = Image.fromarray(arr_master[300:600, 600:900])

print("Cells loaded successfully.")
