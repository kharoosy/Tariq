#!/usr/bin/env python3
"""Phase 9 - automated QA of the final deliverable. Writes 08_QA/*.txt and prints a summary."""
import os, re, json, subprocess
ROOT = os.path.dirname(os.path.abspath(__file__))
MP4 = os.path.join(ROOT, "07_Final", "LS_Open_Closed_Loop_Arabic_120s.mp4")
SRT = os.path.join(ROOT, "07_Final", "LS_Open_Closed_Loop_Arabic_120s.srt")
QA = os.path.join(ROOT, "08_QA")


def sh(*a):
    return subprocess.run(list(a), capture_output=True, text=True)


res = {}
pr = json.loads(sh("ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", MP4).stdout)
v = [s for s in pr["streams"] if s["codec_type"] == "video"][0]
a = [s for s in pr["streams"] if s["codec_type"] == "audio"]
res["duration_s"] = float(pr["format"]["duration"])
res["video_duration_s"] = float(v.get("duration", 0))
res["nb_frames"] = int(v.get("nb_frames", 0))
res["resolution"] = f"{v['width']}x{v['height']}"
res["fps"] = v["r_frame_rate"]
res["video_codec"] = f"{v['codec_name']} ({v.get('profile')}) {v.get('pix_fmt')}"
res["audio_streams"] = [f"{s['codec_name']} {s['sample_rate']} Hz {s['channels']} ch" for s in a]
res["size_mb"] = round(os.path.getsize(MP4) / 1e6, 1)

# full decode (playability) + black frames + frozen frames
bd = sh("ffmpeg", "-hide_banner", "-i", MP4, "-vf", "blackdetect=d=0.25:pic_th=0.97,freezedetect=n=0.001:d=1.5",
        "-an", "-f", "null", "-")
res["decode_errors"] = len([l for l in bd.stderr.splitlines() if "error" in l.lower() and "blackdetect" not in l])
res["black_segments"] = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd.stderr)
res["frozen_segments"] = re.findall(r"freeze_start: ([\d.]+)", bd.stderr)

# audio loudness
eb = sh("ffmpeg", "-hide_banner", "-i", MP4, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-").stderr
summ = eb[eb.rfind("Summary"):]
res["loudness_LUFS"] = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1))
res["true_peak_dBFS"] = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ).group(1))
vol = sh("ffmpeg", "-hide_banner", "-i", os.path.join(ROOT, "04_Audio", "arabic_narration.wav"), "-af",
         "volumedetect", "-f", "null", "-").stderr
res["narration_mean_dB"] = float(re.search(r"mean_volume: (-?[\d.]+)", vol).group(1))

# subtitles
txt = open(SRT, encoding="utf-8").read()
cues = re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})", txt)
ts = [(int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000, int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000)
      for h, m, s, ms, h2, m2, s2, ms2 in cues]
res["subtitle_cues"] = len(ts)
res["subtitle_overlaps"] = sum(1 for (a1, b1), (a2, b2) in zip(ts, ts[1:]) if a2 < b1)
res["subtitle_last_end_s"] = max(b for _, b in ts)
res["subtitle_arabic"] = bool(re.search(r"[\u0600-\u06FF]", txt))

checks = {
    "MP4 exists": os.path.exists(MP4),
    "Duration exactly 120 s (±1 frame)": abs(res["duration_s"] - 120) <= 1 / 30 + 1e-3,
    "Resolution >= 1920x1080": v["width"] >= 1920 and v["height"] >= 1080,
    "30 fps": v["r_frame_rate"] in ("30/1", "30000/1000"),
    "H.264": v["codec_name"] == "h264",
    "3600 frames": res["nb_frames"] == 3600,
    "Audio stream present": len(a) >= 1,
    "Decodes without errors": res["decode_errors"] == 0,
    "No black segments after the 1.2 s fade-in / before the 0.6 s fade-out":
        all(float(s) < 1.3 or float(s) > 119.3 for s, e in res["black_segments"]),
    "Loudness -16 LUFS ±1": abs(res["loudness_LUFS"] + 16) <= 1,
    "True peak <= -1 dBFS": res["true_peak_dBFS"] <= -1.0,
    "Arabic subtitles, no overlaps, inside 120 s": res["subtitle_arabic"] and res["subtitle_overlaps"] == 0 and res[
        "subtitle_last_end_s"] <= 120,
}
lines = ["FINAL QA (automated)", ""] + [f"[{'PASS' if ok else 'FAIL'}] {k}" for k, ok in checks.items()] + ["", json.dumps(res, indent=1, ensure_ascii=False)]
open(os.path.join(QA, "final_qa_automated.txt"), "w", encoding="utf-8").write("\n".join(lines))
open(os.path.join(QA, "audio_validation.txt"), "w").write(
    f"Integrated loudness: {res['loudness_LUFS']} LUFS (target -16)\nTrue peak: {res['true_peak_dBFS']} dBFS (limit -1.5)\n"
    f"Narration mean level (pre-mix stem): {res['narration_mean_dB']} dB\nAudio streams: {res['audio_streams']}\n"
    + summ)
print("\n".join(lines))
