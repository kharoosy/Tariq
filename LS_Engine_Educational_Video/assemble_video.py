#!/usr/bin/env python3
"""Composite rendered 3D frames + motion graphics + Arabic subtitles, mux audio, encode H.264 MP4.

  python3 assemble_video.py [--frames DIR] [--out FILE] [--preview] [--range a-b] [--still F]

* 3D frames (06_Rendered_Scenes/frames/{main,s8a,s8b}) are upscaled to 1920x1080 (Lanczos),
  graded (bloom + vignette), and the split-screen (scene 8) is composed from passes s8a/s8b.
* All typography / diagrams / gauges are drawn natively at 1920x1080 with Pillow + raqm
  (HarfBuzz shaping, FriBidi RTL) using merged Noto Arabic + Noto Sans fonts.
* 3D-tracked labels use the per-frame projected anchors written by render_scenes.py.
* Subtitles come from 05_Subtitles/arabic_subtitles.srt (timed from the measured narration).
"""
import os, sys, json, math, re, argparse, subprocess, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, '03_Blender'))
try:
    import bpy  # noqa: F401  (provides mathutils for animate_engine)
except Exception:
    pass
import animate_engine as A

W, H, FPS, N = 1920, 1080, 30, 3600
FONT_DIR = os.path.join(ROOT, '02_3D_Assets', 'fonts')
F_KUFI = os.path.join(FONT_DIR, 'LSArabicKufi-Bold.ttf')
F_BOLD = os.path.join(FONT_DIR, 'LSArabicSans-Bold.ttf')
F_REG = os.path.join(FONT_DIR, 'LSArabicSans-Regular.ttf')
ORANGE, BLUE, GREEN, PURPLE = (255, 138, 31), (31, 182, 255), (61, 255, 139), (178, 91, 255)
WHITE, MUTED, PANEL = (240, 244, 250), (150, 162, 178), (8, 12, 18)


@functools.lru_cache(maxsize=64)
def font(path, size):
    return ImageFont.truetype(path, size)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def fade(t, a, b, f=0.45):
    """1 inside [a,b] with smooth fades."""
    return ease((t - a) / f) * (1 - ease((t - (b - f)) / f))


def col(c, a):
    return (*c[:3], int(max(0, min(1, a)) * 255))


@functools.lru_cache(maxsize=4096)
def text_img(text, path, size, color, stroke=0, rtl=True):
    f = font(path, size)
    kw = dict(direction='rtl', language='ar') if rtl else {}
    bbox = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=f, stroke_width=stroke, **kw)
    w, h = bbox[2] - bbox[0] + 8, bbox[3] - bbox[1] + 8
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((4 - bbox[0], 4 - bbox[1]), text, font=f, fill=color, stroke_width=stroke,
           stroke_fill=(0, 0, 0, 200) if stroke else None, **kw)
    return im


