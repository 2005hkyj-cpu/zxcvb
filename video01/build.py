"""2027 정미년 띠별 운세 영상 빌드 스크립트 (프리미엄 블랙 & 골드 버전).

1) scenes.json 내레이션을 문장 단위로 오프라인 TTS(sherpa-onnx) 합성 (또는 --voice-dir 의 녹음 파일 사용)
2) 장면 배경(4K)과 문장별 자막(투명 PNG)을 Playwright(Node)로 렌더링
3) ffmpeg: 배경 천천히 확대 + 자막 오버레이 + 장면 페이드 → output/video01.mp4 (+ .srt, 썸네일)

사용법:
  python3 build.py --model-dir <vits-mimic3-ko_KO-kss_low 경로> [--bgm 배경음악.mp3]
  python3 build.py --voice-dir <장면id.wav 녹음 폴더> [--bgm ...]   # 직접 녹음한 목소리 사용
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
GAP = 0.5      # 문장 사이 쉬는 시간(초)
LEAD = 0.6     # 장면 시작 전 여백(초)
TAIL = 0.8     # 장면 끝 여백(초)
FADE = 0.5     # 장면 페이드 인/아웃(초)
FPS = 30

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
    return [p for p in re.split(r"(?<=[.?!])\s+", text.strip()) if p]


FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700;900'
         '&family=Noto+Sans+KR:wght@300;500;700&display=block" rel="stylesheet">')

GOLD = "linear-gradient(180deg,#fff4cf 0%,#f0d58e 28%,#c9a14a 55%,#a77b2c 78%,#e9c97a 100%)"

BG = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}
body{{width:1920px;height:1080px;overflow:hidden;position:relative;font-family:'Noto Sans KR';
background:radial-gradient(ellipse 70% 60% at 50% 42%,#2a1810 0%,#140c08 45%,#070504 100%);color:#f5ead2}}
.grain{{position:absolute;inset:0;opacity:.07;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}}
.glow{{position:absolute;left:50%;top:40%;width:1300px;height:1300px;transform:translate(-50%,-50%);
background:radial-gradient(circle,rgba(201,161,74,.16) 0%,rgba(201,161,74,0) 60%)}}
.mark{{position:absolute;left:50%;top:43%;transform:translate(-50%,-50%);font-family:'Noto Serif KR';font-weight:900;
font-size:{msize}px;line-height:1;color:transparent;-webkit-text-stroke:2px rgba(201,161,74,.16);white-space:nowrap;letter-spacing:-20px}}
.f1{{position:absolute;inset:44px;border:1.5px solid rgba(201,161,74,.7)}}
.f2{{position:absolute;inset:56px;border:1px solid rgba(201,161,74,.32)}}
.c{{position:absolute;width:64px;height:64px;border-color:#d8b25e;border-style:solid}}
.c.tl{{left:34px;top:34px;border-width:3px 0 0 3px}} .c.tr{{right:34px;top:34px;border-width:3px 3px 0 0}}
.c.bl{{left:34px;bottom:34px;border-width:0 0 3px 3px}} .c.br{{right:34px;bottom:34px;border-width:0 3px 3px 0}}
.wrap{{position:absolute;left:160px;right:160px;top:118px;height:640px;display:flex;flex-direction:column;
align-items:center;justify-content:center;text-align:center}}
.kicker{{display:flex;align-items:center;gap:28px;font-size:34px;font-weight:500;letter-spacing:10px;color:#d8b25e}}
.kicker:before,.kicker:after{{content:"";width:110px;height:1px;background:linear-gradient(90deg,transparent,#d8b25e)}}
.kicker:after{{transform:scaleX(-1)}}
.headline{{margin-top:34px;font-family:'Noto Serif KR';font-weight:900;font-size:{hsize}px;line-height:1.18;
white-space:pre-line;background:{gold};-webkit-background-clip:text;background-clip:text;color:transparent;
filter:drop-shadow(0 8px 26px rgba(0,0,0,.7))}}
.rule{{margin:38px auto 0;display:flex;align-items:center;gap:18px}}
.rule i{{display:block;width:180px;height:1px;background:linear-gradient(90deg,transparent,#c9a14a,transparent)}}
.rule b{{display:block;width:12px;height:12px;transform:rotate(45deg);border:1.5px solid #d8b25e}}
.sub{{margin-top:30px;font-family:'Noto Serif KR';font-weight:600;font-size:44px;letter-spacing:2px;color:#eadcbc}}
.brand{{position:absolute;left:0;right:0;top:66px;text-align:center;font-family:'Noto Serif KR';font-size:22px;
letter-spacing:12px;color:rgba(216,178,94,.55)}}
</style></head><body><div class="grain"></div><div class="glow"></div><div class="mark">{mark}</div>
<div class="wrap"><div class="kicker">{kicker}</div><div class="headline">{headline}</div>
<div class="rule"><i></i><b></b><i></i></div><div class="sub">{sub}</div></div></body></html>"""

