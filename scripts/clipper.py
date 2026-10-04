# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["opencv-python-headless"]
# ///
import argparse
import html
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FONTS = SKILL_DIR / "assets" / "fonts"
REEL_TEMPLATE = SKILL_DIR / "assets" / "reel" / "index.html"
HYPERFRAMES = "hyperframes@0.8.96"
JOBS = int(os.environ.get("MUSUBI_CLIPS_JOBS", 3))
WORK = Path(os.environ.get("MUSUBI_CLIPS_DIR", Path.home() / "MusubiClips"))
FACE_MODEL = Path.home() / ".cache" / "musubi-clips" / "face_detection_yunet_2023mar.onnx"
FACE_MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YTDLP = ["yt-dlp"] + (["--cookies-from-browser", os.environ["MUSUBI_CLIPS_COOKIES"]] if os.environ.get("MUSUBI_CLIPS_COOKIES") else [])
OUT_W, OUT_H = 1080, 1920
HOOK_SECONDS = 3.0
MIN_CLIP, MAX_CLIP = 12.0, 90.0
MIN_FACE = 0.05


def run(cmd, cwd=None):
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    except subprocess.CalledProcessError as error:
        print(f"{cmd[0]} failed: {(error.stderr or '')[-800:]}", file=sys.stderr)
        raise


def log(msg):
    print(msg, file=sys.stderr, flush=True)


VIDEO_FORMAT = "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080][ext=mp4]/bv*[height<=1080]"


def fetch(source):
    if Path(source).is_file():
        path = Path(source).resolve()
        workdir = WORK / re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir, path, {"title": path.stem, "url": "", "path": str(path)}
    video_id = run([*YTDLP, "--print", "id", "--skip-download", source]).stdout.strip().splitlines()[-1]
    workdir = WORK / video_id
    workdir.mkdir(parents=True, exist_ok=True)
    if not source_audio(workdir):
        log(f"downloading the audio of {source}")
        run([*YTDLP, "-f", "ba[ext=m4a]/ba", "--write-info-json", "--no-playlist",
             "-o", str(workdir / "source-audio.%(ext)s"), source])
    info = json.loads((workdir / "source-audio.info.json").read_text(encoding="utf-8"))
    return workdir, source_audio(workdir), {"title": info.get("title", video_id), "url": info.get("webpage_url", source)}


def source_audio(workdir):
    full = workdir / "source.mp4"
    if full.exists():
        return full
    found = [f for f in workdir.glob("source-audio.*") if not f.name.endswith(".json")]
    return found[0] if found else None



def stream_url(url):
    for command in (["yt-dlp"], YTDLP):
        try:
            return run([*command, "-g", "-f", VIDEO_FORMAT, "--no-playlist", url]).stdout.strip().splitlines()[0]
        except (subprocess.CalledProcessError, IndexError):
            pass
    return "unavailable:"

def video_section(workdir, meta, clip, stream):
    full = workdir / "source.mp4"
    if full.exists():
        return full, 0.0
    if meta.get("path"):
        return Path(meta["path"]), 0.0
    pieces = pieces_for(clip)
    start = max(0.0, min(a for a, _ in pieces) - 1)
    end = max(b for _, b in pieces) + 1
    out = workdir / "sections" / f"{start:.2f}-{end:.2f}.mp4"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        audio = ["-ss", f"{start}", "-t", f"{end - start}", "-i", str(source_audio(workdir)),
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                 "-c:a", "aac", "-b:a", "192k", str(out)]
        try:
            run(["ffmpeg", "-y", "-ss", f"{start}", "-t", f"{end - start}", "-i", stream, *audio])
        except subprocess.CalledProcessError:
            out.unlink(missing_ok=True)
            if not meta.get("url"):
                raise
            piece = out.with_suffix(".video.mp4")
            for attempt in range(3):
                try:
                    piece.unlink(missing_ok=True)
                    run([*YTDLP, "-f", VIDEO_FORMAT, "--no-playlist", "--download-sections", f"*{start}-{end}",
                         "--force-keyframes-at-cuts", "-o", str(piece), meta["url"]])
                    run(["ffmpeg", "-y", "-t", f"{end - start}", "-i", str(piece), *audio])
                    break
                except subprocess.CalledProcessError:
                    out.unlink(missing_ok=True)
                    if attempt == 2:
                        raise
                    time.sleep(20)
            piece.unlink(missing_ok=True)
    return out, start