def paste_text(layer, text, xy, path=F_BOLD, size=36, color=WHITE, alpha=1.0, anchor='rt', stroke=0, rtl=True):
    """anchor: r/l/m horizontal + t/m/b vertical (relative to the text box)."""
    if alpha <= 0.01:
        return (0, 0)
    im = text_img(text, path, size, tuple(color[:3]) + (255,), stroke, rtl)
    if alpha < 0.999:
        a = im.getchannel('A').point(lambda v: int(v * alpha))
        im = im.copy(); im.putalpha(a)
    x, y = xy
    w, h = im.size
    x = {'r': x - w, 'l': x, 'm': x - w // 2}[anchor[0]]
    y = {'t': y, 'm': y - h // 2, 'b': y - h}[anchor[1]]
    layer.alpha_composite(im, (int(x), int(y)))
    return (w, h)


def panel(d, box, alpha, radius=18, outline=None, fill=PANEL, fa=0.62):
    if alpha <= 0.01:
        return
    d.rounded_rectangle(box, radius, fill=col(fill, fa * alpha),
                        outline=col(outline, 0.9 * alpha) if outline else None, width=2 if outline else 0)


# ------------------------------------------------------------------ subtitles
def load_srt(path):
    subs = []
    txt = open(path, encoding='utf-8').read().strip()
    for block in re.split(r'\n\s*\n', txt):
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        a, b = lines[1].split(' --> ')
        def ts(s):
            h, m, rest = s.strip().split(':'); sec, ms = rest.split(',')
            return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
        text = ' '.join(lines[2:]).replace('‫', '').replace('‬', '')
        subs.append((ts(a), ts(b), text))
    return subs


def wrap_ar(text, path, size, maxw):
    words = text.split(' ')
    lines, cur = [], ''
    f = font(path, size)
    for wd in words:
        trial = (cur + ' ' + wd).strip()
        if f.getlength(trial) > maxw and cur:
            lines.append(cur); cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def draw_subtitle(layer, d, t, subs):
    for a, b, text in subs:
        if a - 0.1 <= t <= b + 0.1:
            al = ease((t - a + 0.1) / 0.2) * (1 - ease((t - b) / 0.12 + 0.1))
            lines = wrap_ar(text, F_BOLD, 44, 1500)
            lh = 66
            total = lh * len(lines)
            y0 = H - 58 - total
            maxw = max(font(F_BOLD, 44).getlength(ln) for ln in lines)
            panel(d, (W / 2 - maxw / 2 - 34, y0 - 12, W / 2 + maxw / 2 + 34, H - 46), al, 16, fa=0.58)
            for i, ln in enumerate(lines):
                paste_text(layer, ln, (W / 2, y0 + i * lh), F_BOLD, 44, WHITE, al, 'mt', stroke=2)


# ------------------------------------------------------------------ widgets
def chapter_tag(layer, d, t):
    names = {1: 'المقدمة', 2: 'داخل المحرك', 3: 'الكمبيوتر والحساسات', 4: 'الحلقة المفتوحة', 5: 'الإحماء والانتقال',
             6: 'الحلقة المغلقة', 7: 'تصحيحات الوقود', 8: 'المقارنة', 9: 'الخلاصة'}
    sid = A.scene_at(t)
    if sid in (1, 9) or (sid == 8):
        return
    s0 = [s for s in A.SCENES if s[0] == sid][0]
    al = fade(t, s0[1] + 0.3, s0[2] - 0.1, 0.5) * 0.95
    accent = {4: ORANGE, 5: ORANGE, 6: BLUE, 7: GREEN}.get(sid, (200, 210, 225))
    if sid == 5:
        accent = tuple(int(a + (b - a) * ease((t - 61) / 5.5)) for a, b in zip(ORANGE, BLUE))
    x1 = W - 70
    paste_text(layer, names[sid], (x1 - 20, 64), F_BOLD, 30, WHITE, al, 'rt')
    paste_text(layer, f'0{sid}', (x1 + 2, 62), F_BOLD, 30, accent, al, 'lt', rtl=False)
    d.line((x1 - 300, 112, x1 + 40, 112), fill=col(accent, 0.6 * al), width=2)


def tracked_label(layer, d, anc, key, ar, en, colr, al, off=(140, -110), side='fixed'):
    if al <= 0.01 or key not in anc:
        return
    x, y, z = anc[key]
    if z <= 0 or not (-200 < x < W + 200 and -200 < y < H + 200):
        return
    ox, oy = off
    if side == 'auto':
        ox = ox if x < W * 0.62 else -ox
    lx, ly = x + ox, y + oy
    lx = max(330, min(W - 330, lx)); ly = max(150, min(H - 230, ly))
    d.ellipse((x - 7, y - 7, x + 7, y + 7), outline=col(colr, al), width=3)
    d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=col(colr, al))
    ex = lx
    d.line((x, y, ex, ly), fill=col(colr, 0.85 * al), width=2)
    f1 = font(F_BOLD, 32); f2 = font(F_REG, 22)
    w = max(f1.getlength(ar), f2.getlength(en)) + 36
    if ox >= 0:
        bx0, bx1 = ex, ex + w
    else:
        bx0, bx1 = ex - w, ex
    panel(d, (bx0, ly - 44, bx1, ly + 40), al, 12, outline=colr, fa=0.55)
    paste_text(layer, ar, (bx1 - 18, ly - 38), F_BOLD, 32, WHITE, al, 'rt')
    paste_text(layer, en, (bx1 - 18, ly + 6), F_REG, 22, colr, al, 'rt', rtl=False)


def mode_banner(layer, d, t, ar, en, colr, al, y=150):
    if al <= 0.01:
        return
    f1 = font(F_KUFI, 54)
    w = f1.getlength(ar) + font(F_BOLD, 40).getlength(en) + 120
    x0, x1 = W / 2 - w / 2, W / 2 + w / 2
    panel(d, (x0, y - 50, x1, y + 50), al, 24, outline=colr, fa=0.6)
    paste_text(layer, ar, (x1 - 36, y), F_KUFI, 54, colr, al, 'rm')
    paste_text(layer, en, (x0 + 36, y + 2), F_BOLD, 40, WHITE, al, 'lm', rtl=False)
    d.line((x1 - 36 - f1.getlength(ar) - 26, y - 26, x1 - 36 - f1.getlength(ar) - 26, y + 26), fill=col(colr, al), width=3)


def gauge_temp(layer, d, t, temp, al, x=150, y=250):
    if al <= 0.01:
        return
    panel(d, (x - 40, y - 60, x + 330, y + 250), al, 18, fa=0.6)
    paste_text(layer, 'حرارة المحرك', (x + 300, y - 46), F_BOLD, 30, WHITE, al, 'rt')
    paste_text(layer, 'ECT', (x - 10, y - 40), F_BOLD, 24, MUTED, al, 'lt', rtl=False)
    cx, cy, r = x + 145, y + 130, 105
    d.arc((cx - r, cy - r, cx + r, cy + r), 150, 390, fill=col((60, 68, 80), al), width=14)
    frac = (temp - 0) / 120
    c = tuple(int(a + (b - a) * ease((temp - 20) / 70)) for a, b in zip((90, 170, 255), (255, 110, 40)))
    d.arc((cx - r, cy - r, cx + r, cy + r), 150, 150 + 240 * frac, fill=col(c, al), width=14)
    ang = math.radians(150 + 240 * frac)
    d.line((cx, cy, cx + (r - 26) * math.cos(ang), cy + (r - 26) * math.sin(ang)), fill=col(WHITE, al), width=4)
    d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=col(WHITE, al))
    paste_text(layer, f'{temp:.0f} °C', (cx, cy + 58), F_BOLD, 40, c, al, 'mt', rtl=False)
    if temp < 40:
        paste_text(layer, 'تشغيل بارد', (cx, cy + 108), F_BOLD, 26, (130, 190, 255), al, 'mt')


