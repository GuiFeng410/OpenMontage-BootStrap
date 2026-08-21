---
name: openmontage-bootstrap-06-providers
description: >-
  BootStrap Skill03: after install, guide filling paid TTS/image/video API Keys
  into already-registered provider MCPs and hand off gated generation. Does not
  call paid APIs itself.
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
      - name: TOKENHUB_API_KEY
        required: false
      - name: OPENAI_API_KEY
        required: false
      - name: DASHSCOPE_API_KEY
        required: false
      - name: VISION_API_KEY
        required: false
      - name: VISION_BASE_URL
        required: false
      - name: VISION_MODEL
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
      - name: OSS_ACCESS_KEY_ID
        required: false
      - name: OSS_ACCESS_KEY_SECRET
        required: false
      - name: ALIYUN_OSS_BUCKET
        required: false
      - name: ALIYUN_OSS_REGION
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🔑"
---

# OpenMontage BootStrap Providers（Skill03）

## 角色

本 Skill **只做收费 Key 接入与门禁引导**。  
安装阶段通常已注册门面 + 三个 providers MCP；此处**优先补 Key**，缺 MCP 时再口述补注册。  
**不直接调用**付费 API。真正生成交给：

| 能力 | MCP | 执行 Skill |
|------|-----|------------|
| 付费 TTS | `openmontage-providers-tts` | `openmontage-providers-tts` |
| 付费生图 | `openmontage-providers-image` | `openmontage-providers-image` |
| 付费生视频 | `openmontage-providers-video` | `openmontage-providers-video` |

零 Key 出片仍走门面 + Skill02（`openmontage-bootstrap-04-produce`）。中文旁白默认 **Edge-TTS 男声**（`edge-tts`，需联网、无 Key）；离线回退 Piper。本 Skill 只管**付费** TTS/图/视频 Key。

## 硬规则

1. **不自动改** OpenClaw 配置；只口述步骤，等用户确认「已配好」。  
2. 未注册对应 providers MCP 前，**禁止**代调付费生成。  
3. 任何付费路径必须：`list → dry_run → sample(confirm_estimate) → generate(confirm + confirm_sample_ok)`。  
4. 失败时**不静默换商**；让用户另选 provider，或退回 Edge 男声 / Piper / 零 Key。  
5. Key **只**来自环境变量；禁止写入 Skill / extras / 对话明文长期保存。  
6. 门面 MCP **保持独立**；providers 为并列 MCP（TTS + Image + Video）。
7. 锁定/恢复视频渠道及付费调用前，必须由 03/04 调只读 `produce_provider_preflight(project_id)`；它只查项目计划、Pixverse 模式/图源、OSS 和项目授权证据，**不查** TokenHub/Agnes Key 或 provider 在线可用性。本 Skill 配 Key 不等于渠道、上传或付费授权。
8. 付费前仍须独立检查 provider registry / 对应 MCP availability、所需 Key 和费用闸；不能用 preflight 的 `ready=true` 代替。

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

### 2. 确认 MCP 已在（安装时通常已注册）

若安装 Skill 已配好四个 MCP，**跳过注册**，直接改对应 server 的 `env` 填 Key 并请用户重启 MCP。  

若缺失，再口述补注册（模板：`README/human/配置/templates/providers-*.mcp.json`）。

### 3. 口述填入环境变量（用户本机 / OpenClaw MCP env）

按需求勾选（同 Key 尽量复用）：

| Key | 常见覆盖 |
|-----|----------|
| `TOKENHUB_API_KEY` | 腾讯 TokenHub：混元 / Pixverse 视频 |
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

Pixverse 是**视频 provider**，只提供 T2V/I2V，不承担 T2I/I2I。商品缺图须选择已配置的 Agnes / Flux / DashScope / OpenAI / Kling / Google / Grok 等 image provider；只有成图随后要作为 Pixverse **本地图 I2V** 参考图时，才需要下列可选阿里云 OSS。Pixverse T2V、Pixverse 公网图 I2V 与 Agnes 均不需要 OSS。

若用户选择 TokenHub·Pixverse 本地图 I2V，可选配置阿里云 OSS：

