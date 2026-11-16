#!/usr/bin/env python3
"""Phase 1 - environment verification and (optional) dependency setup.

  python3 setup.py            # report only
  python3 setup.py --install  # pip install requirements, fetch the Piper Arabic voice + Whisper QA model

This is a plain script (not a setuptools package)."""
import os, sys, shutil, subprocess, importlib, platform, json

ROOT = os.path.dirname(os.path.abspath(__file__))
VOICE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-ar_JO-kareem-medium.tar.bz2"
ASR_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-small.tar.bz2"
CACHE = os.environ.get("LS_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "ls_video"))


def check():
    rep = {"python": sys.version.split()[0], "platform": platform.platform(), "cpus": os.cpu_count()}
    for mod in ("bpy", "numpy", "PIL", "piper", "sherpa_onnx", "fontTools"):
        try:
            m = importlib.import_module(mod)
            rep[mod] = getattr(m, "__version__", None) or (m.app.version_string if mod == "bpy" else "ok")
        except Exception as e:
            rep[mod] = f"MISSING ({e.__class__.__name__})"
    try:
        from PIL import features
        rep["pillow_raqm"] = features.check("raqm")
    except Exception:
        pass
    for exe in ("ffmpeg", "ffprobe", "nvidia-smi", "blender"):
        rep[exe] = shutil.which(exe) or "not found"
    rep["noto_arabic"] = os.path.exists("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf")
    rep["voice_dir"] = os.path.join(CACHE, "vits-piper-ar_JO-kareem-medium")
    rep["voice_present"] = os.path.isdir(rep["voice_dir"])
    st = shutil.disk_usage(ROOT); rep["disk_free_gb"] = round(st.free / 1e9, 1)
    try:
        rep["ram_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except Exception:
        pass
    return rep


def fetch(url):
    os.makedirs(CACHE, exist_ok=True)
    name = url.rsplit("/", 1)[1]
    dst = os.path.join(CACHE, name.replace(".tar.bz2", ""))
    if not os.path.isdir(dst):
        tar = os.path.join(CACHE, name)
        subprocess.run(["curl", "-sSL", "-o", tar, url], check=True)
        subprocess.run(["tar", "xjf", tar, "-C", CACHE], check=True)
        os.remove(tar)
    return dst


if __name__ == "__main__":
    if "--install" in sys.argv:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")], check=True)
        print("voice:", fetch(VOICE_URL)); print("asr:", fetch(ASR_URL))
    r = check()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    os.makedirs(os.path.join(ROOT, "08_QA"), exist_ok=True)
    json.dump(r, open(os.path.join(ROOT, "08_QA", "environment_report.json"), "w"), indent=2)
