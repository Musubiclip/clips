# Musubi clips

A Claude Code skill. Paste a YouTube link and get short vertical clips (9:16 Reels and Shorts) cut from it: an animated hook in the first seconds, word highlighted captions, optional stat and deal cards, and a crop that follows the speaker.

Two designs: `v2` Spotlight (default, dark with one orange accent, no watermark) and `v1` the original white card look with the Musubi watermark. Pick one with `render --design v1|v2`, add or drop the watermark with `--watermark on|off`, and close a v2 clip on the creator's or brand's logo with `--end-screen`.

## Install

```bash
npx skills add Musubiclip/clips
```

## Use

```
make 3 clips from https://www.youtube.com/watch?v=...
```

The clips land in `~/MusubiClips/<video id>/clips/`, with a review page listing each clip, its hook and why it was picked.

## Needs

- [uv](https://docs.astral.sh/uv/)
- ffmpeg and [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Node.js 22 or newer, for the animated captions

Mac: `brew install uv ffmpeg yt-dlp node`
Windows: `winget install astral-sh.uv Gyan.FFmpeg yt-dlp.yt-dlp OpenJS.NodeJS.LTS`

## Before you share a clip

Watch it with sound first. Only cut videos you own or have permission to use.
