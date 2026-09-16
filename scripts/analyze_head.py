from PIL import Image
import numpy as np

img_n = Image.open('scratch/cell_N.png').convert('RGBA')
arr_n = np.array(img_n)

# Find eye centers, lens circles/ellipses in cell_N
# In cell_N:
# The lenses are glasses frames.
# Glasses frame color is around [204, 106, 66] or [217, 113, 74]
# Sclera is around [255, 255, 255]
# Let's find the centers of the two eyes in cell_N

sclera_mask = (arr_n[..., 3] > 200) & (arr_n[..., 0] > 225) & (arr_n[..., 1] > 225) & (arr_n[..., 2] > 225)
sy, sx = np.nonzero(sclera_mask)

# Left eye in N vs Right eye in N
mid_x = (sx.min() + sx.max()) / 2.0
left_sclera = sclera_mask.copy()
left_sclera[:, int(mid_x):] = False
right_sclera = sclera_mask.copy()
right_sclera[:, :int(mid_x)] = False

lsy, lsx = np.nonzero(left_sclera)
rsy, rsx = np.nonzero(right_sclera)

print(f"Cell N Left Eye Sclera: x=[{lsx.min()}, {lsx.max()}], y=[{lsy.min()}, {lsy.max()}], center=({lsx.mean():.1f}, {lsy.mean():.1f})")
print(f"Cell N Right Eye Sclera: x=[{rsx.min()}, {rsx.max()}], y=[{rsy.min()}, {rsy.max()}], center=({rsx.mean():.1f}, {rsy.mean():.1f})")

# Same for Cell C
img_c = Image.open('scratch/cell_C.png').convert('RGBA')
arr_c = np.array(img_c)
scl_c = (arr_c[..., 3] > 200) & (arr_c[..., 0] > 225) & (arr_c[..., 1] > 225) & (arr_c[..., 2] > 225)
cy, cx = np.nonzero(scl_c)
mid_cx = (cx.min() + cx.max()) / 2.0
l_scl_c = scl_c.copy()
l_scl_c[:, int(mid_cx):] = False
r_scl_c = scl_c.copy()
r_scl_c[:, :int(mid_cx)] = False
clsy, clsx = np.nonzero(l_scl_c)
crsy, crsx = np.nonzero(r_scl_c)
print(f"Cell C Left Eye Sclera: x=[{clsx.min()}, {clsx.max()}], y=[{clsy.min()}, {clsy.max()}], center=({clsx.mean():.1f}, {clsy.mean():.1f})")
print(f"Cell C Right Eye Sclera: x=[{crsx.min()}, {crsx.max()}], y=[{crsy.min()}, {crsy.max()}], center=({crsx.mean():.1f}, {crsy.mean():.1f})")
