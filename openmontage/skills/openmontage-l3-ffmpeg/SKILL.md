---
name: openmontage-l3-ffmpeg
description: Pointer to FFmpeg Layer3 skill for probe/mix/encode checks.
metadata:
  openclaw:
    requires:
      bins: [ffmpeg, ffprobe]
    os: [win32, darwin, linux]
    emoji: "🎞️"
---

# OpenMontage L3 — FFmpeg

Read:

- `.agents/skills/ffmpeg/SKILL.md` (or `.claude/skills/ffmpeg/SKILL.md`)

Use `probe_media` after compose. Prefer re-encode settings from OpenMontage compose tooling rather than ad-hoc ffmpeg flags unless debugging.
