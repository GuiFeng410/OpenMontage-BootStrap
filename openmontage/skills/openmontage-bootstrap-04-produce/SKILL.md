---
name: openmontage-bootstrap-04-produce
description: >-
  BootStrap produce flow (04): after theme/usercheck confirmation, present
  light/medium/heavy production tiers, then run facade produce_* with optional
  stock and paid handoffs.
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

# OpenMontage BootStrap Produce（04）

## Scope

统一入口出片：门面 `produce_*` + 按档位交接 Stock / 付费 providers。  
交付物：`<PROJECTS>/<project_id>/renders/final.mp4`。

**素材按项目隔离**（不是全局共享库）：

```text
<PROJECTS>/<project_id>/assets/
  images/  video/  music/  audio/  copy/  subs/  stock/
```

`produce_init_project` / `produce_ensure_captions_music_dirs` 会预建上述目录。  
用户自带图/音/视频放入**当前** `project_id` 对应目录；新项目不会自动继承旧项目素材。

**不做：** 代用户选档、伪造 `approval_text`、静默调付费 API、静默换 provider / 视频渠道。

## 遵守 openmontage-bootstrap-03-usercheck 锁定（强制）

若简报阶段已确认并写入（`production_profile` 或项目 artifacts / 简报 JSON）：

| 字段 | produce 必须 |
|------|----------------|
| `ai_video=disabled` 或不存在 | **禁止**调用付费 AI 视频生成 |
| `ai_video=enabled` + `video_channel` / `video_model` | **只使用**该渠道与模型；禁止改用其它视频供应商 |
| `ai_plan`（表 ③） | 按已确认分段的文案 / 提示词约束生成与拼接；不得擅自改段数或重写提示词而不再问用户 |

**同渠限流：** 可先并行，遇 429/402/可重试错误后转**串行补片**；已有合格片段跳过。  
**跨渠：** 即使另一渠道已填 Key，也**禁止静默切换**；须向用户提案并获同意，再更新简报锁定字段 / 决策记录后继续。

缺少应有的简报锁定（启用了 AI 视频却无 channel/model，或应有 `ai_plan` 却无）→ **先回到 `openmontage-bootstrap-03-usercheck`**，不要在 produce 内临时编造规划。

## Required MCP

- 必有：`openmontage-bootstrap`（`produce_*`）  
- 中度另需：`openmontage-providers-stock`  
- 重度另需：`openmontage-providers-tts` / `image` / `video`  
- 中度可选付费 TTS：同上 TTS MCP  

前提：`openmontage-bootstrap-02-setup` 的 `verify_ready` 通过（或等价 doctor ready）。  
**模糊需求：** 若用户尚未确认成片简报，先读并执行 Skill **`openmontage-bootstrap-03-usercheck`**（表 A → 如需则表 ② 渠道/模型 → 如需则表 ③ AI 规划表），确认后再进入本 Skill 主流程。

## 档位定义（主题确认后必讲清并让用户选）

| 档位 | 画面 | 语音 | Key | 费用 |
|------|------|------|-----|------|
| **轻度** | 模板/字幕为主，无 Stock、无 AI 生图生视频 | **Edge-TTS 男声**（零 Key、需联网；默认 `zh-CN-YunyangNeural`） | 无 | $0 |
| **中度** | Stock（Pexels/Pixabay）搜图/搜视频 → 下载进沙箱 | **默认同上 Edge 男声**；若已配 TTS Key，可**手动**改付费云端 TTS | 至少一个免费 Stock Key | Stock $0 + 可选付费 TTS |
| **重度** | 付费 AI 生图 + 付费 AI 生视频 | **付费高级 TTS**（不默认 Edge/Piper） | TTS + 图 + 视频 Key | 按 provider |

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

缺前置 → 不硬升档；可退回上一档或先走 `06-providers` / providers 执行 Skill 补配置。

## Hard protocol（主流程）

### 0–1. 主题与档位

0. 若需求仍模糊、无已确认简报 → **先交接 `openmontage-bootstrap-03-usercheck`**（表 A；启用 AI 视频时还须表 ②/③），回来后再继续。遵守上一节「锁定」规则。  
1. 确认主题/标题（人审；`approval_text` 用用户原话；若简报已确认可沿用）。  
2. ★ **档位选择关卡**：若简报已写入档位可复查确认；否则讲清轻/中/重 → 用户选定 → 再继续。  
3. `produce_init_project`（若简报阶段未建；`pipeline_type=animated-explainer`）→ 预建 `assets/*`。  
4. ★ 写入档位（优先专用工具；简报已写则可跳过或核对）：

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
| light | template | edge_tts |
| medium | stock | edge_tts |
| heavy | paid_gen | paid |