CAP = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}html,body{{background:transparent}}
body{{width:1920px;height:1080px;overflow:hidden;position:relative}}
.shade{{position:absolute;left:0;right:0;bottom:0;height:330px;
background:linear-gradient(180deg,rgba(5,3,2,0) 0%,rgba(5,3,2,.78) 55%,rgba(5,3,2,.9) 100%)}}
.line{{position:absolute;left:50%;bottom:226px;width:520px;height:1px;transform:translateX(-50%);
background:linear-gradient(90deg,transparent,rgba(216,178,94,.8),transparent)}}
.cap{{position:absolute;left:200px;right:200px;bottom:84px;height:126px;display:flex;align-items:center;justify-content:center;
text-align:center;font-family:'Noto Serif KR';font-weight:700;font-size:46px;line-height:1.42;color:#fbf3e0;
word-break:keep-all;text-shadow:0 2px 12px rgba(0,0,0,.9)}}
</style></head><body><div class="shade"></div><div class="line"></div><div class="cap">{text}</div></body></html>"""

FRAME = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}html,body{{background:transparent}}
body{{width:1920px;height:1080px;overflow:hidden;position:relative}}
.vig{{position:absolute;inset:0;background:radial-gradient(ellipse 85% 80% at 50% 45%,rgba(0,0,0,0) 60%,rgba(0,0,0,.55) 100%)}}
.f1{{position:absolute;inset:44px;border:1.5px solid rgba(201,161,74,.7)}}
.f2{{position:absolute;inset:56px;border:1px solid rgba(201,161,74,.32)}}
.c{{position:absolute;width:64px;height:64px;border-color:#d8b25e;border-style:solid}}
.c.tl{{left:34px;top:34px;border-width:3px 0 0 3px}} .c.tr{{right:34px;top:34px;border-width:3px 3px 0 0}}
.c.bl{{left:34px;bottom:34px;border-width:0 0 3px 3px}} .c.br{{right:34px;bottom:34px;border-width:0 3px 3px 0}}
.brand{{position:absolute;left:0;right:0;top:66px;text-align:center;font-family:'Noto Serif KR';font-size:22px;
letter-spacing:12px;color:rgba(216,178,94,.6)}}
</style></head><body><div class="vig"></div><div class="f1"></div><div class="f2"></div>
<div class="c tl"></div><div class="c tr"></div><div class="c bl"></div><div class="c br"></div>
<div class="brand">二〇二七 · 丁未年 運勢</div></body></html>"""

THUMB = """<!doctype html><html><head><meta charset="utf-8">{fonts}<style>
*{{margin:0;box-sizing:border-box}}
body{{width:1280px;height:720px;overflow:hidden;position:relative;font-family:'Noto Sans KR';
background:radial-gradient(ellipse 80% 90% at 72% 50%,#3a2414 0%,#140c08 50%,#050302 100%)}}
.f{{position:absolute;inset:22px;border:2px solid rgba(216,178,94,.75)}}
.f2{{position:absolute;inset:30px;border:1px solid rgba(216,178,94,.35)}}
.m{{position:absolute;right:70px;top:50%;transform:translateY(-50%);width:400px;height:400px;border-radius:50%;
border:3px solid #d8b25e;box-shadow:0 0 0 12px rgba(216,178,94,.12),0 0 90px rgba(216,178,94,.35);
display:flex;align-items:center;justify-content:center;background:radial-gradient(circle,#2c1a0e,#0d0805)}}
.m span{{font-family:'Noto Serif KR';font-weight:900;font-size:260px;line-height:1;background:{gold};
-webkit-background-clip:text;background-clip:text;color:transparent}}
.y{{position:absolute;left:70px;top:70px;font-family:'Noto Serif KR';font-size:44px;font-weight:700;letter-spacing:4px;color:#d8b25e}}
.t{{position:absolute;left:62px;top:150px;font-family:'Noto Serif KR';font-weight:900;font-size:118px;line-height:1.12;
background:{gold};-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 6px 18px rgba(0,0,0,.8))}}
.t em{{font-style:normal;color:#fff;-webkit-text-fill-color:#fbf3e0}}
.s{{position:absolute;left:70px;bottom:70px;font-size:46px;font-weight:700;color:#140c08;
background:{gold};padding:8px 28px;letter-spacing:1px}}
</style></head><body><div class="f"></div><div class="f2"></div>
<div class="y">2027 丁未年 · 붉은 양의 해</div>
<div class="t"><em>내년 대운</em><br>들어오는 띠</div>
<div class="m"><span>未</span></div>
<div class="s">TOP 3 공개 · 조심할 띠까지</div></body></html>"""