def shifted(clip, words, offset):
    if not offset:
        return clip, words
    moved = {**clip, "start": clip["start"] - offset, "end": clip["end"] - offset,
             "cold_open": [t - offset for t in clip["cold_open"]] if clip["cold_open"] else None}
    return moved, [{**w, "start": w["start"] - offset, "end": w["end"] - offset} for w in words]


def youtube_words(caption_file):
    events = json.loads(caption_file.read_text(encoding="utf-8"))["events"]
    tokens = sorted(((e["tStartMs"] + seg.get("tOffsetMs", 0)) / 1000, re.sub(r">>|\[[^\]]*\]", "", seg.get("utf8", "")).strip())
                    for e in events for seg in e.get("segs", []))
    starts, tagged = [], False
    for start, text in tokens:
        tagged = tagged or text.startswith("[")
        if tagged or not text:
            tagged = tagged and "]" not in text
        elif starts and not re.search(r"\w", text):
            starts[-1] = (starts[-1][0], starts[-1][1] + text)
        else:
            starts.append((start, text))
    return [{"word": text, "start": start, "end": min(start + 0.8, following[0] if following else start + 0.5)}
            for (start, text), following in zip(starts, starts[1:] + [None])]


def group_segments(words, gap=0.8, size=14):
    segments, current = [], []
    for word in words:
        if current and (len(current) == size or word["start"] - current[-1]["end"] > gap):
            segments.append(current)
            current = []
        current.append(word)
    if current:
        segments.append(current)
    return [{"start": g[0]["start"], "end": g[-1]["end"], "text": " ".join(w["word"] for w in g), "words": g} for g in segments]


def caption_file(workdir):
    found = sorted(workdir.glob("captions.en*-orig.json3")) or sorted(workdir.glob("captions.en.json3"))
    return found[0] if found else None


def fetch_translated(workdir):
    info = json.loads((workdir / "source-audio.info.json").read_text(encoding="utf-8"))
    for track in info.get("automatic_captions", {}).get("en", []):
        if track.get("ext") == "json3":
            try:
                request = urllib.request.Request(track["url"], headers={"User-Agent": "Mozilla/5.0"})
                (workdir / "captions.en.json3").write_bytes(urllib.request.urlopen(request, timeout=30).read())
            except OSError as error:
                log(f"youtube refused the translated captions: {error}")
            return


def youtube_transcript(workdir, url):
    if not caption_file(workdir):
        subprocess.run([*YTDLP, "--skip-download", "--write-auto-subs", "--sub-langs", "en.*-orig,en", "--sub-format", "json3",
                        "-o", str(workdir / "captions.%(ext)s"), url], capture_output=True)
    if not caption_file(workdir):
        fetch_translated(workdir)
    found = caption_file(workdir)
    words = youtube_words(found) if found else []
    return {"language": "en", "source": "youtube", "segments": group_segments(words)} if words else None


def transcribe(workdir, video, meta):
    cached = workdir / "transcript.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    transcript = youtube_transcript(workdir, meta["url"]) if meta["url"] else None
    if not transcript:
        sys.exit("YouTube has no English auto captions for this video, so it cannot be clipped.")
    cached.write_text(encoding="utf-8", data=json.dumps(transcript, ensure_ascii=False))
    return transcript


def all_words(transcript):
    return [w for s in transcript["segments"] for w in s["words"] if w["word"]]


def snap(t, words, edge):
    return min(words, key=lambda w: abs(w[edge] - t))[edge]


def rank_score(clip):
    return clip["hook"] * 2 + clip["standalone"] + clip["payoff"] + clip["emotion"]


def tidy_clips(raw, words, keep):
    clips = []
    for clip in raw:
        start, end = snap(clip["start"], words, "start"), snap(clip["end"], words, "end")
        if not MIN_CLIP <= end - start <= MAX_CLIP:
            continue
        if any(start < c["end"] and c["start"] < end for c in clips):
            continue
        cold = None
        if clip.get("cold_open_start") is not None and clip.get("cold_open_end") is not None:
            cs, ce = snap(clip["cold_open_start"], words, "start"), snap(clip["cold_open_end"], words, "end")
            if start + 1 < cs and ce <= end and 1.5 <= ce - cs <= 8:
                cold = [cs, ce]
        clips.append({**clip, "start": start, "end": end, "cold_open": cold, "score": rank_score(clip)})
    clips.sort(key=lambda c: -c["score"])
    return clips[:keep]


SCORES = ("hook", "standalone", "payoff", "emotion")
TEXTS = ("title", "hook_text", "reason")


