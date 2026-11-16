#!/usr/bin/env python3
"""One-command reproducible pipeline.

  python3 render_all.py              # full production (final quality, ~6 h on 4 CPU cores)
  python3 render_all.py --preview    # every 10th frame at 640x360 -> 07_Final/preview_animatic.mp4 (~8 min)

Steps: fonts -> narration (+SRT) -> Blender scene (.blend) -> Cycles frames (resume-capable)
       -> split-screen passes -> sound design & mix -> composite/encode -> QA.
"""
import os, sys, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
VOICE = os.environ.get("PIPER_VOICE_DIR", os.path.join(os.path.expanduser("~"), ".cache", "ls_video",
                                                        "vits-piper-ar_JO-kareem-medium"))


def run(*a):
    print(">>", " ".join(a), flush=True)
    subprocess.run(list(a), check=True, cwd=ROOT)


if __name__ == "__main__":
    preview = "--preview" in sys.argv
    run(PY, "make_fonts.py")
    run(PY, "generate_narration.py", "--voice", VOICE)
    run(PY, "03_Blender/create_scenes.py", "--quality", "final")
    frames = os.path.join(ROOT, "06_Rendered_Scenes", "frames_preview" if preview else "frames")
    extra = ["--step", "10", "--res", "640x360", "--samples", "2"] if preview else []
    run(PY, "03_Blender/render_scenes.py", "--frames", "0-3089", "--out", frames, *extra)
    run(PY, "03_Blender/render_scenes.py", "--frames", "3435-3599", "--out", frames, *extra)
    for p in ("s8a", "s8b"):
        run(PY, "03_Blender/render_scenes.py", "--frames", "3090-3434", "--pass", p, "--out", frames, *extra)
    run(PY, "generate_audio.py")
    out = os.path.join(ROOT, "07_Final", "preview_animatic.mp4" if preview else "LS_Open_Closed_Loop_Arabic_120s.mp4")
    run(PY, "assemble_video.py", "--frames", frames, "--out", out, *(["--preset", "veryfast", "--crf", "23"] if preview else []))
    if not preview:
        run(PY, "export_scene_clips.py")
        run(PY, "qa_check.py")