def fmt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True)


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, help="오프라인 TTS 모델 폴더")
    ap.add_argument("--voice-dir", type=Path, help="직접 녹음한 장면별 음성 폴더 (01_hook.wav ...)")
    ap.add_argument("--bgm", type=Path, help="배경음악 파일 (선택)")
    args = ap.parse_args()
    if not (args.model_dir or args.voice_dir):
        ap.error("--model-dir 또는 --voice-dir 중 하나가 필요합니다")

    import numpy as np
    import soundfile as sf

    data = json.loads((HERE / "scenes.json").read_text(encoding="utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)
    tts = None
    if args.model_dir:
        import sherpa_onnx
        m = args.model_dir
        tts = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(m / "ko_KO-kss_low.onnx"), tokens=str(m / "tokens.txt"),
                                                       data_dir=str(m / "espeak-ng-data")), num_threads=4)))

    jobs, scenes, srt, t_global = [], [], [], 0.0
    for scene in data["scenes"]:
        sid = scene["id"]
        lines = scene["headline"].count("\n") + 1
        bg = WORK / f"{sid}_bg.png"
        (WORK / f"{sid}_bg.html").write_text(BG.format(
            fonts=FONTS, gold=GOLD, kicker=html.escape(scene["kicker"]), headline=html.escape(scene["headline"]),
            sub=html.escape(scene["sub"]), mark=html.escape(scene["mark"]),
            hsize=150 if lines == 1 else 118, msize=900 if len(scene["mark"]) == 1 else 560), encoding="utf-8")
        jobs.append({"html": str(WORK / f"{sid}_bg.html"), "png": str(bg), "width": 1920, "height": 1080, "scale": 2})

        sentences = split_sentences(scene["narration"])
        sr = 22050
        chunks = [np.zeros(int(LEAD * sr), dtype=np.float32)]
        cues, t = [], LEAD
        if args.voice_dir:  # 녹음 파일은 장면 단위: 문장 길이는 글자 수 비율로 나눈다
            rec, sr = sf.read(args.voice_dir / f"{sid}.wav", dtype="float32", always_2d=False)
            rec = rec.mean(axis=1) if rec.ndim > 1 else rec
            chunks = [np.zeros(int(LEAD * sr), dtype=np.float32), rec]
            total = len(rec) / sr
            weights = [len(s) for s in sentences]
            for s, w in zip(sentences, weights):
                d = total * w / sum(weights)
                cues.append((s, t, t + d))
                t += d
        else:
            for s in sentences:
                a = tts.generate(speakable(s), sid=0, speed=0.92)
                sr = a.sample_rate
                x = np.asarray(a.samples, dtype=np.float32)
                cues.append((s, t, t + len(x) / sr))
                chunks += [x, np.zeros(int(GAP * sr), dtype=np.float32)]
                t += len(x) / sr + GAP
        chunks.append(np.zeros(int(TAIL * sr), dtype=np.float32))
        wav = WORK / f"{sid}.wav"
        sf.write(wav, np.concatenate(chunks), sr, subtype="PCM_16")
        scene_dur = len(np.concatenate(chunks)) / sr

        caps = []
        for i, (s, a, b) in enumerate(cues):
            png = WORK / f"{sid}_cap{i:02}.png"
            (WORK / f"{sid}_cap{i:02}.html").write_text(CAP.format(fonts=FONTS, text=html.escape(s)), encoding="utf-8")
            jobs.append({"html": str(WORK / f"{sid}_cap{i:02}.html"), "png": str(png), "width": 1920, "height": 1080,
                         "transparent": True})
            caps.append((png, a, b))
            srt.append(f"{len(srt) + 1}\n{fmt_ts(t_global + a)} --> {fmt_ts(t_global + b)}\n{s}\n")
        scenes.append((sid, bg, wav, scene_dur, caps, t_global))
        print(f"{sid}: {scene_dur:5.1f}s, {len(caps)} captions, starts {t_global:6.1f}s")
        t_global += scene_dur

    frame_png = WORK / "frame.png"
    (WORK / "frame.html").write_text(FRAME.format(fonts=FONTS), encoding="utf-8")
    jobs.append({"html": str(WORK / "frame.html"), "png": str(frame_png), "width": 1920, "height": 1080, "transparent": True})
    (WORK / "thumb.html").write_text(THUMB.format(fonts=FONTS, gold=GOLD), encoding="utf-8")
    jobs.append({"html": str(WORK / "thumb.html"), "png": str(OUT / "thumbnail.png"), "width": 1280, "height": 720})
    manifest = WORK / "render.json"
    manifest.write_text(json.dumps(jobs), encoding="utf-8")
    subprocess.run(["node", str(HERE / "render.js"), str(manifest)], check=True,
                   env={**os.environ, "NODE_PATH": "/opt/node-tools/node_modules"})
    (OUT / "video01.srt").write_text("\n".join(srt), encoding="utf-8")

    parts = []
    for n, (sid, bg, wav, dur, caps, _) in enumerate(scenes):
        frames = int(dur * FPS) + 1
        zoom_in = n % 2 == 0  # 장면마다 확대/축소를 번갈아 적용
        z = f"1+0.06*on/{frames}" if zoom_in else f"1.06-0.06*on/{frames}"
        inputs = ["-i", bg]  # 한 장의 이미지에서 zoompan이 frames개의 프레임을 만든다
        for png, _, _ in caps:
            inputs += ["-loop", "1", "-framerate", FPS, "-i", png]
        inputs += ["-loop", "1", "-framerate", FPS, "-i", frame_png, "-i", wav]
        fidx = len(caps) + 1
        chain = (f"[0:v]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={FPS},"
                 f"setsar=1,format=yuva420p[v0]")
        last = "v0"
        for i, (_, a, b) in enumerate(caps, start=1):
            fi, fo = a, max(a, b + GAP * 0.6)
            chain += (f";[{i}:v]format=rgba,fade=t=in:st={fi:.2f}:d=0.25:alpha=1,"
                      f"fade=t=out:st={fo - 0.25:.2f}:d=0.25:alpha=1[c{i}]"
                      f";[{last}][c{i}]overlay=0:0:shortest=0:enable='between(t,{fi:.2f},{fo:.2f})'[v{i}]")
            last = f"v{i}"
        chain += f";[{last}][{fidx}:v]overlay=0:0[vf]"
        chain += f";[vf]fade=t=in:st=0:d={FADE},fade=t=out:st={dur - FADE:.2f}:d={FADE},format=yuv420p[vout]"
        chain += f";[{fidx + 1}:a]afade=t=in:d=0.2,afade=t=out:st={dur - 0.3:.2f}:d=0.3,aresample=44100[aout]"
        part = WORK / f"scene_{n:02}.mp4"
        ff(*inputs, "-filter_complex", chain, "-map", "[vout]", "-map", "[aout]", "-t", f"{dur:.3f}",
           "-c:v", "libx264", "-preset", "faster", "-crf", "19", "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ac", "2", part)
        parts.append(part)
        print(f"encoded {part.name}")

    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{x}'\n" for x in parts))
    joined = WORK / "joined.mp4"
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined)
    final = OUT / "video01.mp4"
    if args.bgm:
        total = duration(joined)
        ff("-i", joined, "-stream_loop", "-1", "-i", args.bgm, "-filter_complex",
           f"[1:a]volume=0.12,afade=t=in:d=2,afade=t=out:st={total - 3:.2f}:d=3[m];"
           f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final)
    else:
        ff("-i", joined, "-c", "copy", "-movflags", "+faststart", final)
    print(f"done: {final}  {t_global / 60:.1f} min")


if __name__ == "__main__":
    main()
