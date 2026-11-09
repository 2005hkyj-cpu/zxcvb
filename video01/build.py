"""2027 정미년 띠별 운세 영상 빌드 스크립트.

1) scenes.json의 내레이션을 문장 단위로 나눠 오프라인 TTS(sherpa-onnx)로 합성
2) 문장마다 1920x1080 화면(제목 + 자막)을 Playwright로 렌더링
3) ffmpeg로 이미지와 음성을 이어 붙여 output/video01.mp4 생성 (+ 자막 .srt, 썸네일)

사용법: python3 build.py --model-dir <vits-mimic3-ko_KO-kss_low 경로>
"""
import argparse
import html
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
WORK = OUT / "work"
GAP = 0.45  # 문장 사이 쉬는 시간(초)

DIGITS = "영일이삼사오육칠팔구"


def sino(n: int) -> str:
    """정수를 한자어 수사(이천이십칠)로 바꾼다."""
    if n == 0:
        return "영"
    out = ""
    for value, name in ((10000, "만"), (1000, "천"), (100, "백"), (10, "십")):
        q, n = divmod(n, value)
        if q:
            out += ("" if q == 1 and value != 10000 else sino(q) if value == 10000 else DIGITS[q]) + name
    if n:
        out += DIGITS[n]
    return out


def speakable(text: str) -> str:
    return re.sub(r"\d+", lambda m: sino(int(m.group())), text)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return [p for p in parts if p]