def checklist(layer, d, t, items, al, x=W - 120, y=300):
    if al <= 0.01:
        return
    w = 640
    panel(d, (x - w, y - 70, x + 30, y + 92 * len(items) + 10), al, 18, fa=0.62)
    paste_text(layer, 'شروط الانتقال للحلقة المغلقة', (x, y - 54), F_BOLD, 30, WHITE, al, 'rt')
    for i, (ar, en, ton) in enumerate(items):
        yy = y + 10 + i * 92
        on = ease((t - ton) / 0.5)
        bx = x - 18
        c = tuple(int(a + (b - a) * on) for a, b in zip((90, 98, 110), GREEN))
        d.rounded_rectangle((bx - 36, yy, bx, yy + 36), 8, outline=col(c, al), width=3,
                            fill=col(GREEN, 0.25 * on * al))
        if on > 0.05:
            d.line([(bx - 29, yy + 19), (bx - 20, yy + 28), (bx - 6, yy + 8)], fill=col(GREEN, on * al), width=5)
        paste_text(layer, ar, (bx - 52, yy - 4), F_BOLD, 30, WHITE, al * (0.55 + 0.45 * on), 'rt')
        paste_text(layer, en, (bx - 52, yy + 40), F_REG, 21, MUTED, al, 'rt', rtl=False)


def loop_diagram(layer, d, t, al, cx=W - 330, cy=430, r=170):
    if al <= 0.01:
        return
    panel(d, (cx - r - 130, cy - r - 95, cx + r + 130, cy + r + 80), al, 22, fa=0.6)
    paste_text(layer, 'دورة التغذية الراجعة', (cx, cy - r - 82), F_BOLD, 30, BLUE, al, 'mt')
    nodes = [('الكمبيوتر', 'ECU'), ('البخاخ', 'Injector'), ('الاحتراق', 'Combustion'), ('العادم', 'Exhaust'),
             ('حساس O₂', 'O₂ Sensor')]
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col(BLUE, 0.45 * al), width=3)
    ph = (t * 0.25) % 1.0
    for k in range(3):
        a = 2 * math.pi * ((ph + k * 0.04) % 1.0) - math.pi / 2
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        s = 9 - k * 2
        d.ellipse((px - s, py - s, px + s, py + s), fill=col(BLUE, al * (1 - k * 0.3)))
    for i, (ar, en) in enumerate(nodes):
        a = 2 * math.pi * i / len(nodes) - math.pi / 2
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        act = 1 - min(1, abs(((ph - i / len(nodes) + 0.5) % 1.0) - 0.5) * 8)
        d.ellipse((px - 14, py - 14, px + 14, py + 14), fill=col((10, 30, 50), al), outline=col(BLUE, al), width=3)
        if act > 0:
            d.ellipse((px - 22, py - 22, px + 22, py + 22), outline=col(BLUE, act * al), width=2)
        tx = px + (40 if math.cos(a) > 0.2 else -40 if math.cos(a) < -0.2 else 0)
        ty = py + (-46 if i == 0 else 22 if math.sin(a) > 0.5 else -18)
        anchor = 'l' if math.cos(a) > 0.2 else 'r' if math.cos(a) < -0.2 else 'm'
        paste_text(layer, ar, (tx, ty), F_BOLD, 26, WHITE, al, anchor + 't')
        paste_text(layer, en, (tx, ty + 34), F_REG, 19, MUTED, al, anchor + 't', rtl=False)


