---
name: openmontage-providers-video
description: Drive paid/cloud video generation via openmontage-providers-video MCP with dry_run, short sample, and confirm gates.
metadata:
  openclaw:
    requires:
      bins:
        - python
      env:
        - OPENMONTAGE_PROJECTS_DIR
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
        description: Sandboxed projects root for video outputs
      - name: OPENMONTAGE_MAX_COST_USD
        required: false
        description: Hard cap for estimated video cost
      - name: OPENMONTAGE_ALLOWED_PROVIDERS
        required: false
        description: Comma list e.g. kling,seedance,sora,veo,minimax,runway
      - name: FAL_KEY
        required: false
      - name: OPENAI_API_KEY
        required: false
      - name: KLING_API_KEY
        required: false
      - name: GEMINI_API_KEY
        required: false
      - name: GOOGLE_API_KEY
        required: false
      - name: RUNWAY_API_KEY
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🎬"
---

# OpenMontage Providers Video (C-常用)

## Scope

**Paid/cloud video generation only.** Stock footage is out of scope. Uses **official** Kling (`kling_official_video`), not fal `kling_video`.

Supported providers: `kling` · `seedance` · `sora` · `veo` · `minimax` · `runway`.

| provider | tool | typical Key |
|----------|------|-------------|
| kling | kling_official_video | KLING_API_KEY |
| seedance | seedance_video | FAL_KEY |
| sora | sora_video | OPENAI_API_KEY |
| veo | veo_video | GEMINI_API_KEY / GOOGLE_API_KEY or FAL_KEY |
| minimax | minimax_video | FAL_KEY |
| runway | runway_video | RUNWAY_API_KEY |

## Required MCP

`openmontage-providers-video` (`python -m openmontage.mcp.providers_video`)

## Hard protocol

1. `list_video_providers` — only offer **available** + key-configured providers.
2. Announce provider, model, duration, estimated USD **before** any paid call.
3. `video_dry_run(provider, prompt, extras_json)` → show estimate to user.
4. After user accepts → `video_sample(..., confirm_estimate=true)` (short clip ≈4–5s when duration omitted).
5. User watch-check → `video_generate(..., confirm=true, confirm_sample_ok=true)`.
6. On failure: surface blocker; **do not** silently switch provider.
7. Never put API keys in extras or Skills.

## Sample duration

If `extras_json` omits `duration` / `seconds`, sample injects short defaults (kling/seedance/runway ≈5s, sora 4s, veo 4s).

## extras_json

```json
{"duration": "5", "aspect_ratio": "16:9", "model_variant": "veo3.1"}
```

## Budget

Respect `OPENMONTAGE_MAX_COST_USD` and `OPENMONTAGE_ALLOWED_PROVIDERS` when set.

## 与 produce 交接（重度档）

由 Skill02 在 **重度** 画面分支按镜头交接本 Skill。

1. 走完整门禁后，短视频/镜头文件落在项目沙箱。  
2. 回传路径给 produce，写入 `asset_manifest_json`（建议含 `id` / `kind: video` / `path` / `provider`）。  
3. 不调用 compose；中度画面走 Stock，不走本 Skill。
