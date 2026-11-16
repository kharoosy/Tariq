#!/usr/bin/env python3
"""Cut the master MP4 into the nine per-scene clips (06_Rendered_Scenes/scene_XX.mp4) and build the thumbnail."""
import os, sys, json, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(ROOT, "07_Final", "LS_Open_Closed_Loop_Arabic_120s.mp4")
TL = json.load(open(os.path.join(ROOT, "01_Project", "scene_timeline.json"), encoding="utf-8"))
for sc in TL["scenes"]:
    out = os.path.join(ROOT, "06_Rendered_Scenes", f"scene_{sc['id']:02d}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{sc['start']:.3f}", "-i", MASTER, "-t",
                    f"{sc['end'] - sc['start']:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)
    print("clip", out)

# thumbnail: split-screen frame + bold title
sys.path.insert(0, ROOT)
import assemble_video as V
from PIL import Image, ImageDraw
src = V.FrameSource(os.path.join(ROOT, "06_Rendered_Scenes", "frames"))
im = V.grade(V.base_frame(src, 3300)).convert("RGBA")
layer = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
d.rectangle((0, 0, V.W, 330), fill=(5, 8, 12, 200))
V.paste_text(layer, "كيف يتحكم كمبيوتر محرك LS بالوقود؟", (V.W / 2, 40), V.F_KUFI, 92, V.WHITE, 1, "mt", stroke=3)
V.paste_text(layer, "Open Loop", (V.W / 4, 205), V.F_BOLD, 70, V.ORANGE, 1, "mt", rtl=False)
V.paste_text(layer, "Closed Loop", (3 * V.W / 4, 205), V.F_BOLD, 70, V.BLUE, 1, "mt", rtl=False)
V.paste_text(layer, "VS", (V.W / 2, 210), V.F_BOLD, 60, V.WHITE, 1, "mt", rtl=False)
im.alpha_composite(layer)
im.convert("RGB").save(os.path.join(ROOT, "07_Final", "thumbnail.png"))
print("thumbnail ok")