def o2_graph(layer, d, t, al, x0=110, y0=600, w=560, h=200):
    if al <= 0.01:
        return
    panel(d, (x0 - 30, y0 - 80, x0 + w + 30, y0 + h + 60), al, 18, fa=0.62)
    paste_text(layer, 'إشارة حساس الأكسجين', (x0 + w, y0 - 66), F_BOLD, 28, WHITE, al, 'rt')
    paste_text(layer, 'Narrowband O₂  (V)', (x0, y0 - 62), F_REG, 21, MUTED, al, 'lt', rtl=False)
    d.rectangle((x0, y0, x0 + w, y0 + h / 2), fill=col((60, 25, 10), 0.35 * al))
    d.rectangle((x0, y0 + h / 2, x0 + w, y0 + h), fill=col((10, 35, 60), 0.35 * al))
    paste_text(layer, 'غني  Rich', (x0 + w - 10, y0 + 6), F_BOLD, 22, (255, 160, 90), al, 'rt')
    paste_text(layer, 'فقير  Lean', (x0 + w - 10, y0 + h - 6), F_BOLD, 22, (120, 200, 255), al, 'rb')
    d.line((x0, y0 + h / 2, x0 + w, y0 + h / 2), fill=col(MUTED, 0.5 * al), width=1)
    pts = []
    for i in range(120):
        tt = t - 4.0 + 4.0 * i / 119
        v = A.env(tt)['o2v']
        pts.append((x0 + w * i / 119, y0 + h - (v - 0.05) / 0.9 * h))
    d.line(pts, fill=col(BLUE, al), width=4, joint='curve')
    paste_text(layer, '0.9', (x0 - 8, y0), F_REG, 18, MUTED, al, 'rt', rtl=False)
    paste_text(layer, '0.1', (x0 - 8, y0 + h - 16), F_REG, 18, MUTED, al, 'rt', rtl=False)
    v = A.env(t)['o2v']
    rich = v > 0.45
    msg = 'الخليط غني: الكمبيوتر يقلل الوقود' if rich else 'الخليط فقير: الكمبيوتر يزيد الوقود'
    paste_text(layer, msg, (x0 + w, y0 + h + 14), F_BOLD, 26, (255, 170, 100) if rich else (120, 205, 255), al, 'rt')


def dial(layer, d, cx, cy, r, val, rng, colr, title_ar, title_en, sub_ar, al):
    if al <= 0.01:
        return
    panel(d, (cx - r - 60, cy - r - 120, cx + r + 60, cy + 150), al, 22, outline=colr, fa=0.6)
    paste_text(layer, title_en, (cx, cy - r - 108), F_BOLD, 36, colr, al, 'mt', rtl=False)
    paste_text(layer, title_ar, (cx, cy - r - 62), F_BOLD, 26, WHITE, al, 'mt')
    d.arc((cx - r, cy - r, cx + r, cy + r), 180, 360, fill=col((60, 68, 80), al), width=16)
    for k in range(-5, 6):
        a = math.radians(270 + k * 18)
        d.line((cx + (r - 26) * math.cos(a), cy + (r - 26) * math.sin(a), cx + (r - 12) * math.cos(a),
                cy + (r - 12) * math.sin(a)), fill=col(MUTED, al), width=2)
    frac = max(-1, min(1, val / rng))
    a0, a1 = sorted((270, 270 + 90 * frac))
    d.arc((cx - r, cy - r, cx + r, cy + r), a0, a1, fill=col(colr, al), width=16)
    a = math.radians(270 + 90 * frac)
    d.line((cx, cy, cx + (r - 30) * math.cos(a), cy + (r - 30) * math.sin(a)), fill=col(WHITE, al), width=5)
    d.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=col(WHITE, al))
    paste_text(layer, f'{val:+.1f} %', (cx, cy + 22), F_BOLD, 46, colr, al, 'mt', rtl=False)
    paste_text(layer, f'-{rng}%', (cx - r, cy + 10), F_REG, 20, MUTED, al, 'mt', rtl=False)
    paste_text(layer, f'+{rng}%', (cx + r, cy + 10), F_REG, 20, MUTED, al, 'mt', rtl=False)
    paste_text(layer, sub_ar, (cx, cy + 90), F_BOLD, 24, (210, 218, 230), al, 'mt')


def pulse_panel(layer, d, t, e, al, x0=W / 2 - 430, y0=742, w=860, h=120):
    if al <= 0.01:
        return
    panel(d, (x0, y0 - 56, x0 + w, y0 + h + 10), al, 16, fa=0.62)
    paste_text(layer, 'عرض نبضة البخاخ = الأساسي × (1 + STFT + LTFT)', (x0 + w - 24, y0 - 46), F_BOLD, 26, WHITE, al, 'rt')
    base_w = 70
    pw = 1 + (e['stft'] + e['ltft']) / 100
    pts = []
    yb, yt = y0 + h - 18, y0 + 18
    x = x0 + 30
    period = 200
    shift = (t * 90) % period
    xs = x0 + 30 - shift
    while xs < x0 + w - 30:
        on0, on1 = xs + 40, xs + 40 + base_w * pw * 1.6
        seg = [(xs, yb), (on0, yb), (on0, yt), (on1, yt), (on1, yb), (xs + period, yb)]
        for px, py in seg:
            pts.append((min(max(px, x0 + 30), x0 + w - 30), py))
        xs += period
    d.line(pts, fill=col(GREEN, al), width=4)


