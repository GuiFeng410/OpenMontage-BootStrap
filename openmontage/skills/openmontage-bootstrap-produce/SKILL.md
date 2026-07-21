---
name: openmontage-bootstrap-produce
description: >-
  BootStrap Skill02 produce flow: after theme confirmation, present light/medium/heavy
  production tiers, then run facade produce_* with optional stock and paid handoffs.
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
        description: Sandboxed projects root
      - name: OPENMONTAGE_P1_ALLOW_WRITES
        required: true
        description: Must be true for produce writes
      - name: PIPER_MODEL_DIR
        required: false
      - name: OPENMONTAGE_PIPER_MODEL
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "🎬"
---

# OpenMontage BootStrap Produce（Skill02）

## Scope

统一入口出片：门面 `produce_*` + 按档位交接 Stock / 付费 providers。  
交付物：`<PROJECTS>/<project_id>/renders/final.mp4`。

**不做：** 代用户选档、伪造 `approval_text`、静默调付费 API、静默换 provider。

## Required MCP

- 必有：`openmontage-bootstrap`（`produce_*`）  
- 中度另需：`openmontage-providers-stock`  
- 重度另需：`openmontage-providers-tts` / `image` / `video`  
- 中度可选付费 TTS：同上 TTS MCP  

前提：Skill01 `verify_ready` 通过（或等价 doctor ready）。

## 档位定义（主题确认后必讲清并让用户选）

| 档位 | 画面 | 语音 | Key | 费用 |
|------|------|------|-----|------|
| **轻度** | 模板/字幕为主，无 Stock、无 AI 生图生视频 | Piper（零 Key） | 无 | $0 |
| **中度** | Stock（Pexels/Pixabay）搜图/搜视频 → 下载进沙箱 | **默认 Piper**；若已配 TTS Key，可**手动**改云端 TTS | 至少一个免费 Stock Key | Stock $0 + 可选付费 TTS |
| **重度** | 付费 AI 生图 + 付费 AI 生视频 | **付费高级 TTS**（不默认 Piper） | TTS + 图 + 视频 Key | 按 provider |

用户可读版：`README/说明/02-免费与收费能力.md`。

### 档位时机

1. **主题/标题确认之后、脚本关卡之前** 停下，展示上表，等用户明确选一档。  
2. 脚本关卡通过后若要改档：须用户明确说「升到中度 / 升到重度 / 改回轻度」；Agent 再检查前置并更新 checkpoint。  
3. **不要**在用户未选时默认重度；模糊时先建议轻度跑通。

### 前置检查（选档前内部核对，缺则说明如何补）

- 轻度：`verify_ready`  
- 中度：+ stock MCP 能启动 + 至少一个 `PEXELS_API_KEY` / `PIXABAY_API_KEY` + Skill `openmontage-providers-stock`  
- 重度：+ 三个付费 MCP 能启动 + 对应 Key 已填 + 执行 Skill 已启用  
- 中度要升 TTS：+ TTS MCP + Key + `openmontage-providers-tts`  

缺前置 → 不硬升档；可退回上一档或先走 Skill03 / 05 补配置。

## Hard protocol（主流程）

### 0–1. 主题与档位

