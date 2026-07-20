---
name: openmontage-bootstrap-providers
description: >-
  BootStrap Skill03: guide paid TTS / image / video provider setup (Keys + MCP
  registration + gate protocol). Does not call paid APIs itself — hands off to
  openmontage-providers-tts / image / video.
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
      - name: OPENMONTAGE_MAX_COST_USD
        required: false
      - name: OPENMONTAGE_ALLOWED_PROVIDERS
        required: false
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
      - name: RUNWAY_API_KEY
        required: false
      - name: XAI_API_KEY
        required: false
      - name: ELEVENLABS_API_KEY
        required: false
      - name: DOUBAO_SPEECH_API_KEY
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🔑"
---

# OpenMontage BootStrap Providers（Skill03）

## 角色

本 Skill **只做收费接入引导**：配 Key、口述注册 MCP、说明门禁协议。  
**不直接调用**付费 API。真正生成交给：

| 能力 | MCP | 执行 Skill |
|------|-----|------------|
| 付费 TTS | `openmontage-providers-tts` | `openmontage-providers-tts` |
| 付费生图 | `openmontage-providers-image` | `openmontage-providers-image` |
| 付费生视频 | `openmontage-providers-video` | `openmontage-providers-video` |

零 Key 出片仍走门面 + Skill02（`openmontage-bootstrap-produce` / Piper）。

## 硬规则

1. **不自动改** OpenClaw 配置；只口述步骤，等用户确认「已配好」。  
2. 未注册对应 providers MCP 前，**禁止**代调付费生成。  
3. 任何付费路径必须：`list → dry_run → sample(confirm_estimate) → generate(confirm + confirm_sample_ok)`。  
4. 失败时**不静默换商**；让用户另选 provider 或退回 Piper / 零 Key。  
5. Key **只**来自环境变量；禁止写入 Skill / extras / 对话明文长期保存。  
6. 门面 MCP **保持独立**；providers 为并列 MCP（TTS + Image + Video）。

## 何时启用本 Skill

用户说类似：

- 我想用云端语音 / ElevenLabs / DashScope TTS  
- 我想用 FLUX / Kling 生图  
- 我想用 Seedance / Sora / 可灵生视频  
- 怎么配 API Key / 收费能力  

若用户只要零 Key：交回 Skill01/02，不要强行推收费。

## 流程

### 1. 确认需求与预算

问清：只要 TTS、只要图、只要视频，还是组合。  
建议设置：`OPENMONTAGE_MAX_COST_USD`、`OPENMONTAGE_ALLOWED_PROVIDERS`（逗号白名单）。

### 2. 口述配环境变量（用户本机）

按需求勾选（同 Key 尽量复用）：

| Key | 常见覆盖 |
|-----|----------|
| `FAL_KEY` | 图 flux；视频 seedance / minimax；（veo 可选 fal 后端） |
| `OPENAI_API_KEY` | TTS openai；图 openai；视频 sora |
| `DASHSCOPE_API_KEY` | TTS dashscope；图 dashscope |
| `KLING_API_KEY` | TTS kling；图/视频官方 Kling |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | TTS google；图 google；视频 veo |
| `XAI_API_KEY` | 图 grok |
| `RUNWAY_API_KEY` | 视频 runway |
| `ELEVENLABS_API_KEY` | TTS elevenlabs |
| `DOUBAO_SPEECH_API_KEY` | TTS doubao |

另需：`OPENMONTAGE_PROJECTS_DIR`（与门面相同沙箱根）。

### 3. 口述注册 providers MCP（可多选）

模板（仓内，可提交）：

- `README/templates/providers-tts.mcp.json`
- `README/templates/providers-image.mcp.json`
- `README/templates/providers-video.mcp.json`

要点（每个 server）：

- `command`：仓库 `.venv` 的 python  
- `cwd`：`<REPO>`  
- `args`：`-m openmontage.mcp.providers_tts` / `providers_image` / `providers_video`  
- `env`：上表 Key + `OPENMONTAGE_PROJECTS_DIR` + `PYTHONUTF8=1`

等用户回复「MCP 已配好」再继续。

### 4. 口述启用 Skill

`skills.load.extraDirs` 已含 `<REPO>/openmontage/skills` 时，启用：

- 本 Skill：`openmontage-bootstrap-providers`（可选保留）  
- 对应执行 Skill：`openmontage-providers-tts` / `image` / `video`

### 5. 交接执行

按能力交给对应 providers Skill，并强调必须走门禁。  
示例口令：

> 用 openai TTS：先 list，再 dry_run 给我看估价，未经我确认不要 sample。

> 用 flux 生一张样图：dry_run → 我确认后再 sample。

> 用 seedance 出 5 秒样片：先估价，确认后再 sample。

## C-常用白名单（执行层已锁定）

**图：** flux · openai · dashscope · kling · google · grok  
**视频：** kling（官方）· seedance · sora · veo · minimax · runway  
**TTS：** openai · elevenlabs · dashscope · doubao · google · kling  

Stock（Pexels/Pixabay）**不在本 Skill 范围**（以后单独 stock MCP）。

## 与 Skill01 / 02 的关系

| Skill | 职责 |
|-------|------|
| 01 setup | 环境 / 零 Key 依赖 |
| 02 produce | 门面 `produce_*`，默认 Piper |
| **03 providers（本 Skill）** | 收费接入引导 → 交 providers-* |

用户可在零 Key 成片后再按需启用本 Skill，不必一开始就配齐全部 Key。

## 成功标准

- 用户知道要配哪些 Key / 哪个 MCP  
- 用户已口述确认 MCP + Skill 就绪  
- 后续付费调用由对应 `openmontage-providers-*` Skill 按门禁执行  

操作说明：`README/04-收费Providers接入.md`
