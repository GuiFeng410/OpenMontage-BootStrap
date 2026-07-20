# 04 — 收费 Providers 接入（Skill03）

> 前提：安装时已注册门面 + 三个 providers MCP，且零 Key 路径可参考 [03](./03-零Key最小出片.md)。  
> 本文只做**可选**：往已有 MCP 里填 Key，即可用付费能力。

使用 Skill：`openmontage-bootstrap-providers`（引导填 Key）  
真正生成：`openmontage-providers-tts` / `image` / `video`

## 架构（安装时已注册，Key 后填）

```text
openmontage-bootstrap          ← 零 Key setup/produce
openmontage-providers-tts      ← 付费语音（安装已注册，Key 可选）
openmontage-providers-image    ← 付费生图
openmontage-providers-video    ← 付费生视频
```

## 1. 在已有 MCP 的 env 里填 Key

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
| `OPENMONTAGE_MAX_COST_USD` | 估价上限（可选） |
| `OPENMONTAGE_ALLOWED_PROVIDERS` | 白名单，如 `flux,kling`（可选） |

填完后**重启**对应 MCP。不必重装项目、不必重配 cwd/command。

若安装时漏了某个 providers server，模板仍在 [templates/](./templates/)。

## 2. 启用执行 Skill

`extraDirs` → `<REPO>/openmontage/skills`，按需启用：

- `openmontage-providers-tts` / `image` / `video`

## 3. 门禁协议

```text
list_*_providers
→ *_dry_run（展示估价，等用户同意）
→ *_sample(..., confirm_estimate=true)
→ 用户确认样片
→ *_generate(..., confirm=true, confirm_sample_ok=true)
```

失败不静默换商。

## 4. 对 Agent 示例口令

> 按 Skill03：我要给 Kling 填 Key，只口述改 env，先别调用付费 API。

> list 可用图商；用 flux dry_run 估价，未经确认不要 sample。

## 白名单（C-常用）

- **图：** flux · openai · dashscope · kling · google · grok  
- **视频：** kling（官方）· seedance · sora · veo · minimax · runway  
- **TTS：** openai · elevenlabs · dashscope · doubao · google · kling  
