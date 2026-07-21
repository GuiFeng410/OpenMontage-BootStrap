---
name: openmontage-providers-image
description: Drive paid/cloud image generation via openmontage-providers-image MCP with dry_run, sample, and confirm gates.
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
        description: Sandboxed projects root for image outputs
      - name: OPENMONTAGE_MAX_COST_USD
        required: false
        description: Hard cap for estimated image cost
      - name: OPENMONTAGE_ALLOWED_PROVIDERS
        required: false
        description: Comma list e.g. flux,openai,dashscope,kling,google,grok
      - name: FAL_KEY
        required: false
      - name: OPENAI_API_KEY
        required: false
      - name: DASHSCOPE_API_KEY
        required: false
      - name: KLING_API_KEY
        required: false
      - name: GEMINI_API_KEY
        required: false
      - name: GOOGLE_API_KEY
        required: false
      - name: XAI_API_KEY
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🖼️"
---

# OpenMontage Providers Image (C-常用)

## Scope

**Paid/cloud image generation only.** Stock (Pexels/Pixabay) is out of scope.

Supported providers: `flux` · `openai` · `dashscope` · `kling` · `google` · `grok`.

| provider | tool | typical Key |
|----------|------|-------------|
| flux | flux_image | FAL_KEY |
| openai | openai_image | OPENAI_API_KEY |
| dashscope | dashscope_image | DASHSCOPE_API_KEY |
| kling | kling_official_image | KLING_API_KEY |
| google | google_imagen | GEMINI_API_KEY / GOOGLE_API_KEY |
| grok | grok_image | XAI_API_KEY |

## Required MCP

`openmontage-providers-image` (`python -m openmontage.mcp.providers_image`)

## Hard protocol

1. `list_image_providers` — only offer **available** + key-configured providers.
2. Announce provider, model, estimated USD **before** any paid call.
3. `image_dry_run(provider, prompt, extras_json)` → show estimate to user.
4. After user accepts estimate → `image_sample(..., confirm_estimate=true)`.
5. User visual check → `image_generate(..., confirm=true, confirm_sample_ok=true)`.
6. On failure: surface blocker; **do not** silently switch provider.
7. Never put API keys in extras or Skills.

## extras_json

Provider-specific fields as a JSON object string, e.g.:

```json
{"model": "flux-pro", "aspect_ratio": "16:9", "seed": 42}
```

## Budget

Respect `OPENMONTAGE_MAX_COST_USD` and `OPENMONTAGE_ALLOWED_PROVIDERS` when set.

## 与 produce 交接（重度档）

由 Skill02 在 **重度** 画面分支按镜头交接本 Skill。

1. 走完整门禁后，生图文件落在项目沙箱。  
2. 回传路径给 produce，写入 `asset_manifest_json`（建议含 `id` / `kind: image` / `path` / `provider`）。  
3. 不调用 compose；中度画面走 Stock，不走本 Skill。