def flow_boxes(layer, d, t, al, y=840):
    if al <= 0.01:
        return
    items = [('الحساسات + الخرائط', 'Sensors + Maps', WHITE), ('الكمبيوتر يحسب', 'ECU calculation', BLUE),
             ('أمر البخاخات', 'Injector pulse', ORANGE)]
    bw, gap = 360, 90
    x = W / 2 + (3 * bw + 2 * gap) / 2
    for i, (ar, en, c) in enumerate(items):
        a = al * ease((t - 33.2 - i * 0.6) / 0.5)
        x1, x0 = x, x - bw
        panel(d, (x0, y - 60, x1, y + 50), a, 16, outline=c, fa=0.62)
        paste_text(layer, ar, (x1 - 22, y - 50), F_BOLD, 30, WHITE, a, 'rt')
        paste_text(layer, en, (x1 - 22, y + 4), F_REG, 21, c, a, 'rt', rtl=False)
        if i < 2:
            ax = x0 - 14
            a2 = al * ease((t - 33.5 - i * 0.6) / 0.5)
            d.line((ax, y - 5, ax - gap + 28, y - 5), fill=col(WHITE, a2), width=4)
            d.polygon([(ax - gap + 22, y - 5), (ax - gap + 40, y - 16), (ax - gap + 40, y + 6)], fill=col(WHITE, a2))
        x = x0 - gap