def moment_problems(raw):
    problems = []
    for i, clip in enumerate(raw, 1):
        for field in ("start", "end"):
            if not isinstance(clip.get(field), (int, float)):
                problems.append(f"moment {i}: {field} must be a number of seconds")
        for field in TEXTS:
            if not isinstance(clip.get(field), str) or not clip[field].strip():
                problems.append(f"moment {i}: {field} is missing")
        for field in SCORES:
            if clip.get(field) not in (1, 2, 3, 4, 5):
                problems.append(f"moment {i}: {field} must be a whole number from 1 to 5")
        emphasis = clip.get("emphasis", [])
        if not isinstance(emphasis, list) or not all(isinstance(w, str) for w in emphasis):
            problems.append(f"moment {i}: emphasis must be a list of words")
        for field in ("speaker_name", "speaker_role"):
            if clip.get(field) is not None and not isinstance(clip[field], str):
                problems.append(f"moment {i}: {field} must be text")
    return problems


def load_moments(workdir):
    path = workdir / "moments.json"
    if not path.exists():
        sys.exit(f"{path} does not exist. Pick the moments first.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw = raw.get("clips", []) if isinstance(raw, dict) else raw
    problems = moment_problems(raw)
    if problems:
        sys.exit("moments.json needs fixing:\n" + "\n".join(problems))
    return raw


def probe_size(video):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "csv=p=0", str(video)]).stdout.strip()
    width, height = out.split(",")[:2]
    return int(width), int(height)


def shot_cuts(video, start, end):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{start}", "-t", f"{end - start}", "-i", str(video),
                          "-vf", "scale=320:-2,select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return [start + float(t) for t in re.findall(r"pts_time:([\d.]+)", out)]


def face_detector():
    import cv2

    if not FACE_MODEL.exists():
        FACE_MODEL.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FACE_MODEL_URL, FACE_MODEL)
    return cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (320, 320), 0.7)


def face_center(capture, detector, start, end, focus=None):
    import cv2

    centers = []
    for fraction in (0.2, 0.5, 0.8):
        capture.set(cv2.CAP_PROP_POS_MSEC, (start + (end - start) * fraction) * 1000)
        ok, frame = capture.read()
        if not ok:
            continue
        scale = 640 / frame.shape[1]
        small = cv2.resize(frame, (640, round(frame.shape[0] * scale)))
        detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = detector.detect(small)
        faces = [f for f in faces if f[2] >= small.shape[1] * MIN_FACE] if faces is not None else []
        if faces:
            near = (lambda f: -abs((f[0] + f[2] / 2) / small.shape[1] - focus)) if focus else (lambda f: f[2] * f[3])
            x, _, w, h = max(faces, key=near)[:4]
            centers.append((x + w / 2) / scale)
    return statistics.median(centers) if centers else None


def crop_x(center, src_w, crop_w):
    if center is None:
        center = src_w / 2
    return int(max(0, min(src_w - crop_w, center - crop_w / 2)))


def crop_expression(steps):
    expr = str(steps[-1][1])
    for (_, x), (next_start, _) in reversed(list(zip(steps, steps[1:]))):
        expr = f"if(lt(t,{next_start:.3f}),{x},{expr})"
    return expr


def pieces_for(clip):
    if clip["cold_open"]:
        return [tuple(clip["cold_open"]), (clip["start"], clip["end"])]
    return [(clip["start"], clip["end"])]


def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def caption_chunks(words, size=3, gap=0.6):
    chunks, current = [], []
    for word in words:
        if current and (len(current) == size or word["start"] - current[-1]["end"] > gap
                        or current[-1]["word"][-1:] in ".?!,"):
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def clip_timeline(clip, words):
    timeline, offset = [], 0.0
    for a, b in pieces_for(clip):
        timeline += [{"word": w["word"], "start": w["start"] - a + offset, "end": w["end"] - a + offset}
                     for w in words if w["start"] >= a - 0.05 and w["end"] <= b + 0.05]
        offset += b - a
    return timeline


