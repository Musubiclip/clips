# Musubi clips

A Claude Code skill. Paste a YouTube link and get short vertical clips (9:16 Reels and Shorts) cut from it: a hook card in the first 3 seconds, word highlighted captions and a crop that follows the speaker.

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
