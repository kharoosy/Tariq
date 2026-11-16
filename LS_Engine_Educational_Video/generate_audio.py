#!/usr/bin/env python3
"""Original procedural sound design + music + final mix (no third-party audio -> no licensing issues).

Outputs (48 kHz):
  04_Audio/background_music.wav             original ambient score (D minor), 120 s
  04_Audio/sound_effects/*.wav              engine idle / cold start, injector clicks, combustion thumps,
                                            ECU data blips, whooshes, closed-loop power-up, final hit
  04_Audio/final_audio_mix.wav              narration + music + SFX, ducked, mastered to -16 LUFS / -1.5 dBTP
Effects that belong to on-screen events (combustion, injector clicks, cold start, O2 switching) are
placed from the same kinematics/timeline used by the renderer (03_Blender/animate_engine.py).
"""
import os, sys, json, wave, subprocess
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, '03_Blender'))
try:
    import bpy  # noqa: F401  (mathutils for animate_engine)
except Exception:
    pass
import animate_engine as A

SR = 48000
DUR = 120.0
NS = int(SR * DUR)
rng = np.random.default_rng(7)
SFX_DIR = os.path.join(ROOT, '04_Audio', 'sound_effects')
os.makedirs(SFX_DIR, exist_ok=True)


def wav_write(fn, a):
    a = np.asarray(a, np.float32)
    if a.ndim == 1:
        a = np.stack([a, a], 1)
    a16 = (np.clip(a, -1, 1) * 32767).astype(np.int16)
    with wave.open(fn, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(a16.tobytes())


def wav_read(fn):
    with wave.open(fn) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    a = a.reshape(-1, ch)
    if sr != SR:
        n = int(len(a) * SR / sr)
        a = np.stack([np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a[:, c]) for c in range(ch)], 1)
    return a


