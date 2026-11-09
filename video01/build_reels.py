"""릴스/쇼츠용 세로 영상(1080x1920) 빌드. 디자인과 TTS는 build.py와 같은 것을 쓴다.

사용법: python3 build_reels.py --model-dir <vits-mimic3-ko_KO-kss_low 경로> [--bgm 배경음악.mp3]
결과: output/reels01.mp4, output/reels01_cover.png
"""
import argparse
import html
import json
import os
import subprocess
from pathlib import Path

from build import FONTS, GOLD, ff, speakable, split_sentences

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
WORK = OUT / "work_reels"
W, H, FPS = 1080, 1920, 30
GAP, LEAD, TAIL, FADE = 0.3, 0.25, 0.35, 0.25

# 인스타그램 릴스 UI 안전 영역: 위 약 250px, 아래 약 420px, 오른쪽 약 140px은 가려질 수 있다.
BG = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}
body{{width:1080px;height:1920px;overflow:hidden;position:relative;font-family:'Noto Sans KR';
background:radial-gradient(ellipse 90% 55% at 50% 38%,#2c1a10 0%,#140c08 50%,#060403 100%)}}
.glow{{position:absolute;left:50%;top:36%;width:1100px;height:1100px;transform:translate(-50%,-50%);
background:radial-gradient(circle,rgba(201,161,74,.2) 0%,rgba(201,161,74,0) 60%)}}
.mark{{position:absolute;left:50%;top:37%;transform:translate(-50%,-50%);font-family:'Noto Serif KR';font-weight:900;
font-size:{msize}px;line-height:1;color:transparent;-webkit-text-stroke:2px rgba(201,161,74,.18);white-space:nowrap}}
.wrap{{position:absolute;left:70px;right:70px;top:330px;height:760px;display:flex;flex-direction:column;
align-items:center;justify-content:center;text-align:center}}
.kicker{{display:flex;align-items:center;gap:22px;font-size:44px;font-weight:500;letter-spacing:8px;color:#d8b25e}}
.kicker:before,.kicker:after{{content:"";width:80px;height:1px;background:linear-gradient(90deg,transparent,#d8b25e)}}
.kicker:after{{transform:scaleX(-1)}}
.headline{{margin-top:30px;font-family:'Noto Serif KR';font-weight:900;font-size:{hsize}px;line-height:1.15;
white-space:pre-line;background:{gold};-webkit-background-clip:text;background-clip:text;color:transparent;
filter:drop-shadow(0 8px 26px rgba(0,0,0,.7))}}
.rule{{margin:34px auto 0;display:flex;align-items:center;gap:16px}}
.rule i{{display:block;width:140px;height:1px;background:linear-gradient(90deg,transparent,#c9a14a,transparent)}}
.rule b{{display:block;width:12px;height:12px;transform:rotate(45deg);border:1.5px solid #d8b25e}}
.sub{{margin-top:28px;font-family:'Noto Serif KR';font-weight:600;font-size:44px;color:#eadcbc;word-break:keep-all}}
</style></head><body><div class="glow"></div><div class="mark">{mark}</div>
<div class="wrap"><div class="kicker">{kicker}</div><div class="headline">{headline}</div>
<div class="rule"><i></i><b></b><i></i></div><div class="sub">{sub}</div></div></body></html>"""

FRAME = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}html,body{{background:transparent}}
body{{width:1080px;height:1920px;overflow:hidden;position:relative}}
.vig{{position:absolute;inset:0;background:radial-gradient(ellipse 90% 70% at 50% 45%,rgba(0,0,0,0) 55%,rgba(0,0,0,.6) 100%)}}
.f1{{position:absolute;inset:34px;border:1.5px solid rgba(201,161,74,.65)}}
.f2{{position:absolute;inset:46px;border:1px solid rgba(201,161,74,.3)}}
.c{{position:absolute;width:56px;height:56px;border-color:#d8b25e;border-style:solid}}
.c.tl{{left:24px;top:24px;border-width:3px 0 0 3px}} .c.tr{{right:24px;top:24px;border-width:3px 3px 0 0}}
.c.bl{{left:24px;bottom:24px;border-width:0 0 3px 3px}} .c.br{{right:24px;bottom:24px;border-width:0 3px 3px 0}}
.brand{{position:absolute;left:0;right:0;top:250px;text-align:center;font-family:'Noto Serif KR';font-size:28px;
letter-spacing:12px;color:rgba(216,178,94,.7)}}
</style></head><body><div class="vig"></div><div class="f1"></div><div class="f2"></div>
<div class="c tl"></div><div class="c tr"></div><div class="c bl"></div><div class="c br"></div>
<div class="brand">二〇二七 · 丁未年 運勢</div></body></html>"""

CAP = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}html,body{{background:transparent}}
body{{width:1080px;height:1920px;overflow:hidden;position:relative}}
.box{{position:absolute;left:80px;right:150px;top:1150px;height:300px;display:flex;flex-direction:column;
align-items:center;justify-content:center}}
.line{{width:360px;height:1px;margin-bottom:28px;background:linear-gradient(90deg,transparent,rgba(216,178,94,.85),transparent)}}
.cap{{text-align:center;font-family:'Noto Serif KR';font-weight:700;font-size:54px;line-height:1.42;color:#fbf3e0;
word-break:keep-all;text-shadow:0 2px 14px rgba(0,0,0,.95)}}
</style></head><body><div class="box"><div class="line"></div><div class="cap">{text}</div></div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True, type=Path)
    ap.add_argument("--bgm", type=Path)
    args = ap.parse_args()

    import numpy as np
    import sherpa_onnx
    import soundfile as sf

    m = args.model_dir
    tts = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(m / "ko_KO-kss_low.onnx"), tokens=str(m / "tokens.txt"),
                                                   data_dir=str(m / "espeak-ng-data")), num_threads=4)))
    data = json.loads((HERE / "reels.json").read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)

    jobs, scenes = [], []
    for scene in data["scenes"]:
        sid = scene["id"]
        lines = scene["headline"].count("\n") + 1
        longest = max(len(x) for x in scene["headline"].split("\n"))
        hsize = 210 if lines == 1 and longest <= 4 else 150 if lines == 1 else 140
        (WORK / f"{sid}_bg.html").write_text(BG.format(
            fonts=FONTS, gold=GOLD, kicker=html.escape(scene["kicker"]), headline=html.escape(scene["headline"]),
            sub=html.escape(scene["sub"]), mark=html.escape(scene["mark"]), hsize=hsize, msize=900), encoding="utf-8")
        bg = WORK / f"{sid}_bg.png"
        jobs.append({"html": str(WORK / f"{sid}_bg.html"), "png": str(bg), "width": W, "height": H, "scale": 2})

        sr, chunks, cues, t = 22050, [], [], LEAD
        chunks.append(np.zeros(int(LEAD * sr), dtype=np.float32))
        for s in split_sentences(scene["narration"]):
            a = tts.generate(speakable(s), sid=0, speed=1.0)
            sr = a.sample_rate
            x = np.asarray(a.samples, dtype=np.float32)
            cues.append((s, t, t + len(x) / sr))
            chunks += [x, np.zeros(int(GAP * sr), dtype=np.float32)]
            t += len(x) / sr + GAP
        chunks.append(np.zeros(int(TAIL * sr), dtype=np.float32))
        audio = np.concatenate(chunks)
        wav = WORK / f"{sid}.wav"
        sf.write(wav, audio, sr, subtype="PCM_16")
        dur = len(audio) / sr

        caps = []
        for i, (s, a, b) in enumerate(cues):
            (WORK / f"{sid}_cap{i}.html").write_text(CAP.format(fonts=FONTS, text=html.escape(s)), encoding="utf-8")
            png = WORK / f"{sid}_cap{i}.png"
            jobs.append({"html": str(WORK / f"{sid}_cap{i}.html"), "png": str(png), "width": W, "height": H,
                         "transparent": True})
            caps.append((png, a, b))
        scenes.append((sid, bg, wav, dur, caps))
        print(f"{sid}: {dur:4.1f}s")

    frame_png = WORK / "frame.png"
    (WORK / "frame.html").write_text(FRAME.format(fonts=FONTS), encoding="utf-8")
    jobs.append({"html": str(WORK / "frame.html"), "png": str(frame_png), "width": W, "height": H, "transparent": True})
    (WORK / "render.json").write_text(json.dumps(jobs), encoding="utf-8")
    subprocess.run(["node", str(HERE / "render.js"), str(WORK / "render.json")], check=True,
                   env={**os.environ, "NODE_PATH": "/opt/node-tools/node_modules"})

    parts = []
    for n, (sid, bg, wav, dur, caps) in enumerate(scenes):
        frames = int(dur * FPS) + 1
        z = f"1+0.08*on/{frames}" if n % 2 == 0 else f"1.08-0.08*on/{frames}"
        inputs = ["-i", bg]
        for png, _, _ in caps:
            inputs += ["-loop", "1", "-framerate", FPS, "-i", png]
        fidx = len(caps) + 1
        inputs += ["-loop", "1", "-framerate", FPS, "-i", frame_png, "-i", wav]
        chain = (f"[0:v]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
                 f"setsar=1,format=yuva420p[v0]")
        last = "v0"
        for i, (_, a, b) in enumerate(caps, start=1):
            fo = b + GAP * 0.6
            chain += (f";[{i}:v]format=rgba,fade=t=in:st={a:.2f}:d=0.15:alpha=1,fade=t=out:st={fo - 0.15:.2f}:d=0.15:alpha=1[c{i}]"
                      f";[{last}][c{i}]overlay=0:0:enable='between(t,{a:.2f},{fo:.2f})'[v{i}]")
            last = f"v{i}"
        chain += f";[{last}][{fidx}:v]overlay=0:0[vf]"
        fade_in = "" if n == 0 else f"fade=t=in:st=0:d={FADE},"  # 첫 프레임은 바로 보여야 한다
        chain += f";[vf]{fade_in}fade=t=out:st={dur - FADE:.2f}:d={FADE},format=yuv420p[vout]"
        chain += f";[{fidx + 1}:a]aresample=44100[aout]"
        part = WORK / f"scene_{n:02}.mp4"
        ff(*inputs, "-filter_complex", chain, "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.3f}",
           "-c:v", "libx264", "-preset", "faster", "-crf", "19", "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ac", "2", part)
        parts.append(part)
        print(f"encoded {part.name}")

    (WORK / "list.txt").write_text("".join(f"file '{x}'\n" for x in parts))
    joined = WORK / "joined.mp4"
    ff("-f", "concat", "-safe", "0", "-i", WORK / "list.txt", "-c", "copy", joined)
    final = OUT / "reels01.mp4"
    if args.bgm:
        ff("-i", joined, "-stream_loop", "-1", "-i", args.bgm, "-filter_complex",
           "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final)
    else:
        ff("-i", joined, "-c", "copy", "-movflags", "+faststart", final)
    ff("-ss", "0.5", "-i", final, "-frames:v", "1", OUT / "reels01_cover.png")
    print(f"done: {final}  {sum(s[3] for s in scenes):.1f}s")


if __name__ == "__main__":
    main()
