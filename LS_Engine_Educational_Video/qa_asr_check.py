#!/usr/bin/env python3
"""QA: transcribe each narration chunk with Whisper-small (sherpa-onnx, offline) to verify intelligibility."""
import sys, os, glob, json, wave
import numpy as np, sherpa_onnx
M = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/asr/sherpa-onnx-whisper-small"
rec = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=f"{M}/small-encoder.int8.onnx", decoder=f"{M}/small-decoder.int8.onnx",
                                                 tokens=f"{M}/small-tokens.txt", language="ar", task="transcribe", num_threads=4)
ROOT = os.path.dirname(os.path.abspath(__file__))
timing = json.load(open(f"{ROOT}/01_Project/narration_timing.json", encoding="utf-8"))
out = []
for t in timing:
    fn = f"{ROOT}/04_Audio/narration_chunks/s{t['scene']:02}_c{t['chunk']}.wav"
    with wave.open(fn) as w:
        sr = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    a = np.interp(np.arange(0, len(a), sr / 16000), np.arange(len(a)), a).astype(np.float32)
    s = rec.create_stream(); s.accept_waveform(16000, a); rec.decode_stream(s)
    out.append(f"S{t['scene']}C{t['chunk']}\n  script: {t['text']}\n  heard : {s.result.text.strip()}")
rep = "Whisper-small (offline) transcription of each synthesized narration chunk\n\n" + "\n".join(out)
open(f"{ROOT}/08_QA/audio_asr_check.txt", "w", encoding="utf-8").write(rep); print(rep)