1. 确认主题/标题（人审；`approval_text` 用用户原话）。  
2. ★ **档位选择关卡**：讲清轻/中/重 → 用户选定 → 再继续。  
3. `produce_init_project`（`pipeline_type=animated-explainer`）。  
4. ★ 写入档位（优先专用工具）：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",   # 可空：按档位默认
  tts_source=""       # 可空：按档位默认；中度改付费 TTS 时再写成 "paid"
)
```

默认映射：

| tier | visual_source | tts_source |
|------|---------------|------------|
| light | template | piper |
| medium | stock | piper |
| heavy | paid_gen | paid |

也可用 `produce_write_checkpoint` 的 `artifacts_json` 带同名字段，会**同步写进** `project.json`。  
之后用 `produce_read_state` → 顶层 `production_profile` 读取（权威在 marker）。

### 2. 脚本等人审关卡（共用）

`produce_write_checkpoint` / `produce_approve_checkpoint`：必须带用户原话 `approval_text`，禁止编造。

### 3. 语音分支

**轻度 / 中度（默认）：**

1. `produce_tts_preflight`  
2. `produce_tts_sample` → 用户试听 OK  
3. `produce_tts_generate(..., confirm_sample_ok=true)`  

**中度可选升级（仅当用户显式要云端语音）：**

- 再问一次：「继续用 Piper / 改用云端 TTS？」  
- 选云端 → 交接 `openmontage-providers-tts`（`list → dry_run → sample(confirm_estimate) → generate(confirm + confirm_sample_ok)`）  
- **禁止**因「已配置 Key」就自动走付费  

**重度：**

- 必须付费 TTS（同上 providers-tts 门禁）；不要默认 Piper（除非用户明确降级）。

产出音频路径记入项目沙箱，供字幕与 compose。

### 4. 画面分支

**轻度：** 不调 stock / 付费图视频；compose 用模板/字幕轨（现有最小路径）。

**中度：** 交接 `openmontage-providers-stock`

1. `list_stock_sources`  
2. 按镜头 `stock_search(source, media_kind, query)` → 展示候选 → 用户确认  
3. `stock_download(..., confirm=true, project_id=<id>, scene_id=..., asset_id=...)`  
   - 下载到项目沙箱，并**自动 upsert** `artifacts/asset_manifest.json`  
4. `produce_read_asset_manifest(project_id)` 取 `asset_manifest_json`  
5. 编 `edit_decisions_json`（镜头引用 `asset_id` / `scene_id`）  
6. `produce_compose_preflight` → `produce_compose_start`（用上一步的 manifest JSON）  

失败不静默换源；让用户改 query 或换 pexels/pixabay。

**重度：** 按镜头需要交接

- `openmontage-providers-image`：dry_run → sample → generate  
- `openmontage-providers-video`：dry_run → sample → generate  

产物路径写入 `asset_manifest_json`。本 Skill **不**直接调付费工具；只编排与等人审。

### 5–7. 字幕与合成

**字幕 / 文稿 / BGM：** Skill `openmontage-bootstrap-captions-music`（B+C）  
文稿→`segment_copy_to_subtitles`；BGM→`import/register_music`→`produce_build_compose_inputs`→交回 `compose_*`。  
可选：`produce_mix_narration_and_music`（需 ffmpeg）。详见 `README/说明/03-字幕与配乐.md`。

也可直接：

1. `produce_generate_subtitles`（已有分段时）  
2. `produce_compose_preflight` → `produce_compose_start` → 轮询 `produce_job_status`  
3. 交付 `renders/final.mp4`；可用 `produce_probe_media` 抽检  

**工具失败时（强制）：** 先读 Skill `openmontage-bootstrap-error-handling`，调用  
`error_capture_context` → `error_plan_recovery` → `error_apply_recovery`（安全动作），再重试。  
高危覆盖/付费须 `confirm=true`。详见 `README/错误处理/`。

有 explainer stage director 时可读 `skills/pipelines/explainer/`。

## 与其它 Skill 的关系

| Skill | 关系 |
|-------|------|
| setup (01) | 前置环境 |
| captions-music | 文稿→字幕；BGM 登记与 compose 输入打包（可选 ffmpeg 混音） |
| error-handling | 工具失败：capture → plan → **apply**（≤3；高危须确认） |
| providers (03) | 补 Key；重度/中度付费 TTS 前可先走 03 |
| providers-stock | 中度画面 |
| providers-tts/image/video | 中度可选 TTS；重度全套 |
| installer | 不负责出片，只配 MCP/Skill |

## Related

- `README/说明/02-免费与收费能力.md`  
- `openmontage-animated-explainer` / `openmontage-production-contract`（若已加载）
