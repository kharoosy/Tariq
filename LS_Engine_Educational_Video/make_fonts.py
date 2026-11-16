#!/usr/bin/env python3
"""Merge Noto Arabic fonts with Noto Sans (Latin) so mixed Arabic/English labels render with one font.
Both fonts are SIL Open Font License 1.1 (merged output keeps OFL)."""
import os
from fontTools.merge import Merger, Options
from fontTools.ttLib import TTFont
N = "/usr/share/fonts/truetype/noto/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "02_3D_Assets", "fonts")
os.makedirs(OUT, exist_ok=True)
for ar, lat, name in (("NotoSansArabic-Regular.ttf", "NotoSans-Regular.ttf", "LSArabicSans-Regular.ttf"),
                      ("NotoSansArabic-Bold.ttf", "NotoSans-Bold.ttf", "LSArabicSans-Bold.ttf"),
                      ("NotoKufiArabic-Bold.ttf", "NotoSans-Bold.ttf", "LSArabicKufi-Bold.ttf")):
    m = Merger(options=Options(drop_tables=["vmtx", "vhea", "MATH", "STAT", "fvar", "gvar", "avar", "HVAR", "MVAR"]))
    f = m.merge([N + ar, N + lat])
    f.save(os.path.join(OUT, name))
    cm = f.getBestCmap()
    print(name, "ok", all(ord(c) in cm for c in "Open Loop ECU O₂ °C % كيف"))
