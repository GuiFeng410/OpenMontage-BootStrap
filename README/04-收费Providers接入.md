# 04 — 收费 Providers 接入（Skill03）

> 零 Key 出片先完成 [03](./03-零Key最小出片.md)。本文为**可选**收费能力。

使用 Skill：`openmontage-bootstrap-providers`（引导）  
真正生成：`openmontage-providers-tts` / `image` / `video`

## 架构（门面不动）

```text
openmontage-bootstrap          ← 零 Key setup/produce
openmontage-providers-tts      ← 付费语音
openmontage-providers-image    ← 付费生图（C-常用 6）
openmontage-providers-video    ← 付费生视频（C-常用 6）
```

## 1. 配环境变量

| Key | 用途 |
|-----|------|
| `FAL_KEY` | flux 图；seedance / minimax 视频 |
| `OPENAI_API_KEY` | openai TTS/图；sora 视频 |
| `DASHSCOPE_API_KEY` | dashscope TTS/图 |
| `KLING_API_KEY` | kling TTS；官方 Kling 图/视频 |
| `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` | google TTS/图；veo |
| `XAI_API_KEY` | grok 图 |
| `RUNWAY_API_KEY` | runway 视频 |
| `ELEVENLABS_API_KEY` / `DOUBAO_SPEECH_API_KEY` | 对应 TTS |
| `OPENMONTAGE_PROJECTS_DIR` | 沙箱根（必填） |
| `OPENMONTAGE_MAX_COST_USD` | 估价上限（可选） |
| `OPENMONTAGE_ALLOWED_PROVIDERS` | 白名单，如 `flux,kling`（可选） |

## 2. 注册 MCP（口述/手改）

模板：

- [templates/providers-tts.mcp.json](./templates/providers-tts.mcp.json)
- [templates/providers-image.mcp.json](./templates/providers-image.mcp.json)
- [templates/providers-video.mcp.json](./templates/providers-video.mcp.json)

按需注册 1～3 个 server；`cwd` 为仓库根，`command` 用 `.venv` python。

## 3. 启用 Skill

`extraDirs` → `<REPO>/openmontage/skills`，启用：

- `openmontage-bootstrap-providers`（本引导，可选）  
- 以及你实际用到的 `openmontage-providers-tts` / `image` / `video`

## 4. 门禁协议（所有付费能力）

```text
list_*_providers
→ *_dry_run（展示估价，等用户同意）
→ *_sample(..., confirm_estimate=true)
→ 用户确认样片
→ *_generate(..., confirm=true, confirm_sample_ok=true)
```

失败不静默换商。

## 5. 对 Agent 示例口令

> 按 Skill03：我要配 Kling 生图+生视频，只口述步骤，先别调用付费 API。

> list 可用图商；用 flux dry_run 估价，未经确认不要 sample。

## 白名单（C-常用）

- **图：** flux · openai · dashscope · kling · google · grok  
- **视频：** kling（官方）· seedance · sora · veo · minimax · runway  
- **TTS：** openai · elevenlabs · dashscope · doubao · google · kling  

Stock 素材站另议，不在本文。
