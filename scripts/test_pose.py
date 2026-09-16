import numpy as np
import cv2
from PIL import Image, ImageDraw
from scripts.generate_mascot_system import measure_gaze_metrics

# Load C and N cells
master = Image.open('assets/brand/hiretrace_mascot_directions.webp').convert('RGBA')
arr = np.array(master)

cell_c = Image.fromarray(arr[300:600, 300:600])
cell_n = Image.fromarray(arr[0:300, 300:600])

print("Ready to test poses")
