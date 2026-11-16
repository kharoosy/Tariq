#!/usr/bin/env python3
"""Generate the Arabic narration with Piper TTS (voice: ar_JO-kareem-medium, male).

Each subtitle chunk is synthesized separately so subtitle timing comes from the
real measured audio, not from estimates. Output:
  04_Audio/narration_chunks/*.wav
  04_Audio/arabic_narration.wav        (120 s, chunks placed on the timeline)
  05_Subtitles/arabic_subtitles.srt    (+ copy in 07_Final)
  05_Subtitles/arabic_script.txt
  01_Project/narration_timing.json
Usage: python3 generate_narration.py [--voice DIR]
"""
import json, os, sys, wave, argparse
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
TL = json.load(open(os.path.join(ROOT, "01_Project", "scene_timeline.json"), encoding="utf-8"))
SR_OUT = 48000
GAP = 0.22           # pause between chunks inside a scene (s)
LENGTH_SCALE = 1.0   # >1 = slower. Never pushed below 0.82 (no unnatural speed-up)


def synth(voice, text, length_scale):
    from piper import SynthesisConfig
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        voice.synthesize_wav(text, w, syn_config=SynthesisConfig(
            length_scale=length_scale, noise_scale=0.6, noise_w_scale=0.75))
    buf.seek(0)
    with wave.open(buf) as r:
        sr = r.getframerate()
        a = np.frombuffer(r.readframes(r.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    # trim leading/trailing silence
    idx = np.where(np.abs(a) > 0.01)[0]
    if len(idx):
        a = a[max(0, idx[0] - int(0.03 * sr)): idx[-1] + int(0.08 * sr)]
    # resample to 48 kHz (linear is fine after Piper's band-limited 22 kHz output)
    n = int(len(a) * SR_OUT / sr)
    a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=os.environ.get("PIPER_VOICE_DIR", "/tmp/claude-0/voice"))
    args = ap.parse_args()
    from piper import PiperVoice
    onnx = [f for f in os.listdir(args.voice) if f.endswith(".onnx")][0]
    voice = PiperVoice.load(os.path.join(args.voice, onnx))

    out_dir = os.path.join(ROOT, "04_Audio", "narration_chunks"); os.makedirs(out_dir, exist_ok=True)
    total = np.zeros(int(TL["duration"] * SR_OUT), np.float32)
    timing, subs, script = [], [], []
    for sc in TL["scenes"]:
        avail = sc["end"] - sc["voice_start"] - 0.2
        ls = LENGTH_SCALE
        while True:
            clips = [synth(voice, c["tts"].replace("،", ""), ls) for c in sc["chunks"]]
            dur = sum(len(c) for c in clips) / SR_OUT + GAP * (len(clips) - 1)
            if dur <= avail or ls <= 0.82:
                break
            ls = round(ls - 0.03, 3)
        if dur > avail:
            print(f"WARNING scene {sc['id']}: speech {dur:.2f}s exceeds slot {avail:.2f}s")
        t = sc["voice_start"]
        for i, (c, clip) in enumerate(zip(sc["chunks"], clips)):
            s0 = int(t * SR_OUT)
            seg = clip[: max(0, len(total) - s0)]
            total[s0:s0 + len(seg)] += seg
            d = len(clip) / SR_OUT
            fn = os.path.join(out_dir, f"s{sc['id']:02}_c{i+1}.wav")
            write_wav(fn, clip)
            subs.append((t, t + d, c["sub"]))
            timing.append({"scene": sc["id"], "chunk": i + 1, "start": round(t, 3), "end": round(t + d, 3),
                           "length_scale": ls, "text": c["sub"]})
            t += d + GAP
        script.append(f"[المشهد {sc['id']} — {sc['name']}  {sc['start']:.0f}s–{sc['end']:.0f}s]\n" +
                      "\n".join(c["sub"] for c in sc["chunks"]) + "\n")
        print(f"scene {sc['id']}: speech {dur:5.2f}s / slot {avail:5.2f}s  length_scale={ls}")

    # loudness: peak-normalise; final LUFS mastering happens in assemble_video.py
    total *= 0.89 / max(1e-6, np.abs(total).max())
    write_wav(os.path.join(ROOT, "04_Audio", "arabic_narration.wav"), total)

    srt = []
    for i, (a, b, txt) in enumerate(subs, 1):
        # keep subtitles on screen a little longer than the audio, never overlapping the next
        nxt = subs[i][0] if i < len(subs) else TL["duration"]
        b2 = min(b + 0.6, nxt - 0.05, TL["duration"])
        srt.append(f"{i}\n{srt_time(a)} --> {srt_time(b2)}\n‫{txt}‬\n")
    srt_txt = "\n".join(srt)
    for p in ("05_Subtitles/arabic_subtitles.srt", "07_Final/LS_Open_Closed_Loop_Arabic_120s.srt"):
        open(os.path.join(ROOT, p), "w", encoding="utf-8").write(srt_txt)
    open(os.path.join(ROOT, "05_Subtitles", "arabic_script.txt"), "w", encoding="utf-8").write("\n".join(script))
    json.dump(timing, open(os.path.join(ROOT, "01_Project", "narration_timing.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def write_wav(fn, a):
    a16 = (np.clip(a, -1, 1) * 32767).astype(np.int16)
    with wave.open(fn, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR_OUT); w.writeframes(a16.tobytes())


if __name__ == "__main__":
    main()