def build_ass(clip, words):
    timeline = clip_timeline(clip, words)
    events = [f"Dialogue: 1,{ass_time(0)},{ass_time(HOOK_SECONDS)},Hook,,0,0,0,,{ass_escape(clip['hook_text'])}"]
    captions = []
    for chunk in caption_chunks(timeline):
        for i, word in enumerate(chunk):
            text = " ".join(("{\\c&H0000E5FF&}" + ass_escape(w["word"]) + "{\\c&HFFFFFF&}") if j == i else ass_escape(w["word"])
                            for j, w in enumerate(chunk))
            captions.append((word["start"], word["end"], re.sub(r" (?=(\{[^}]*\})?[-'’])", "", text)))
    for (start, end, text), following in zip(captions, captions[1:] + [None]):
        if following:
            end = following[0] if following[0] - end < 0.4 else min(end + 0.15, following[0])
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{text}")
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Poppins ExtraBold,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,0,2,80,80,560,1
Style: Hook,Poppins ExtraBold,70,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,20,0,8,90,90,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n"


def cut_graph(video, clip, detector, subtitles=None):
    import cv2

    src_w, src_h = probe_size(video)
    pieces = pieces_for(clip)
    focus = clip.get("focus_x")
    base = clip["start"]
    parts, steps, offset, seen = [], [], 0.0, []
    capture = cv2.VideoCapture(str(video))
    crop_w = min(src_w, round(src_h * 9 / 16 / 2) * 2)
    for i, (a, b) in enumerate(pieces):
        parts.append(f"[0:v]trim=start={a - base:.3f}:end={b - base:.3f},setpts=PTS-STARTPTS[v{i}];"
                     f"[0:a]atrim=start={a - base:.3f}:end={b - base:.3f},asetpts=PTS-STARTPTS[a{i}]")
        bounds = [a] + [t for t in shot_cuts(video, a, b) if a + 0.3 < t < b - 0.3] + [b]
        for s, e in zip(bounds, bounds[1:]):
            center = face_center(capture, detector, s, e, focus)
            seen.append(center is not None)
            steps.append((offset + s - a, crop_x(center, src_w, crop_w)))
        offset += b - a
    capture.release()

    joined = "".join(f"[v{i}][a{i}]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=1[cv][ca]"
    if src_w / src_h > 9 / 16 + 0.01 and sum(seen) < len(seen) / 2:
        frame = (f"split[bg][fg];[bg]scale=-2:{OUT_H},crop={OUT_W}:{OUT_H},boxblur=30:2[blur];"
                 f"[fg]scale={OUT_W}:-2[fit];[blur][fit]overlay=0:(H-h)/2")
    elif src_w / src_h > 9 / 16 + 0.01:
        frame = f"crop={crop_w}:{src_h}:x='{crop_expression(steps)}':y=0,scale={OUT_W}:{OUT_H}"
    else:
        frame = f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2"
    caption = f",subtitles={subtitles}:fontsdir=." if subtitles else ""
    return ";".join(parts + [joined, f"[cv]{frame},setsar=1{caption}[vo]"])


def cut(video, clip, graph, out, cwd):
    run(["ffmpeg", "-y", "-ss", f"{clip['start']}", "-t", f"{clip['end'] - clip['start']}", "-i", str(video),
         "-filter_complex", graph, "-map", "[vo]", "-map", "[ca]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(out)], cwd=cwd)


def reel_data(clip, words, duration):
    timeline = clip_timeline(clip, words)
    groups, index = [], 0
    for chunk in caption_chunks(timeline):
        groups.append([index, index + len(chunk) - 1])
        index += len(chunk)
    name = (clip.get("speaker_name") or "").strip()
    return {
        "duration": duration,
        "cut": round(clip["cold_open"][1] - clip["cold_open"][0], 3) if clip["cold_open"] else None,
        "hook": clip["hook_text"],
        "emphasis": clip.get("emphasis") or [],
        "speaker": {"name": name, "role": (clip.get("speaker_role") or "").strip()} if name else None,
        "words": [{"t": w["word"], "s": round(max(0.0, w["start"]), 3), "e": round(w["end"], 3)} for w in timeline],
        "groups": groups,
    }


def npx():
    return shutil.which("npx")


def node_ok():
    node = shutil.which("node")
    if not node or not npx():
        return False
    version = run([node, "--version"]).stdout.strip().lstrip("v")
    return int(version.split(".")[0]) >= 22


def render_styled(workdir, video, clip, words, name, detector, clip_dir, parallel):
    project = workdir / "reel" / name
    if project.exists():
        shutil.rmtree(project)
    (project / "fonts").mkdir(parents=True)
    for font in FONTS.glob("*.ttf"):
        shutil.copy(font, project / "fonts" / font.name)
    cut(video, clip, cut_graph(video, clip, detector), project / "base.mp4", project)
    duration = round(duration_of(project / "base.mp4") - 0.05, 3)
    data = json.dumps(reel_data(clip, words, duration), ensure_ascii=False)
    html = REEL_TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__DURATION__", f"{duration}").replace("<!--__DATA__-->", f"<script>window.__REEL_DATA__ = {data};</script>")
    (project / "index.html").write_text(encoding="utf-8", data=html)
    command = [npx(), "--yes", HYPERFRAMES, "render", str(project), "-o", str(clip_dir / f"{name}.mp4"),
               "--crf", "23", "--fps", "30", "--quiet"]
    if sys.platform == "win32" or JOBS == 1:
        command += ["--workers", "1"]
    elif parallel:
        command += ["--workers", "2"]
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0 or not (clip_dir / f"{name}.mp4").exists():
        sys.exit(f"hyperframes render failed for {name}:\n{(done.stderr or done.stdout)[-1500:]}")


def render_basic(video, clip, words, name, detector, clip_dir):
    (clip_dir / f"{name}.ass").write_text(encoding="utf-8", data=build_ass(clip, words))
    for font in FONTS.glob("*.ttf"):
        shutil.copy(font, clip_dir / font.name)
    cut(video, clip, cut_graph(video, clip, detector, subtitles=f"{name}.ass"), f"{name}.mp4", clip_dir)
    (clip_dir / f"{name}.ass").unlink()
    for font in clip_dir.glob("*.ttf"):
        font.unlink()


def clip_name(index, clip):
    return f"{index:02d}-{re.sub(r'[^a-z0-9]+', '-', clip['title'].lower()).strip('-')[:40] or 'clip'}"


def render(workdir, meta, clip, words, index, styled, stream, parallel):
    clip_dir = workdir / "clips"
    name = clip_name(index, clip)
    video, offset = video_section(workdir, meta, clip, stream)
    clip, words = shifted(clip, words, offset)
    detector = face_detector()
    if styled:
        render_styled(workdir, video, clip, words, name, detector, clip_dir, parallel)
    else:
        render_basic(video, clip, words, name, detector, clip_dir)
    log(f"done: {name}.mp4")
    return f"{name}.mp4"


def stamp(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


def write_review(workdir, meta, clips):
    cards = []
    for c in clips:
        at = f"{meta['url']}&t={int(c['start'])}s" if "?" in meta["url"] else meta["url"]
        cards.append(f"""<article>
<video src="{html.escape(c['file'])}" controls preload="metadata"></video>
<div><h2>{html.escape(c['title'])}</h2>
<p class="hook">{html.escape(c['hook_text'])}</p>
<p>{html.escape(c['reason'])}</p>
<p class="meta">Score {c['score']} of 25 · hook {c['hook']} · standalone {c['standalone']} · payoff {c['payoff']} · emotion {c['emotion']}</p>
<p class="meta"><a href="{html.escape(at)}">Source {stamp(c['start'])} to {stamp(c['end'])}</a>{' · cold open' if c['cold_open'] else ''}</p></div>
</article>""")
    (workdir / "clips" / "index.html").write_text(encoding="utf-8", data=f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(meta['title'])} clips</title>
<style>body{{font:15px/1.5 system-ui;margin:24px auto;max-width:980px;padding:0 16px;background:#f6f6f4;color:#161616}}
article{{display:flex;gap:20px;background:#fff;border-radius:14px;padding:16px;margin:16px 0}}
video{{width:240px;aspect-ratio:9/16;border-radius:10px;background:#000;flex:none}}
h2{{margin:0 0 6px;font-size:18px}}.hook{{font-weight:700}}.meta{{color:#666;font-size:13px}}
@media(max-width:600px){{article{{flex-direction:column}}video{{width:100%}}}}</style>
<h1>{html.escape(meta['title'])}</h1>{''.join(cards)}""")


def duration_of(video):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)]).stdout)


def prepare(source):
    workdir, video, meta = fetch(source)
    transcript = transcribe(workdir, video, meta)
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in transcript["segments"]]
    (workdir / "transcript.txt").write_text(encoding="utf-8", data="\n".join(lines) + "\n")
    meta = {**meta, "duration": round(duration_of(video)), "transcript_source": transcript["source"],
            "language": transcript["language"]}
    (workdir / "meta.json").write_text(encoding="utf-8", data=json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps({"workdir": str(workdir), **meta, "segments": len(lines),
                      "transcript": str(workdir / "transcript.txt"), "moments_file": str(workdir / "moments.json")},
                     ensure_ascii=False, indent=2))


def render_all(workdir, count, basic=False):
    meta = json.loads((workdir / "meta.json").read_text(encoding="utf-8"))
    transcript = json.loads((workdir / "transcript.json").read_text(encoding="utf-8"))
    words = all_words(transcript)
    clips = tidy_clips(load_moments(workdir), words, count)
    if not clips:
        sys.exit(f"No usable moments: each needs {MIN_CLIP:.0f} to {MAX_CLIP:.0f} seconds and must not overlap another.")
    old = workdir / "clips"
    if old.exists():
        shutil.rmtree(old)
    old.mkdir()
    styled = not basic and node_ok()
    if not basic and not styled:
        log("Node.js 22 or newer not found, so rendering basic captions. Install Node for the animated style.")
    if (workdir / "reel").exists():
        shutil.rmtree(workdir / "reel")
    stream = None
    if not (workdir / "source.mp4").exists() and meta.get("url"):
        log("finding the video stream")
        for attempt in range(3):
            try:
                stream = stream_url(meta["url"])
                break
            except subprocess.CalledProcessError:
                if attempt == 2:
                    raise
                time.sleep(30)
    from concurrent.futures import ThreadPoolExecutor

    parallel = len(clips) > 1
    log(f"rendering {len(clips)} clips {'animated' if styled else 'with basic captions'}, {min(JOBS, len(clips))} at a time")
    with ThreadPoolExecutor(min(JOBS, len(clips))) as pool:
        files = list(pool.map(lambda pair: render(workdir, meta, pair[1], words, pair[0], styled, stream, parallel),
                              enumerate(clips, 1)))
    for clip, file in zip(clips, files):
        clip["file"] = file
    (workdir / "clips" / "clips.json").write_text(encoding="utf-8", data=json.dumps(clips, ensure_ascii=False, indent=2))
    write_review(workdir, meta, clips)
    print(json.dumps({"review_page": str(workdir / "clips" / "index.html"),
                      "clips": [{"file": str(workdir / "clips" / c["file"]), "title": c["title"], "score": c["score"],
                                 "seconds": round(c["end"] - c["start"] + (c["cold_open"][1] - c["cold_open"][0] if c["cold_open"] else 0))}
                                for c in clips]}, ensure_ascii=False, indent=2))


def install_hint(tool):
    if sys.platform == "win32":
        return {"ffmpeg": "winget install Gyan.FFmpeg", "ffprobe": "winget install Gyan.FFmpeg", "yt-dlp": "winget install yt-dlp.yt-dlp"}[tool]
    return f"brew install {'ffmpeg' if tool.startswith('ff') else tool}"


def doctor():
    ok = True
    for tool in ("ffmpeg", "ffprobe", "yt-dlp"):
        found = shutil.which(tool)
        print(f"{tool}: {'ok' if found else 'missing (' + install_hint(tool) + ')'}")
        ok = ok and bool(found)
    if shutil.which("ffmpeg"):
        filters = run(["ffmpeg", "-hide_banner", "-filters"]).stdout
        has_ass = " subtitles " in filters
        print(f"ffmpeg captions (libass): {'ok' if has_ass else 'missing, install a full ffmpeg build (' + install_hint('ffmpeg') + ')'}")
        ok = ok and has_ass
    node_hint = "winget install OpenJS.NodeJS.LTS" if sys.platform == "win32" else "brew install node"
    print(f"node 22+ (animated clips): {'ok' if node_ok() else 'missing (' + node_hint + '), clips fall back to basic captions'}")
    print(f"clips folder: {WORK}")
    sys.exit(0 if ok else 1)


def workdir_for(value):
    path = Path(value).expanduser()
    return path if path.is_dir() else WORK / value


def main():
    parser = argparse.ArgumentParser(description="Cut vertical clips with captions from a long video.")
    commands = parser.add_subparsers(dest="command", required=True)
    step = commands.add_parser("prepare", help="download the video and write transcript.txt")
    step.add_argument("source", help="YouTube url or local video file")
    step = commands.add_parser("render", help="render the moments in moments.json")
    step.add_argument("workdir", help="the workdir prepare printed, or the video id")
    step.add_argument("-n", "--count", type=int, default=3, help="clips to render")
    step.add_argument("--basic", action="store_true", help="plain burned in captions instead of the animated template")
    commands.add_parser("doctor", help="check the tools and key are in place")
    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args.source)
    elif args.command == "render":
        render_all(workdir_for(args.workdir), args.count, args.basic)
    else:
        doctor()


if __name__ == "__main__":
    main()
