# Production plan & environment log

## 1. Environment (verified, not assumed)

| Resource | Found | Decision |
|---|---|---|
| CPU / GPU | 4 vCPU, **no GPU**, 15 GB RAM | CPU rendering only |
| Blender | not installed; `download.blender.org` blocked by the network policy | `pip install bpy==5.3.0` (official Blender-as-a-module wheel from PyPI) |
| Eevee | works only through Mesa llvmpipe (software GL): 45–77 s/frame at 720p | rejected |
| Cycles (CPU) | 20 s/frame at 720p with defaults → tuned to **≈5–8 s/frame** | chosen (see §3) |
| FFmpeg / FFprobe | installed (system) | encoding, loudness, QA |
| Arabic TTS | Hugging Face blocked; GitHub reachable | Piper voice **ar_JO-kareem-medium** (male) fetched from the sherpa-onnx GitHub release, run with `piper-tts` |
| ASR for QA | Whisper-small (int8 ONNX) from the sherpa-onnx GitHub release | narration intelligibility check |
| Fonts | Noto Sans/Kufi Arabic + Noto Sans (apt `fonts-noto-core`, OFL) | merged with fontTools so Arabic + Latin labels render in one font |
| Text shaping | Pillow 11 + libraqm (HarfBuzz, FriBidi) | correct joined, right-to-left Arabic |

## 2. Pipeline (all steps scripted, see `render_all.py`)

1. `make_fonts.py` – merged Arabic/Latin fonts.
2. `generate_narration.py` – one TTS clip per subtitle cue, measured, placed on the timeline; writes the
   120 s narration WAV, SRT and timing JSON. Speech rate adapts per scene (Piper `length_scale` 0.82–0.91,
   never faster). Commas are removed from the TTS input (each comma inserted a ~0.5 s pause).
3. `03_Blender/create_scenes.py` – builds the procedural LS V8, ECU, sensors, harness, fuel map and studio
   (`build_engine.py`), camera, render settings → `LS_Engine_Master.blend` (animator embedded as text blocks).
4. `03_Blender/render_scenes.py` – resume-capable frame renderer; poses everything per frame with
   `animate_engine.apply_frame()` and exports projected label anchors.
   Passes: `main` (frames 0–3089, 3435–3599), `s8a`/`s8b` (scene 8 split screen, half width each).
5. `generate_audio.py` – original score + sound design, ducking, two-pass EBU R128 loudness (-16 LUFS).
6. `assemble_video.py` – upscale, bloom/vignette grade, split-screen & dissolves, motion graphics,
   burned-in Arabic subtitles, H.264 High / yuv420p / 30 fps + AAC 256 k.
7. `export_scene_clips.py` – per-scene clips + thumbnail. 8. `qa_check.py` – automated QA.

Preview gate: the full timeline was first rendered every 10th frame at 640×360 (2 spp) and composited
into an animatic; framing, label placement, timing and lighting were corrected from two preview rounds
before the final render.

## 3. Render budget decisions

* 3D is rendered at **1280×720**, 4 samples (adaptive), OpenImageDenoise (balanced quality, fast prefilter),
  bounces 3/1/1/1, transparent 5, emission sampling disabled for the small emitters (particles, harness,
  x-ray rim glow). Frames are upscaled to 1920×1080 (Lanczos + light unsharp mask); **all text, diagrams
  and subtitles are drawn natively at 1920×1080**. Native 1080p Cycles would have needed ≈2.25× the
  render time (~14 h on this machine).
* Script narration was tightened (same meaning, fewer filler words) because the only available male
  Arabic voice speaks ≈9 characters/s; the original script measured ≈137 s of speech for a 120 s video.

## 4. Known limitations

* Voice: Piper `ar_JO-kareem` is a **Jordanian/Levantine-trained** male voice. No free, locally-runnable
  Emirati or Gulf voice was reachable from this environment. The *script* uses Gulf/Emirati wording
  (بنشوف، هني، عشان، يقدر، بس), but the accent is not Emirati. Whisper ASR transcribes the narration
  almost word-for-word; the voice softens «غ» in some words (e.g. التغذية).
* Simplified engine details – see `technical_validation.md`.