也可用 `produce_write_checkpoint` 的 `artifacts_json` 带同名字段，会**同步写进** `project.json`。  
之后用 `produce_read_state` → 顶层 `production_profile` 读取（权威在 marker）。

### 2. 脚本等人审关卡（共用）

`produce_write_checkpoint` / `produce_approve_checkpoint`：必须带用户原话 `approval_text`，禁止编造。

### 3. 语音分支

**轻度 / 中度（默认 · 中文旁白）：Edge-TTS 男声**

| 项 | 约定 |
|----|------|
| 音色 | `zh-CN-YunyangNeural`（男）；rate 建议 `-18%`，pitch 建议 `-2Hz` |
| 依赖 | `requirements.txt` 的 `edge-tts`；**需联网**（Microsoft Edge TTS） |
| 对齐 | **按字幕 SRT 每条 cue 合成并拟合到 cue 时间窗**，再拼接旁白轨 |
| 禁止 | 整段一次合成后用静音「垫满」镜头（Piper 试片踩过的坑） |
| 参考脚本 | `scripts/_edge_tts_preview_prompt_explainer.py`（按 cue 合成→fit→concat） |
| 离线回退 | 无网 / edge-tts 失败 → 再问用户是否改用 Piper（门面 `produce_tts_*`） |

门面 `produce_tts_*` 若仍绑定 Piper：中文讲解片**优先用 Edge CLI/脚本**完成旁白；仅在用户选离线或 Edge 不可用时走门面 Piper。

流程：

1. 确认 SRT（或文稿切分后的字幕）已定稿  
2. Edge：按 cue 生成样片 → 用户试听 OK  
3. 全片旁白轨 → 写入 `assets/audio/`，再混流/烧字幕  

**中度可选升级（仅当用户显式要付费云端语音）：**

- 再问一次：「继续用 Edge 男声 / 改用付费云端 TTS / 离线 Piper？」  
- 选付费 → 交接 `openmontage-providers-tts`（`list → dry_run → sample(confirm_estimate) → generate(confirm + confirm_sample_ok)`）  
- **禁止**因「已配置 Key」就自动走付费  

**重度：**

- 必须付费 TTS（同上 providers-tts 门禁）；不要默认 Edge/Piper（除非用户明确降级）。

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

**字幕 / 文稿 / BGM：** Skill `openmontage-bootstrap-05-captions-music`（B+C）  
文稿→`segment_copy_to_subtitles`；BGM→`import/register_music`→`produce_build_compose_inputs`→交回 `compose_*`。  
可选：`produce_mix_narration_and_music`（需 ffmpeg）；E01 静音 BGM 确认后可用 `produce_synthesize_bgm(confirm=true)`。  
详见 `README/说明/03-字幕与配乐.md`。

也可直接：

1. `produce_generate_subtitles`（已有分段时）  
2. `produce_compose_preflight` → `produce_compose_start` → 轮询 `produce_job_status`  
3. 交付 `renders/final.mp4`；可用 `produce_probe_media` 抽检  

**工具失败时（强制）：** 先读 Skill `openmontage-bootstrap-07-error-handling`（阶段 3），调用  
`error_capture_context` → `error_plan_recovery` → `error_apply_recovery`（安全动作），再重试。  
高危覆盖/付费/换 BGM 须 `confirm=true`（如 `action_ids="replace_bgm"`）。详见 `README/错误处理/`。

有 explainer stage director 时可读 `skills/pipelines/explainer/`。

## 与其它 Skill 的关系

| Skill | 关系 |
|-------|------|
| setup (01) | 前置环境 |
| openmontage-bootstrap-03-usercheck | 模糊需求：成片简报表确认后再进入本 Skill |
| captions-music | 文稿→字幕；BGM 登记与 compose 输入打包（可选 ffmpeg 混音） |
| error-handling | 工具失败：capture → plan → **apply**（≤3；高危须确认） |
| providers (03) | 补 Key；重度/中度付费 TTS 前可先走 03 |
| providers-stock | 中度画面 |
| providers-tts/image/video | 中度可选 TTS；重度全套 |
| installer | 不负责出片，只配 MCP/Skill |

## Related

- `README/说明/02-免费与收费能力.md`  
- `openmontage-animated-explainer` / `openmontage-production-contract`（若已加载）
