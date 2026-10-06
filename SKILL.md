---
name: musubi-clips
description: Cut short vertical spec clips (9:16 Reels and Shorts with an animated hook, word highlighted captions and pitch cards) from a YouTube video or podcast episode, for Musubi outbound to YouTubers, podcasters, creators and brands. Use this whenever someone shares a YouTube link or video and wants clips, reels, shorts, highlights, spec clips, "cut this episode", or "make N clips from this", even if they never mention a skill.
---

# Musubi spec clips

Turns one long video into a few ready to send vertical clips: 1080×1920, cropped to follow the speaker, and animated like a produced Reel. Musubi sends these privately to a creator or brand to show what their content could look like as Reels.

The script does the mechanical work (download, transcript, crop, captions, render). **You** pick the moments, by reading the transcript like an editor would. That judgement is the part that makes the clips worth sending, so give it real attention.

The script is `scripts/clipper.py` inside this skill's base directory. Run every command below with `uv run <skill dir>/scripts/clipper.py ...`. The first run installs its Python packages, which takes about a minute.

## Two designs

`render --design v2` is the default. Pass `--design v1` only when the user asks for the old look.

- **v2, Spotlight** (`assets/reel/v2.html`). Dark cinematic overlay, one hot orange accent, Bricolage Grotesque display type, no watermark unless asked for (`--watermark on` puts it small, top right, clear of the cards). The hook lands in the first 0.3 seconds: the frame whips in from a blurred zoom with a white flash, a big number slams down counting up, the punch line reassembles from scattered letters onto an orange bar with a frame shake, and the hook splits away at 1.85 seconds. Captions start as the hook leaves: a full line of up to six words in the lower third, an orange pill sweeping under each spoken word, key words left yellow with a small shake and a camera punch. Optional pitch cards: a **stat** card (a filling ring for a percentage, a counting number otherwise), a **deal** card (counting value, terms, a valuation strip, the brand chip) and a **speaker** block that wipes in. The hook and cards are placed in whichever band is clear of the speaker's face (above the head, below the chin, or below the captions), scaling down when space is tight, so nothing covers the face.
- **v1, the original** (`assets/reel/v1.html`). White tilted hook card, a yellow pill on each spoken word, uppercase outlined captions, pink pops on key words, a speaker tag and the Musubi watermark bottom right (`assets/brand/watermark.png`; `--watermark off` drops it). It ignores `hook_parts`, `stat` and `deal`.

Both are HyperFrames templates rendered per clip; the fonts in `assets/fonts` are bundled so renders never wait on a font CDN.

## First time on a machine

Run `uv run <skill dir>/scripts/clipper.py doctor`. It checks ffmpeg (with caption support), yt-dlp and Node.js 22 or newer (for the animated designs).

If `uv` itself is missing, or doctor reports missing tools, install them, asking the user first:

- **Mac:** `brew install uv ffmpeg yt-dlp node`
- **Windows:** `winget install astral-sh.uv Gyan.FFmpeg yt-dlp.yt-dlp OpenJS.NodeJS.LTS`, then open a new terminal so the new commands are found. Gyan's build of ffmpeg includes the caption support (libass) the script needs.

## Making clips

The user usually says how many clips they want. Default to 3.

### 1. Prepare

```bash
uv run <skill dir>/scripts/clipper.py prepare "<youtube url>"
```

This downloads only the audio and writes a transcript; the video for each clip is fetched later, at render time. The transcript is YouTube's auto captions **in the language spoken**: `en-orig` for an English video, `hi-orig` for a Hindi or Hinglish one, with word timings. Only when no original track exists does it fall back to YouTube's English translation, which YouTube often refuses with HTTP 429. A video with no auto captions at all cannot be clipped, and prepare says so. Everything is cached in `MusubiClips/<video id>/` under the user's home folder, so running it again is instant.

It prints JSON with `workdir`, `title`, `duration`, `language`, `transcript` (a text file) and `moments_file` (where your picks go).

If prepare fails on its first yt-dlp call, YouTube refused one request: wait a few seconds and run it again.

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

- `hook_text`: at most 8 words on screen for the first seconds. Write it in English. No emojis, hashtags or dashes.
- `hook_parts` (v2): the same hook split for the animation: `kicker` (a short line above), `big` (one number or short word that slams in, such as `90%`, `₹5 Cr`, `₹299`; a number counts up), `punch` (one to three words; the first sits white, the rest land on the orange bar). Any part may be `""`. Without it v2 splits `hook_text` itself.
- `cold_open_start` / `cold_open_end`: optional, a 2 to 6 second line from inside the clip, usually the payoff, played first as a teaser before the clip starts. Use `null` when the opening line is already strong.
- `title`: a short working title. `reason`: one sentence on why it holds a viewer.
- `emphasis`: 3 to 8 words from the clip's own speech to punch: names, places, numbers, the words the point turns on. Numbers are emphasised automatically. Spell them exactly as the captions will show them (after romanising, below).
- `speaker_name` and `speaker_role`: who is talking, for the name tag. Take them from the video title, the intro or someone addressing them by name; leave them out if you're unsure rather than guessing, and leave them out when several people talk in the clip.
- `stat` (v2, optional): a number spoken in the clip. `{"at": <source seconds when it is said>, "value": "90%", "label": "Water", "sub": "+ harmful chemicals", "sub_at": <source seconds>, "hold": 3}`. A percentage of 100 or less draws a filling ring.
- `deal` (v2, optional): an ask or an offer spoken in the clip. `{"at": <source seconds>, "kicker": "The ask", "value": "₹75L", "sub": "for 1.5% equity", "strip": "₹50 crore valuation", "brand": "Cleevo", "hold": 5}`.
- Only put a figure on a card if it is said in that clip. `at` is in source seconds and must fall inside the clip.
- Scores from 1 to 5: `hook` (first 3 seconds stop the scroll), `standalone` (needs no context), `payoff` (ends on a satisfying line), `emotion` (funny, surprising, controversial or moving). Be strict: most clips land at 2 to 4, and 5 is rare. Scores only rank clips within this video; they do not predict views.

