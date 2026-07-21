---
name: openmontage-providers-tts
description: Drive paid/cloud TTS via openmontage-providers-tts MCP with dry_run, sample, and confirm gates.
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
        description: Sandboxed projects root for TTS outputs
      - name: OPENMONTAGE_MAX_COST_USD
        required: false
        description: Hard cap for estimated TTS cost
      - name: OPENMONTAGE_ALLOWED_PROVIDERS
        required: false
        description: Comma list e.g. openai,elevenlabs,dashscope,doubao
      - name: OPENAI_API_KEY
        required: false
      - name: ELEVENLABS_API_KEY
        required: false
      - name: DASHSCOPE_API_KEY
        required: false
      - name: DOUBAO_SPEECH_API_KEY
        required: false
      - name: GOOGLE_API_KEY
        required: false
      - name: KLING_API_KEY
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🎙️"
---

# OpenMontage Providers TTS (P2)

## Scope

**Advanced / paid TTS only.** Zero-key Piper remains on `openmontage-media`.

Supported providers (tool names): `openai` · `elevenlabs` · `dashscope` · `doubao` · `google` · `kling`.

## Required MCP

`openmontage-providers-tts` (`python -m openmontage.mcp.providers_tts`)

## Hard protocol

1. `list_tts_providers` — only offer **available** + key-configured providers.
2. Announce provider, model, sample vs batch, estimated USD **before** any paid call.
3. `tts_dry_run(provider, text, extras_json)` → show estimate to user.
4. After user accepts estimate → `tts_sample(..., confirm_estimate=true)`.
5. User listen-check → `tts_generate(..., confirm=true, confirm_sample_ok=true)`.
6. On failure: surface blocker; **do not** silently switch provider. Offer Piper via media MCP or ask user to pick another provider.
7. Log `decision_log` category `voice_selection` with options considered.

## extras_json

Pass provider-specific fields as a JSON object string, e.g.:

```json
{"voice": "nova", "model": "gpt-4o-mini-tts", "instructions": "curious educational Mandarin"}
```

Never put API keys in extras or Skills.

## Budget

Respect `OPENMONTAGE_MAX_COST_USD` and `OPENMONTAGE_ALLOWED_PROVIDERS` when set.

## With animated-explainer / produce 交接

| 档位 | 何时用本 Skill |
|------|----------------|
| 轻度 | 不用（门面 Piper） |
| 中度 | **仅当用户显式选云端 TTS**；已配 Key 也不要自动升级 |
| 重度 | **必用**付费 TTS（全套语音） |

被 Skill02 交接时：

1. 产出 wav/mp3 写到项目沙箱（路径告知 produce）。  
2. produce 用该路径做字幕与 compose；本 Skill 不调 `produce_compose_*`。  
3. 失败不静默改走 Piper；问用户：换 provider / 退回 Piper / 中止。

At assets stage: if a paid TTS provider is available and user wants higher voice quality, present Piper (free) vs selected paid path with itemized cost, then follow this protocol. Default remains Piper unless user opts in.
