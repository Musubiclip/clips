---
name: musubi-clips
description: Cut short vertical spec clips (9:16 Reels and Shorts with a hook line and word highlighted captions) from a YouTube video or podcast episode, for Musubi outbound to YouTubers, podcasters, creators and brands. Use this whenever someone shares a YouTube link or video and wants clips, reels, shorts, highlights, spec clips, "cut this episode", or "make N clips from this", even if they never mention a skill.
---

# Musubi spec clips

Turns one long video into a few ready to send vertical clips: 1080×1920, cropped to follow the speaker, and animated like a produced Reel. A hook card lands in the first 3 seconds, placed clear of the speaker's face: above the head, else between chin and captions, else below the captions. Captions show a full line of up to six words that stays on screen while it is spoken, with a yellow pill moving to each word as the speaker says it. Key words and numbers get a pink pop and a camera punch. A speaker tag, a progress bar and a Musubi watermark (mark and musubiclip.com in a dark pill, bottom right, `assets/brand/watermark.png`) round it off. The animation is a HyperFrames template (`assets/reel/index.html`) rendered per clip. Musubi sends these privately to a creator or brand to show what their content could look like as Reels.

The script does the mechanical work (download, transcript, crop, captions, render). **You** pick the moments, by reading the transcript like an editor would. That judgement is the part that makes the clips worth sending, so give it real attention.

The script is `scripts/clipper.py` inside this skill's base directory. Run every command below with `uv run <skill dir>/scripts/clipper.py ...`. The first run installs its Python packages, which takes about a minute.

## First time on a machine

Run `uv run <skill dir>/scripts/clipper.py doctor`. It checks ffmpeg (with caption support), yt-dlp and Node.js 22 or newer (for the animated style).

If `uv` itself is missing, or doctor reports missing tools, install them, asking the user first:

- **Mac:** `brew install uv ffmpeg yt-dlp node`
- **Windows:** `winget install astral-sh.uv Gyan.FFmpeg yt-dlp.yt-dlp OpenJS.NodeJS.LTS`, then open a new terminal so the new commands are found. Gyan's build of ffmpeg includes the caption support (libass) the script needs.

## Making clips

The user usually says how many clips they want. Default to 3.

### 1. Prepare

```bash
uv run <skill dir>/scripts/clipper.py prepare "<youtube url>"
```

This downloads only the audio and writes a transcript; the video for each clip is fetched later, at render time. The transcript is YouTube's English auto captions (`en-orig`, `en-US-orig` and the like), which is free and instant. **On a Hindi or Hinglish video that track is YouTube's English translation of the speech**, so the captions read as English subtitles, not the spoken words. A video with no English auto captions cannot be clipped, and prepare says so. Everything is cached in `MusubiClips/<video id>/` under the user's home folder, so running it again is instant.

It prints JSON with `workdir`, `title`, `duration`, `transcript` (a text file) and `moments_file` (where your picks go).

### 2. Pick the moments

Read the whole `transcript.txt`. Each line is `[start-end seconds] text`. Then choose **twice as many candidates as the clips wanted**. The script ranks them by your scores and keeps the best, so a wider pool gives better final clips.

What makes a clip worth sending:

- **It stands alone.** Someone who never saw the video has to follow it. No "as I said", no unexplained "he" or "that". This matters most, because the recipient judges the clip cold.
- **It hooks inside 3 seconds.** Start on the first word of a line that makes someone stop scrolling: a bold claim, a number, a question, a confession.
- **It pays off.** End right after the punchline or the answer, never mid thought.
- **Length is 12 to 60 seconds.** 20 to 45 is the sweet spot for Reels.
- **Clips never overlap.**
- **Timestamps come from the transcript lines.** The script snaps them to the nearest word, so a line's start and end are safe choices.

For each candidate write:

- `hook_text`: at most 8 words on screen for the first 3 seconds. Write it in English, like the captions. No emojis, hashtags or dashes.
- `cold_open_start` / `cold_open_end`: optional, a 2 to 6 second line from inside the clip, usually the payoff, played first as a teaser before the clip starts. Use `null` when the opening line is already strong.
- `title`: a short working title. `reason`: one sentence on why it holds a viewer.
- `emphasis`: 3 to 8 words from the clip's own speech to punch: names, places, numbers, the words the point turns on. They pop in pink on screen and stay yellow afterwards, and the camera punches in on them. Numbers are emphasised automatically. Pick words spelled exactly as in the transcript, since matching is by the word itself.
- `speaker_name` and `speaker_role`: who is talking, for the name tag after the hook. Take them from the video title or intro; leave them out if you're unsure, rather than guessing.
- Scores from 1 to 5: `hook` (first 3 seconds stop the scroll), `standalone` (needs no context), `payoff` (ends on a satisfying line), `emotion` (funny, surprising, controversial or moving). Be strict: most clips land at 2 to 4, and 5 is rare. Scores only rank clips within this video; they do not predict views.

Write them to `moments_file` as a JSON array:

```json
[
  {
    "start": 52.5, "end": 105.9,
    "cold_open_start": null, "cold_open_end": null,
    "title": "Rs 10 lakh profit before the expo",
    "hook_text": "Aaj ka profit: lagbhag ₹10,00,000",
    "reason": "Live trade proof with big rupee numbers keeps viewers waiting for the total.",
    "emphasis": ["profit", "₹10,00,000", "trade"],
    "speaker_name": "Wizard Trader", "speaker_role": "Forex trader",
    "hook": 4, "standalone": 4, "payoff": 4, "emotion": 3
  }
]
```

### 3. Render

```bash
uv run <skill dir>/scripts/clipper.py render <workdir> -n <clips wanted>
```

It snaps your picks to word boundaries, drops any that overlap or fall outside 12 to 90 seconds, keeps the top `n` by score, and renders them. It fetches only each clip's minutes of video, then renders up to 3 clips at once in a headless browser: about 6 to 7 minutes for 3 clips on a recent Mac, slower on Windows. Run it in the background and tell the user it is rendering. The first run also downloads the renderer. Without Node it falls back to plain captions on its own; `--basic` forces them. It prints the clip files and a `review_page`. If it says moments.json needs fixing, fix the listed fields and run it again.

### 4. Look before you hand over

Grab one frame from each clip and look at it, to catch a bad crop or missing captions:

```bash
ffmpeg -v error -y -ss 5 -i "<clip file>" -frames:v 1 -vf scale=360:-2 "<workdir>/check.jpg"
```

Then look at `check.jpg`, and delete it afterwards.

The speaker's face should sit near the middle, the captions in the lower third, the hook card clear of the face, and the speaker tag near the top. Wide shots with two people far apart follow the bigger face; mention that if you see it.

### 5. Report

Open the review page for the user (`open <review_page>` on a Mac, `start "" "<review_page>"` on Windows), then list each clip: file path, length, hook line, score and your one line reason. Remind them of two things:

- **Watch each clip with sound before sending.** On a Hindi or Hinglish video the captions are a translation, so the highlight does not land on the spoken word and a line can be mistranslated.
- **Share privately and never post publicly.** Use a Google Drive "anyone with the link" share, or an unlisted YouTube upload. This is the creator's own content, cut without their permission.

## Changing the clips

- **Different moments or hook lines:** edit `moments.json` and run `render` again. There's no need to prepare again.
- **More clips from the same video:** add candidates to `moments.json` and render with a higher `-n`.
- **The download fails** with "Sign in to confirm" or a format error: update yt-dlp (`brew upgrade yt-dlp` on a Mac, `winget upgrade yt-dlp.yt-dlp` on Windows) and try again, since YouTube changes often.