Write them to `moments_file` as a JSON array:

```json
[
  {
    "start": 819.8, "end": 864.6,
    "cold_open_start": 856.0, "cold_open_end": 863.1,
    "title": "₹5 crore for 10%: the biggest deal so far",
    "hook_text": "Biggest deal on the show: ₹5 crore",
    "hook_parts": { "kicker": "Biggest deal on the show", "big": "₹5 Cr", "punch": "For 10%" },
    "reason": "The founder names the number, the investors say done, and the host calls it the biggest deal yet.",
    "emphasis": ["crore", "done", "deal", "valuation"],
    "deal": { "at": 824.7, "kicker": "The deal", "value": "₹5 Cr", "sub": "for 10% equity", "strip": "₹50 crore valuation", "brand": "Cleevo", "hold": 9 },
    "hook": 4, "standalone": 4, "payoff": 5, "emotion": 4
  }
]
```

### 3. Romanise a Hindi transcript

When `language` is not `en` (a Hindi or Hinglish video gives Devanagari), the captions should read as romanised Hinglish, the way Indian Reels are captioned. After writing `moments.json`, run:

```bash
uv run <skill dir>/scripts/clipper.py words <workdir>
```

It lists every word inside your moments that has no spelling yet. Write `roman.json` in the workdir mapping each to its everyday Roman spelling: `{"पानी": "paani", "क्लीनर": "cleaner", "हैं": "hain"}`. English words YouTube wrote in Devanagari go back to English, names are capitalised (`Cleevo`, `Mayank`). Run `words` again until it prints `[]`. Punctuation is kept automatically.

### 4. Check the source for burned in subtitles

Grab one source frame and look at it. If the video already has subtitles burned into the bottom (TV shows usually do), render with `--keep-height 0.86`, which keeps the top 86% of the frame and crops them off. Raise it towards 0.9 if a sliver remains, lower it if the subtitles sit higher.

### 5. Render

```bash
uv run <skill dir>/scripts/clipper.py render <workdir> -n <clips wanted> [--design v1|v2] [--watermark on|off] [--keep-height 0.86]
```

`--watermark` adds or drops the musubiclip.com watermark. Leave it out to get each design's default: on for v1, off for v2. Ask the user only if they mention branding.

It snaps your picks to word boundaries, drops any that overlap or fall outside 12 to 90 seconds, keeps the top `n` by score, and renders them. It fetches only each clip's minutes of video, then renders up to 3 clips at once in a headless browser: about 6 to 7 minutes for 3 clips on a recent Mac, slower on Windows. Run it in the background and tell the user it is rendering. The first run also downloads the renderer. Without Node it falls back to plain captions on its own; `--basic` forces them. It prints the clip files and a `review_page`. If it says moments.json needs fixing, fix the listed fields and run it again.

Rendering again replaces the whole `clips` folder, so to add clips, add candidates to `moments.json` and render with a higher `-n`.

### 6. Look before you hand over

Grab frames from each clip and look at them: one in the hook (about 1.3 seconds), one while each card shows, one in the middle.

```bash
ffmpeg -v error -y -ss 1.3 -i "<clip file>" -frames:v 1 -vf scale=360:-2 "<workdir>/check.jpg"
```

Check that the hook is whole and readable, the cards appear and sit clear of the face, the captions are in the lower third, and no burned in subtitles show. In a tight close up the hook shrinks to fit above the head; mention it if it reads small. Wide shots with two people far apart follow the bigger face; mention that if you see it. Delete the check frames afterwards.

### 7. Report

Open the review page for the user (`open <review_page>` on a Mac, `start "" "<review_page>"` on Windows), then list each clip: file path, length, hook line, score and your one line reason. Remind them of two things:

- **Watch each clip with sound before sending.** Romanised captions come from YouTube's auto captions, so a word can be misheard or an English word misspelt.
- **Share privately and never post publicly.** Use a Google Drive "anyone with the link" share, or an unlisted YouTube upload. This is the creator's own content, cut without their permission.

## Changing the clips

- **Different moments or hook lines:** edit `moments.json` and run `render` again. There's no need to prepare again.
- **More clips from the same video:** add candidates to `moments.json`, spell any new words in `roman.json`, and render with a higher `-n`.
- **The old look:** `--design v1`.
- **With or without the watermark:** `--watermark on` or `--watermark off`.
- **The download fails** with "Sign in to confirm" or a format error: update yt-dlp (`brew upgrade yt-dlp` on a Mac, `winget upgrade yt-dlp.yt-dlp` on Windows) and try again, since YouTube changes often.
