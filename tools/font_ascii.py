#!/usr/bin/env python3
from PIL import Image
img = Image.open("NanoApps/build/font_engine_sim.png").convert("1")
w, h = img.size
step_x = max(1, w // 100)
step_y = max(1, h // 50)
px = img.load()
for y in range(0, h, step_y):
    row = "".join("#" if px[x, y] else "." for x in range(0, w, step_x))
    print(row)