def stroke_indicator(layer, d, t, frame, al, x=W - 130, y=330):
    if al <= 0.01:
        return
    th = A.crank_angle(frame)
    c = A.cycle_angle(1, th)
    idx = {0: 2, 1: 3, 2: 0, 3: 1}[int(c // 180) % 4]     # 0-180 power, 180-360 exhaust, 360-540 intake...
    strokes = [('السحب', 'Intake', (120, 200, 255)), ('الضغط', 'Compression', WHITE),
               ('الاحتراق', 'Power', ORANGE), ('العادم', 'Exhaust', (255, 110, 70))]
    panel(d, (x - 360, y - 74, x + 30, y + 4 * 70 + 6), al, 18, fa=0.6)
    paste_text(layer, 'الأسطوانة رقم 1', (x, y - 60), F_BOLD, 30, WHITE, al, 'rt')
    for i, (ar, en, c2) in enumerate(strokes):
        yy = y + i * 70
        on = 1.0 if i == idx else 0.0
        if on:
            d.rounded_rectangle((x - 340, yy - 4, x + 10, yy + 58), 12, fill=col(c2, 0.22 * al), outline=col(c2, al),
                                width=2)
        paste_text(layer, ar, (x - 12, yy + 2), F_BOLD, 30, c2 if on else MUTED, al, 'rt')
        paste_text(layer, en, (x - 320, yy + 12), F_REG, 22, c2 if on else MUTED, al, 'lt', rtl=False)


def chips(layer, d, t, al, x=W - 110, y=300):
    if al <= 0.01:
        return
    panel(d, (x - 640, y - 20, x + 30, y + 250), al, 18, fa=0.62)
    paste_text(layer, 'يستخدم:', (x, y), F_BOLD, 30, WHITE, al, 'rt')
    paste_text(layer, 'MAF • MAP • RPM • ECT • TPS', (x - 130, y + 6), F_BOLD, 28, (200, 230, 255), al, 'rt', rtl=False)
    paste_text(layer, '+ خرائط الوقود المبرمجة', (x, y + 54), F_BOLD, 28, (200, 230, 255), al, 'rt')
    a2 = al * ease((t - 45.5) / 0.6)
    yy = y + 120
    d.line((x - 600, yy - 10, x + 10, yy - 10), fill=col(MUTED, 0.4 * al), width=1)
    paste_text(layer, 'تصحيح الوقود من حساس O₂:', (x, yy + 4), F_BOLD, 30, WHITE, a2, 'rt')
    paste_text(layer, 'غير مُفعّل', (x - 400, yy + 4), F_BOLD, 30, ORANGE, a2, 'rt')
    cx, cy = x - 590, yy + 26
    d.line((cx - 14, cy - 14, cx + 14, cy + 14), fill=col(ORANGE, a2), width=5)
    d.line((cx - 14, cy + 14, cx + 14, cy - 14), fill=col(ORANGE, a2), width=5)
    paste_text(layer, '* الشروط الدقيقة تختلف حسب معايرة كل محرك', (x, yy + 62), F_REG, 22, MUTED, a2, 'rt')


# ------------------------------------------------------------------ overlay per frame
def overlays(layer, frame, anc, subs):
    t = frame / FPS
    e = A.env(t)
    d = ImageDraw.Draw(layer)
    sid = A.scene_at(t)

    # S1 title
    al = fade(t, 1.4, 10.9, 0.8)
    if al > 0.01:
        y = 140 - 20 * (1 - ease((t - 1.4) / 1.2))
        paste_text(layer, 'كيف يتحكم كمبيوتر محرك LS بالوقود؟', (W / 2, y), F_KUFI, 76, WHITE, al, 'mt', stroke=2)
        f = font(F_BOLD, 44)
        parts = [('Open Loop', ORANGE), ('  vs  ', MUTED), ('Closed Loop', BLUE)]
        tw = sum(f.getlength(p) for p, _ in parts)
        x = W / 2 - tw / 2
        a2 = fade(t, 2.4, 10.9, 0.8)
        for p, c in parts:
            paste_text(layer, p, (x, y + 132), F_BOLD, 44, c, a2, 'lt', rtl=False); x += f.getlength(p)
        ww = 520 * ease((t - 2.2) / 1.5)
        d.line((W / 2 - ww, y + 118, W / 2, y + 118), fill=col(ORANGE, 0.8 * a2), width=3)
        d.line((W / 2, y + 118, W / 2 + ww, y + 118), fill=col(BLUE, 0.8 * a2), width=3)

    chapter_tag(layer, d, t)

    # S2
    tracked_label(layer, d, anc, 'ThrottleBody', 'الثروتل — دخول الهواء', 'Throttle Body', (120, 200, 255),
                  fade(t, 13.0, 17.2), (-160, -120))
    tracked_label(layer, d, anc, 'Injector_1', 'البخاخ — يرش في مجرى السحب', 'Port Fuel Injector', ORANGE,
                  fade(t, 17.6, 26.2), (170, -140))
    stroke_indicator(layer, d, t, frame, fade(t, 19.4, 26.3), y=330)
    tracked_label(layer, d, anc, 'Cyl_1', 'الأسطوانة 1 — المكبس', 'Cylinder 1 / Piston', ORANGE,
                  fade(t, 22.4, 26.3), (-240, -190))

    # S3 sensors
    for i, (k, ar, en) in enumerate((('MAF', 'حساس تدفق الهواء', 'MAF – Mass Air Flow'),
                                     ('MAP', 'حساس ضغط المجمع', 'MAP – Manifold Pressure'),
                                     ('ECT', 'حرارة سائل التبريد', 'ECT – Coolant Temp'),
                                     ('TPS', 'وضعية الثروتل', 'TPS – Throttle Position'),
                                     ('CKP', 'سرعة المحرك RPM', 'CKP – Crank Position'))):
        offs = {'MAF': (230, -90), 'MAP': (-60, -230), 'ECT': (-260, 40), 'TPS': (250, 90), 'CKP': (240, 150)}
        tracked_label(layer, d, anc, k, ar, en, (200, 228, 255), fade(t, 27.6 + i * 0.75, 32.6 + i * 0.2), offs[k])
    tracked_label(layer, d, anc, 'ECU', 'كمبيوتر المحرك', 'ECU / PCM', BLUE, fade(t, 31.0, 37.8), (-200, -160))
    flow_boxes(layer, d, t, fade(t, 33.0, 37.9))

    # S4 open loop
    mode_banner(layer, d, t, 'الحلقة المفتوحة', 'Open Loop', ORANGE, fade(t, 39.2, 64.6, 0.6) if t < 64.6 else 0)
    gauge_temp(layer, d, t, e['coolant'], fade(t, 40.0, 63.0), x=150, y=int(560 - 270 * ease((t - 55.0) / 1.2)))
    chips(layer, d, t, fade(t, 43.0, 54.8), y=300)
    tracked_label(layer, d, anc, 'FuelMap', 'خريطة الوقود المبرمجة', 'Base Fuel Map (RPM × Load)', ORANGE,
                  fade(t, 42.8, 54.8), (40, -250))

    # S5 warm-up and switch
    checklist(layer, d, t, [('حرارة المحرك مناسبة', 'ECT above calibrated threshold', 59.6),
                            ('حساس الأكسجين جاهز (ساخن ويتذبذب)', 'O₂ sensor ready / active', 62.6),
                            ('وقت التشغيل وشروط المعايرة', 'Run time & calibration conditions', 64.6)],
              fade(t, 56.2, 67.8), x=W - 110, y=310)
    tracked_label(layer, d, anc, 'O2_L_tip', 'حساس الأكسجين — قبل المحوّل', 'Upstream O₂ (Bank 1 Sensor 1)', BLUE,
                  fade(t, 59.0, 66.8), (200, -200))
    mode_banner(layer, d, t, 'الحلقة المغلقة', 'Closed Loop', BLUE, fade(t, 65.0, 87.8, 0.8))

    # S6 closed loop
    loop_diagram(layer, d, t, fade(t, 69.0, 87.6), cx=W - 330, cy=470)
    o2_graph(layer, d, t, fade(t, 73.5, 87.6), x0=120, y0=560)
    tracked_label(layer, d, anc, 'O2_L_tip', 'إشارة O₂ إلى الكمبيوتر', 'O₂ feedback to ECU', BLUE, fade(t, 69.0, 73.4),
                  (220, -160))

    # S7 fuel trims
    al7 = fade(t, 89.0, 102.8)
    dial(layer, d, 440, 420, 170, e['stft'], 25, GREEN, 'تصحيح قصير المدى — سريع', 'STFT', 'يتغير بسرعة مع حساس O₂', al7)
    dial(layer, d, W - 440, 420, 170, e['ltft'], 25, PURPLE, 'تصحيح طويل المدى — متعلَّم', 'LTFT',
         'يتغير ببطء ويُحفظ', fade(t, 93.5, 102.8))
    pulse_panel(layer, d, t, e, fade(t, 96.5, 102.8))

    # S8 split labels
    al8 = fade(t, 103.4, 114.6, 0.5) if t < 114.6 else 0
    if al8 > 0.01:
        for half, (ar, en, sub, c, ok) in enumerate((('الحلقة المفتوحة', 'Open Loop', 'بدون تصحيح من O₂', ORANGE, False),
                                                     ('الحلقة المغلقة', 'Closed Loop', 'تصحيح بالتغذية الراجعة', BLUE, True))):
            cx = W / 4 + half * W / 2
            panel(d, (cx - 300, 70, cx + 300, 230), al8, 20, outline=c, fa=0.6)
            paste_text(layer, ar, (cx, 84), F_KUFI, 50, c, al8, 'mt')
            paste_text(layer, en, (cx, 168), F_BOLD, 34, WHITE, al8, 'mt', rtl=False)
            y = 760
            panel(d, (cx - 280, y - 10, cx + 280, y + 70), al8, 16, fa=0.6)
            paste_text(layer, sub, (cx + 250, y + 2), F_BOLD, 34, WHITE, al8, 'rt')
            ix, iy = cx - 235, y + 30
            if ok:
                d.line([(ix - 16, iy), (ix - 4, iy + 14), (ix + 18, iy - 14)], fill=col(GREEN, al8), width=6)
            else:
                d.line((ix - 14, iy - 14, ix + 14, iy + 14), fill=col(ORANGE, al8), width=6)
                d.line((ix - 14, iy + 14, ix + 14, iy - 14), fill=col(ORANGE, al8), width=6)

    # S9 closing title
    al9 = fade(t, 115.6, 121.0, 0.9)
    if al9 > 0.01:
        paste_text(layer, 'افهم نظام الوقود، تفهم محركك أكثر.', (W / 2, 150), F_KUFI, 74, WHITE, al9, 'mt', stroke=2)
        ww = 560 * ease((t - 116.0) / 1.5)
        d.line((W / 2 - ww, 280, W / 2, 280), fill=col(ORANGE, al9), width=4)
        d.line((W / 2, 280, W / 2 + ww, 280), fill=col(BLUE, al9), width=4)
        paste_text(layer, 'GM LS V8  —  Open Loop  vs  Closed Loop', (W / 2, 304), F_BOLD, 30, MUTED, al9, 'mt', rtl=False)

    draw_subtitle(layer, d, t, subs)


# ------------------------------------------------------------------ image pipeline
_VIG = None


def vignette():
    global _VIG
    if _VIG is None:
        y, x = np.mgrid[0:H, 0:W]
        r = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
        _VIG = (1 - 0.32 * np.clip((r - 0.55) / 0.85, 0, 1) ** 1.6).astype(np.float32)[..., None]
    return _VIG


def grade(img):
    a = np.asarray(img, dtype=np.float32) / 255.0
    small = img.resize((W // 4, H // 4), Image.BILINEAR)
    s = np.asarray(small, dtype=np.float32) / 255.0
    br = np.clip(s - 0.72, 0, 1) * 1.6
    bl = Image.fromarray((np.clip(br, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9))
    bl = np.asarray(bl.resize((W, H), Image.BILINEAR), dtype=np.float32) / 255.0
    a = 1 - (1 - a) * (1 - 0.55 * bl)          # screen-blend bloom
    a = a * vignette()
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


class FrameSource:
    def __init__(self, base):
        self.base = base
        self.idx = {}
        for p in ('main', 's8a', 's8b'):
            d = os.path.join(base, p)
            self.idx[p] = sorted(int(f[2:6]) for f in os.listdir(d) if f.endswith('.png') and not f.endswith('.tmp.png')) \
                if os.path.isdir(d) else []
        ad = os.path.join(base, 'anchors')
        self.anc = sorted(int(f[2:6]) for f in os.listdir(ad) if f.endswith('.json')) if os.path.isdir(ad) else []
        self.missing = []

    def nearest(self, lst, f, lo=0, hi=10 ** 9):
        cand = [x for x in lst if lo <= x <= hi] or lst
        if not cand:
            return None
        import bisect
        i = bisect.bisect_left(cand, f)
        best = min(cand[max(0, i - 1): i + 1], key=lambda x: abs(x - f))
        return best

    def load(self, p, f, lo=0, hi=10 ** 9, size=(W, H)):
        g = self.nearest(self.idx[p], f, lo, hi)
        if g != f:
            self.missing.append((p, f))
        im = Image.open(os.path.join(self.base, p, f'f_{g:04d}.png')).convert('RGB')
        if im.size != size:
            im = im.resize(size, Image.LANCZOS)
            im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=45, threshold=2))
        return im

    def anchors(self, f):
        g = self.nearest(self.anc, f)
        return json.load(open(os.path.join(self.base, 'anchors', f'f_{g:04d}.json'))) if g is not None else {}


S8A, S8B = 3090, 3434


def base_frame(src, f):
    t = f / FPS
    if f < S8A:
        return src.load('main', f, 0, S8A - 1)
    if f <= S8B:
        L = src.load('s8a', f, S8A, S8B, (W // 2, H))
        R = src.load('s8b', f, S8A, S8B, (W // 2, H))
        im = Image.new('RGB', (W, H)); im.paste(L, (0, 0)); im.paste(R, (W // 2, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((W // 2 - 2, 0, W // 2 + 2, H), fill=(235, 240, 250))
        # crossfade in from the last scene-7 frame
        k = (f - S8A) / 15.0
        if k < 1:
            prev = src.load('main', S8A - 1, 0, S8A - 1)
            im = Image.blend(prev, im, ease(k))
        return im
    im = src.load('main', f, S8B + 1, N - 1)
    k = (f - S8B - 1) / 20.0
    if k < 1:   # the two halves merge back into one engine
        L = src.load('s8a', S8B, S8A, S8B, (W // 2, H)); R = src.load('s8b', S8B, S8A, S8B, (W // 2, H))
        sp = Image.new('RGB', (W, H)); sp.paste(L, (0, 0)); sp.paste(R, (W // 2, 0))
        im = Image.blend(sp, im, ease(k))
    return im


def compose(src, f, subs):
    im = grade(base_frame(src, f))
    t = f / FPS
    # global fades: from black at the start, to black at the very end
    k = min(ease(t / 1.2), 1 - ease((t - 119.4) / 0.6))
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    overlays(layer, f, src.anchors(f) if f < S8A or f > S8B else {}, subs)
    out = im.convert('RGBA'); out.alpha_composite(layer)
    out = out.convert('RGB')
    if k < 0.999:
        out = Image.blend(Image.new('RGB', (W, H)), out, k)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frames', default=os.path.join(ROOT, '06_Rendered_Scenes', 'frames'))
    ap.add_argument('--out', default=os.path.join(ROOT, '07_Final', 'LS_Open_Closed_Loop_Arabic_120s.mp4'))
    ap.add_argument('--audio', default=os.path.join(ROOT, '04_Audio', 'final_audio_mix.wav'))
    ap.add_argument('--range', default='0-3599')
    ap.add_argument('--still', type=int, default=None)
    ap.add_argument('--crf', default='18')
    ap.add_argument('--preset', default='slow')
    args = ap.parse_args()
    subs = load_srt(os.path.join(ROOT, '05_Subtitles', 'arabic_subtitles.srt'))
    src = FrameSource(args.frames)
    if args.still is not None:
        compose(src, args.still, subs).save(args.out); print('still', args.out); return
    a, b = map(int, args.range.split('-'))
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
           '-i', '-']
    if os.path.exists(args.audio):
        cmd += ['-i', args.audio, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000']
    cmd += ['-c:v', 'libx264', '-preset', args.preset, '-crf', args.crf, '-pix_fmt', 'yuv420p', '-profile:v', 'high',
            '-tune', 'film', '-movflags', '+faststart', '-r', str(FPS), '-frames:v', str(b - a + 1),
            '-metadata', 'title=LS V8 Open Loop vs Closed Loop (Arabic)', '-metadata:s:a:0', 'language=ara',
            '-shortest' if False else '-t', f'{(b - a + 1) / FPS:.3f}', args.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    import time
    t0 = time.time()
    for f in range(a, b + 1):
        p.stdin.write(compose(src, f, subs).tobytes())
        if f % 300 == 0:
            print(f'frame {f}  {time.time() - t0:.0f}s', flush=True)
    p.stdin.close(); p.wait()
    miss = len(set(src.missing))
    print('done', args.out, 'substituted frames:', miss)
    rep = os.path.join(ROOT, '08_QA', 'rendering_report.txt')
    with open(rep, 'a') as fh:
        fh.write(f'assemble {args.out}: frames {a}-{b}, substituted (nearest-frame) frames: {miss}\n')


if __name__ == '__main__':
    main()
