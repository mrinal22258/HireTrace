from PIL import Image
import numpy as np

img_c = Image.open('scratch/cell_C.png').convert('RGBA')
arr_c = np.array(img_c)

colors, counts = np.unique(arr_c.reshape(-1, 4), axis=0, return_counts=True)
idx = np.argsort(-counts)
for i in idx[:10]:
    print('color:', colors[i].tolist(), 'count:', counts[i])