def tts_engine(model_dir: Path):
    import sherpa_onnx

    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model_dir / "ko_KO-kss_low.onnx"),
                tokens=str(model_dir / "tokens.txt"),
                data_dir=str(model_dir / "espeak-ng-data"),
            ),
            num_threads=4,
        )
    )
    return sherpa_onnx.OfflineTts(cfg)


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@500;700;900&family=Noto+Serif+KR:wght@700;900&display=block" rel="stylesheet">
<style>
*{{margin:0;box-sizing:border-box}}
body{{width:1920px;height:1080px;overflow:hidden;font-family:'Noto Sans KR',sans-serif;
background:radial-gradient(ellipse at 50% 35%,#7a1d1d 0%,#3d0b0b 55%,#1a0505 100%);color:#fff}}
.frame{{position:absolute;inset:36px;border:3px solid rgba(232,190,106,.55);border-radius:6px}}
.frame:after{{content:"";position:absolute;inset:12px;border:1px solid rgba(232,190,106,.3)}}
.seal{{position:absolute;right:110px;top:90px;width:150px;height:150px;border-radius:50%;
border:4px solid #e8be6a;color:#e8be6a;display:flex;align-items:center;justify-content:center;
font-family:'Noto Serif KR';font-size:76px;font-weight:900;opacity:.85}}
.wrap{{position:absolute;left:150px;right:150px;top:150px;height:560px;display:flex;flex-direction:column;justify-content:center}}
.kicker{{font-size:44px;font-weight:700;color:#e8be6a;letter-spacing:4px;margin-bottom:26px}}
.headline{{font-family:'Noto Serif KR';font-size:{hsize}px;font-weight:900;line-height:1.2;
white-space:pre-line;text-shadow:0 6px 24px rgba(0,0,0,.5)}}
.sub{{margin-top:30px;font-size:46px;font-weight:500;color:#f3dfb4}}
.cap{{position:absolute;left:120px;right:120px;bottom:80px;min-height:170px;padding:26px 44px;
background:rgba(0,0,0,.62);border-radius:18px;font-size:50px;font-weight:700;line-height:1.45;
display:flex;align-items:center;justify-content:center;text-align:center;word-break:keep-all}}
</style></head><body><div class="frame"></div><div class="seal">未</div>
<div class="wrap"><div class="kicker">{kicker}</div><div class="headline">{headline}</div><div class="sub">{sub}</div></div>
{cap}</body></html>"""

THUMB = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@900&family=Noto+Serif+KR:wght@900&display=block" rel="stylesheet">
<style>*{margin:0}body{width:1280px;height:720px;overflow:hidden;font-family:'Noto Sans KR';
background:radial-gradient(circle at 75% 50%,#c0392b 0%,#6b0f0f 50%,#1f0404 100%);color:#fff;position:relative}
.y{position:absolute;left:60px;top:50px;font-size:58px;font-weight:900;color:#ffd76a}
.t{position:absolute;left:60px;top:150px;font-size:150px;font-weight:900;line-height:1.08;
-webkit-text-stroke:4px #000;paint-order:stroke fill;text-shadow:0 10px 30px rgba(0,0,0,.6)}
.t b{color:#ffd76a}
.c{position:absolute;right:60px;top:110px;width:400px;height:400px;border-radius:50%;
border:10px solid #ffd76a;display:flex;align-items:center;justify-content:center;
font-family:'Noto Serif KR';font-size:250px;font-weight:900;color:#ffd76a;background:rgba(0,0,0,.25)}
.s{position:absolute;left:60px;bottom:50px;font-size:60px;font-weight:900;background:#ffd76a;color:#3d0b0b;padding:6px 26px;border-radius:10px}
</style></head><body><div class="y">2027 정미년 · 붉은 양의 해</div>
<div class="t">내년 대박<br><b>나는 띠</b></div><div class="c">未</div>
<div class="s">TOP 3 공개 + 조심할 띠</div></body></html>"""


def fmt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True, type=Path)
    args = ap.parse_args()

    import numpy as np
    import soundfile as sf

    data = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)
    tts = tts_engine(args.model_dir)

    clips, srt, jobs, t = [], [], [], 0.0
    for scene in data["scenes"]:
        lines = scene["headline"].count("\n") + 1
        hsize = 150 if lines == 1 else 120
        for i, sentence in enumerate(split_sentences(scene["narration"])):
            key = f"{scene['id']}_{i:02}"
            audio = tts.generate(speakable(sentence), sid=0, speed=0.95)
            samples = np.concatenate([np.asarray(audio.samples, dtype=np.float32),
                                      np.zeros(int(GAP * audio.sample_rate), dtype=np.float32)])
            wav = WORK / f"{key}.wav"
            sf.write(wav, samples, audio.sample_rate, subtype="PCM_16")
            dur = len(samples) / audio.sample_rate

            page = WORK / f"{key}.html"
            page.write_text(PAGE.format(
                kicker=html.escape(scene["kicker"]), headline=html.escape(scene["headline"]),
                sub=html.escape(scene["sub"]), hsize=hsize,
                cap=f'<div class="cap">{html.escape(sentence)}</div>'), encoding="utf-8")
            png = WORK / f"{key}.png"
            jobs.append({"html": str(page), "png": str(png), "width": 1920, "height": 1080})

            clips.append((png, wav, dur))
            srt.append(f"{len(srt) + 1}\n{fmt_ts(t)} --> {fmt_ts(t + dur - GAP)}\n{sentence}\n")
            t += dur
            print(f"{key}  {dur:5.1f}s  {sentence[:30]}")

    thumb = WORK / "thumbnail.html"
    thumb.write_text(THUMB, encoding="utf-8")
    jobs.append({"html": str(thumb), "png": str(OUT / "thumbnail.png"), "width": 1280, "height": 720})
    manifest = WORK / "render.json"
    manifest.write_text(json.dumps(jobs), encoding="utf-8")
    subprocess.run(["node", str(HERE / "render.js"), str(manifest)], check=True,
                   env={**os.environ, "NODE_PATH": "/opt/node-tools/node_modules"})

    (OUT / "video01.srt").write_text("\n".join(srt), encoding="utf-8")

    # 문장별 클립(정지 화면 + 음성)을 만든 뒤 하나로 이어 붙인다.
    parts = []
    for n, (png, wav, dur) in enumerate(clips):
        part = WORK / f"part_{n:03}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", str(png),
                        "-i", str(wav), "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast",
                        "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                        "-ar", "44100", "-ac", "2", str(part)], check=True)
        parts.append(part)
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{x}'\n" for x in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(OUT / "video01.mp4")], check=True)
    print(f"done: {OUT / 'video01.mp4'}  total {t / 60:.1f} min, {len(clips)} sentences")


if __name__ == "__main__":
    main()