def lowpass(x, fc):
    """FFT brick-ish low-pass with smooth roll-off (zero phase)."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 / np.sqrt(1 + (f / fc) ** 4)
    return np.fft.irfft(X * (g if X.ndim == 1 else g[:, None]), n=len(x), axis=0)


def highpass(x, fc):
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** 4)
    return np.fft.irfft(X * (g if X.ndim == 1 else g[:, None]), n=len(x), axis=0)


def env_curve(points):
    """piecewise-linear envelope over the whole timeline from (t, value) points."""
    t = np.arange(NS) / SR
    ts, vs = zip(*points)
    return np.interp(t, ts, vs).astype(np.float32)


def place(buf, clip, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= len(buf) or i + len(clip) <= 0:
        return
    c = clip if clip.ndim == 2 else np.stack([clip * (1 - pan) ** 0.5, clip * (1 + pan) ** 0.5], 1) / 1.0
    j = min(len(buf), i + len(c))
    buf[max(0, i):j] += gain * c[max(0, -i): j - i]


# ------------------------------------------------------------------ music
def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def music():
    t = np.arange(NS) / SR
    out = np.zeros((NS, 2), np.float32)
    # D minor: Dm - Bb - F - C  (i - VI - III - VII), 8 s per chord
    chords = [[50, 57, 62, 65, 69], [46, 53, 58, 62, 65], [41, 53, 57, 60, 65], [48, 55, 60, 64, 67]]
    seg = 8.0
    for k in range(int(DUR / seg) + 1):
        ch = chords[k % 4]
        t0 = k * seg
        a, b = int(max(0, t0 - 1.5) * SR), int(min(DUR, t0 + seg + 1.5) * SR)
        tt = t[a:b] - t0
        envl = np.clip((tt + 1.5) / 2.5, 0, 1) * np.clip((seg + 1.5 - tt) / 2.5, 0, 1)
        envl = envl ** 1.5
        for j, m in enumerate(ch):
            f = note(m)
            for det, pan in ((-0.12, -0.6), (0.12, 0.6)):
                ph = 2 * np.pi * f * (1 + det / 100) * t[a:b] + rng.uniform(0, 6.28)
                wv = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)
                g = 0.05 / (1 + j * 0.25)
                out[a:b, 0] += (g * (1 - pan) / 2 * wv * envl).astype(np.float32)
                out[a:b, 1] += (g * (1 + pan) / 2 * wv * envl).astype(np.float32)
        # sub root
        out[a:b] += (0.09 * np.sin(2 * np.pi * note(ch[0] - 12) * t[a:b]) * envl)[:, None]
    out = lowpass(out, 2200)
    # soft pulse (8th notes @ 96 bpm) - enters with the ECU section, stronger in closed loop
    pulse = np.zeros((NS, 2), np.float32)
    step = 60 / 96 / 2
    pl = np.arange(int(0.35 * SR)) / SR
    for i in range(int(DUR / step)):
        tt = i * step
        ch = chords[int(tt // seg) % 4]
        m = ch[[2, 3, 4, 3][i % 4]] + 12
        tone = np.sin(2 * np.pi * note(m) * pl) * np.exp(-pl * 14) + 0.3 * np.sin(4 * np.pi * note(m) * pl) * np.exp(-pl * 22)
        lvl = 0.035 * (A.ramp(tt, 26.5, 29) * (1 - 0.5 * A.ramp(tt, 38, 40)) + 0.6 * A.ramp(tt, 66, 68.5)) * \
            (1 - A.ramp(tt, 112.5, 114.5))
        place(pulse, tone, tt, lvl, pan=0.35 * (1 if i % 2 else -1))
    out += lowpass(pulse, 5000)
    # overall arc
    out *= env_curve([(0, 0.0), (2.5, 0.8), (12, 0.85), (38, 0.7), (40, 0.6), (64, 0.7), (68, 0.95), (110, 0.95),
                      (114.5, 1.1), (118.5, 1.1), (120, 0.0)])[:, None]
    # reverb-ish widening: short multi-tap delay
    rev = np.zeros_like(out)
    for dly, g in ((0.031, 0.35), (0.047, 0.3), (0.071, 0.25), (0.113, 0.2), (0.173, 0.15)):
        d = int(dly * SR)
        rev[d:, 0] += g * out[:-d, 1]; rev[d:, 1] += g * out[:-d, 0]
    return out + 0.6 * rev


# ------------------------------------------------------------------ SFX
def exhaust_pulse(n=None):
    L = int(0.05 * SR); tt = np.arange(L) / SR
    nz = rng.standard_normal(L) * np.exp(-tt * 140)
    body = np.sin(2 * np.pi * 95 * tt) * np.exp(-tt * 55) + 0.5 * np.sin(2 * np.pi * 190 * tt) * np.exp(-tt * 80)
    return (0.6 * body + 0.4 * nz).astype(np.float32)


def engine_bed():
    """cross-plane V8 burble: firing pulses at engine speed with bank-dependent timbre/pan."""
    out = np.zeros((NS, 2), np.float32)
    # real-world rpm (audio is real-time even when the picture is slow-motion)
    rpm_pts = [(0, 680), (12, 680), (38.0, 680), (38.6, 0), (39.6, 0), (40.6, 200), (40.65, 1500), (41.6, 1150),
               (43, 1050), (55.5, 1020), (62, 720), (120, 700)]
    gain_pts = [(0, 0.0), (2.0, 0.55), (12.0, 0.45), (13.0, 0.08), (26.0, 0.08), (27.5, 0.35), (38.0, 0.35),
                (38.8, 0.0), (40.55, 0.0), (40.65, 0.9), (42.0, 0.5), (55, 0.4), (88, 0.3), (103, 0.35),
                (114.5, 0.45), (119.6, 0.3), (120, 0.0)]
    rpm = env_curve(rpm_pts); g = env_curve(gain_pts)
    t = 0.0
    k = 0
    pulse = exhaust_pulse()
    bank = {1: -1, 3: -1, 5: -1, 7: -1, 2: 1, 4: 1, 6: 1, 8: 1}
    while t < DUR:
        i = int(t * SR)
        r = rpm[min(i, NS - 1)]
        if r < 60:
            t += 0.01; continue
        cyl = A.FIRING_ORDER[k % 8]
        amp = (0.85 + 0.3 * (cyl in (1, 8, 4, 5))) * (0.9 + 0.2 * rng.random())
        place(out, pulse * amp, t + rng.normal(0, 0.0006), g[min(i, NS - 1)], pan=0.35 * bank[cyl])
        t += 60.0 / r / 4.0 * (1 + rng.normal(0, 0.01))
        k += 1
    out = lowpass(out, 900) * 1.4
    # cold-start cranking: starter whine + compression chugs 39.6-40.6
    a, b = int(39.6 * SR), int(40.62 * SR)
    tt = np.arange(b - a) / SR
    whine = 0.08 * np.sin(2 * np.pi * (520 + 60 * np.sin(2 * np.pi * 3 * tt)) * tt) * (1 - np.exp(-tt * 20))
    chug = 0.35 * (np.sin(2 * np.pi * 7.0 * tt) > 0.6) * np.sin(2 * np.pi * 70 * tt)
    out[a:b] += lowpass((whine + chug).astype(np.float32), 3000)[:, None]
    return out


def click():
    L = int(0.012 * SR); tt = np.arange(L) / SR
    return (np.sin(2 * np.pi * 3200 * tt) * np.exp(-tt * 900) + 0.4 * rng.standard_normal(L) * np.exp(-tt * 1500)).astype(
        np.float32)


def thump():
    L = int(0.45 * SR); tt = np.arange(L) / SR
    f = 70 * np.exp(-tt * 3) + 38
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-tt * 7) + 0.25 * rng.standard_normal(L) * np.exp(-tt * 40)).astype(np.float32)


def blip(freq):
    L = int(0.09 * SR); tt = np.arange(L) / SR
    return (np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 45) * np.clip(tt * 600, 0, 1)).astype(np.float32)


def whoosh(length=1.2, up=True):
    L = int(length * SR); tt = np.arange(L) / SR
    n = rng.standard_normal(L).astype(np.float32)
    envl = np.sin(np.pi * np.clip(tt / length, 0, 1)) ** 2
    out = np.zeros(L, np.float32)
    # time-varying band via crossfaded low-passes
    lo, hi = lowpass(n, 400), lowpass(n, 3500)
    x = tt / length if up else 1 - tt / length
    out = (lo * (1 - x) + hi * x) * envl
    return out * 0.6


def power_up():
    L = int(2.2 * SR); tt = np.arange(L) / SR
    f = 220 * 2 ** (tt / 2.2 * 1.0)
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = (np.sin(ph) + 0.5 * np.sin(1.5 * ph) + 0.3 * np.sin(2 * ph)) * np.clip(tt / 1.8, 0, 1) ** 2 * np.exp(
        -np.clip(tt - 1.9, 0, None) * 12)
    L2 = int(1.6 * SR); t2 = np.arange(L2) / SR
    chime = sum(np.sin(2 * np.pi * note(m) * t2) * np.exp(-t2 * 3) for m in (74, 81, 86)) / 3
    return np.concatenate([tone * 0.4, chime * 0.5]).astype(np.float32)


def final_hit():
    L = int(4.0 * SR); tt = np.arange(L) / SR
    boom = np.sin(2 * np.pi * (45 + 30 * np.exp(-tt * 6)) * tt) * np.exp(-tt * 1.4)
    chord = sum(np.sin(2 * np.pi * note(m) * tt) * np.exp(-tt * 0.9) for m in (50, 57, 62, 65, 69)) / 5
    return (0.7 * boom + 0.5 * lowpass(chord.astype(np.float32), 3000)).astype(np.float32)


def sfx_track():
    out = np.zeros((NS, 2), np.float32)
    # combustion thumps + injector clicks in slow-motion scene 2, synced to the rendered kinematics
    ck, th = click(), thump()
    prev = {}
    for f in range(int(12.5 * 30), int(26.4 * 30)):
        a0, a1 = A.crank_angle(f), A.crank_angle(f + 1)
        for n in A.CYL:
            c0, c1 = A.cycle_angle(n, a0), A.cycle_angle(n, a1)
            if c1 < c0:   # wrapped through compression TDC -> combustion starts
                place(out, th, f / 30, 0.55, pan=-0.3 if A.CYL[n]['side'] == 'L' else 0.3)
            inj0 = A.injecting(n, a0, 1.0); inj1 = A.injecting(n, a1, 1.0)
            if inj1 and not inj0:
                place(out, ck, f / 30, 0.22, pan=-0.4 if A.CYL[n]['side'] == 'L' else 0.4)
    # ECU data blips (sensors -> ECU) in scene 3, then O2 switching ticks in closed loop
    for i, tt in enumerate(np.arange(27.6, 37.5, 0.45)):
        place(out, blip([1320, 1760, 1980, 1480][i % 4]), tt, 0.10, pan=-0.4)
    prev_v = None
    for f in range(int(66.5 * 30), int(102.5 * 30)):
        v = A.env(f / 30)['o2v']
        if prev_v is not None and (prev_v - 0.45) * (v - 0.45) < 0:
            place(out, blip(2200 if v > 0.45 else 1650), f / 30, 0.07, pan=-0.5)
        prev_v = v
    # transitions
    for tt in (11.6, 26.1, 37.6, 54.6, 67.6, 87.6, 102.6):
        place(out, whoosh(1.2), tt - 0.2, 0.32)
    place(out, whoosh(1.6, up=False), 114.1, 0.4)
    place(out, power_up(), 64.2, 0.35)
    place(out, final_hit(), 115.5, 0.45)
    return out


# ------------------------------------------------------------------ mix
def main():
    narr = wav_read(os.path.join(ROOT, '04_Audio', 'arabic_narration.wav'))
    narr = narr[:, :1] if narr.shape[1] > 1 else narr
    narr = np.concatenate([narr, np.zeros((max(0, NS - len(narr)), 1), np.float32)])[:NS]
    narr = highpass(narr, 80)
    # gentle presence + compression for intelligibility
    pk = np.abs(narr).max(); narr = narr / max(pk, 1e-6) * 0.9
    narr = np.sign(narr) * (1 - np.exp(-np.abs(narr) * 2.2)) / (1 - np.exp(-2.2))
    narr_st = np.repeat(narr, 2, 1)

    mus = music(); eng = engine_bed(); fx = sfx_track()
    wav_write(os.path.join(ROOT, '04_Audio', 'background_music.wav'), mus / max(1e-6, np.abs(mus).max()) * 0.9)
    wav_write(os.path.join(SFX_DIR, 'engine_idle_cold_start.wav'), eng / max(1e-6, np.abs(eng).max()) * 0.9)
    wav_write(os.path.join(SFX_DIR, 'sfx_events.wav'), fx / max(1e-6, np.abs(fx).max()) * 0.9)
    for nm, clip in (('injector_click', click()), ('combustion_thump', thump()), ('ecu_blip', blip(1760)),
                     ('whoosh', whoosh()), ('closed_loop_power_up', power_up()), ('final_hit', final_hit())):
        wav_write(os.path.join(SFX_DIR, nm + '.wav'), clip / max(1e-6, np.abs(clip).max()) * 0.9)

    # side-chain ducking driven by the narration envelope
    e = np.abs(narr[:, 0])
    k = int(0.25 * SR)
    e = np.convolve(e, np.ones(k) / k, mode='same')
    duck = 1 - 0.62 * np.clip(e / (np.percentile(e[e > 1e-4], 60) + 1e-6), 0, 1)
    duck = np.convolve(duck, np.ones(int(0.1 * SR)) / int(0.1 * SR), mode='same')[:, None].astype(np.float32)
    mus_n = mus / max(1e-6, np.sqrt(np.mean(mus ** 2))) * 0.045
    eng_n = eng / max(1e-6, np.abs(eng).max()) * 0.33
    fx_n = fx / max(1e-6, np.abs(fx).max()) * 0.42
    mix = narr_st * 0.80 + (mus_n + eng_n) * duck + fx_n * (0.55 + 0.45 * duck)
    mix /= max(1e-6, np.abs(mix).max()) / 0.95
    raw = os.path.join(ROOT, '04_Audio', 'mix_premaster.wav')
    wav_write(raw, mix)
    # two-pass EBU R128 loudness normalisation
    out = os.path.join(ROOT, '04_Audio', 'final_audio_mix.wav')
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', raw, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json',
                        '-f', 'null', '-'], capture_output=True, text=True)
    js = json.loads(r.stderr[r.stderr.rindex('{'):r.stderr.rindex('}') + 1])
    af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw, '-af', af, '-ar', '48000', '-t', '120', out],
                   check=True)
    os.remove(raw)
    print('wrote', out, 'input loudness', js['input_i'])


if __name__ == '__main__':
    main()