| Key | 说明 |
|-----|------|
| `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` | 官方 OSS SDK 凭据；兼容 `ALIYUN_OSS_ACCESS_KEY_ID` / `ALIYUN_OSS_ACCESS_KEY_SECRET` |
| `OSS_SESSION_TOKEN` | 可选 STS 临时凭据 |
| `ALIYUN_OSS_BUCKET` / `ALIYUN_OSS_REGION` | 私有桶与区域 |
| `ALIYUN_OSS_ENDPOINT` | 可选外网 endpoint；禁止 `internal` |
| `ALIYUN_OSS_PREFIX` | 可选前缀，默认 `openmontage/tmp/` |
| `OSS_SIGNED_URL_EXPIRES_SEC` | 默认 `21600` 秒 |

引导口径：建议 RAM 用户仅授予指定前缀的 Put/Get/Delete；把字段写入本机 `.env` 后重启/刷新 MCP。**配置 Key 不等于授权上传**：每个新项目仍须在 03 聊天明确确认一次，并写入项目 decision log。批准严格要求最新固定 subject 决策同时具备 `selected=approved`、`user_approved=true`、非空 `user_response_text` 三项证据。不得让用户在 Backlot 填 Secret，不得在回复中要求用户粘贴 Secret。

等用户回复「Key 已写入并已重启 MCP」后，调用只读 `produce_provider_preflight(project_id)` 复检项目证据与 **OSS readiness**：

- `ready=false`：只说明 `blockers`、缺失字段与下一步，一次问一个问题；
- `ready=true`：不代表 TokenHub/Agnes Key 有效或 provider 在线；继续检查 registry / MCP availability 与费用闸后，才交回原 checkpoint 阶段，不重走表 1–3、不自动越级；
- 无论结果如何，不因 OSS 配置存在而自动上传；上传仍由当前项目决策证据和每次显式调用参数共同约束。

### 4. 口述启用执行 Skill

`skills.load.extraDirs` 已含 `<REPO>/skills/providers` 时，启用实际用到的：

- `openmontage-providers-tts` / `image` / `video`

### 5. 交接执行

按能力交给对应 providers Skill，并强调必须走门禁。  
示例口令：

> 用 openai TTS：先 list，再 dry_run 给我看估价，未经我确认不要 sample。

> 用 flux 生一张样图：dry_run → 我确认后再 sample。

> 用 seedance 出 5 秒样片：先估价，确认后再 sample。

## C-常用白名单（执行层已锁定）

**图：** agnes · flux · openai · dashscope · kling · google · grok
**视频：** kling（官方）· seedance · sora · veo · minimax · runway  
**TTS：** openai · elevenlabs · dashscope · doubao · google · kling  

Stock（Pexels/Pixabay）**不在本 Skill 范围** — 见可选后补 `openmontage-providers-stock` / `README/human/说明/02-免费与收费能力.md`。

## 与出片三档的关系

| 档位 | 本 Skill 做什么 |
|------|-----------------|
| 轻度 | 通常不需要 |
| 中度 | 画面用 Stock（05）；若用户**手动**要付费 TTS，再按本 Skill 补 TTS Key |
| 重度 | **全套**：引导补齐付费 TTS + 生图 + 生视频 Key，再交对应执行 Skill |

用户可读版：`README/human/说明/02-免费与收费能力.md`。

## 与 Skill01 / 02 / 安装的关系

| Skill | 职责 |
|-------|------|
| installer | 拉仓 + 注册 4 MCP + 启用 3 Skill；**不填付费 Key** |
| 01 setup | 环境 / 零 Key 依赖 |
| 02 produce | 门面 `produce_*`；主题后选轻/中/重并编排交接 |
| **03 providers（本 Skill）** | 后补 Key → 交 providers-* |

建议先 **轻度** 成片，再按需开本 Skill 填 Key 升到中度付费 TTS 或重度。

## 成功标准

- 用户在已注册的 providers MCP 中写入所需 Key 并重启  
- 后续付费调用由对应 `openmontage-providers-*` Skill 按门禁执行  

操作说明：`README/human/说明/02-免费与收费能力.md`；字段：`README/human/配置/00-字段清单.md`
