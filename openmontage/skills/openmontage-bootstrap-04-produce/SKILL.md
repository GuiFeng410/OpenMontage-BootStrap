---
name: openmontage-bootstrap-04-produce
description: >-
  BootStrap produce (04): after 03-usercheck locks theme/tier/table-2/video_plan,
  run facade produce_* by locked tier. Does not re-present tier picker; tier
  changes return to 03. Narration/BGM optional and deferred — must not block
  picture/video deliverable.
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

# 长商品视频执行引用

当当前项目是商品视频且 `duration_seconds >= 30` 时，执行过程中必须遵守：

`openmontage/skills/openmontage-bootstrap-03-usercheck/references/commercial-video-30s-review.md`

该规则要求按 3-4 个 beat 分批展示预览，AI 先做初审，用户反馈后先生成修改清单，并在用户回复 `1` 同意后才执行修改。默认只修改被指出的 beat；衔接问题才扩大到相邻片段。所有批次确认后，才能进行最终 Remotion 时间线合成。

本 Skill 不得在执行中自行改变已锁定的 provider、模型、视频计划或 render runtime。若用户改变生产方向，应返回 `03-usercheck` 重新确认。

# OpenMontage BootStrap Produce（04）

## Scope

统一入口出片：门面 `produce_*` + 按 **03 已锁定** 的档位执行 Stock / 付费视频等。  
交付物：`<PROJECTS>/<project_id>/renders/final.mp4`（本阶段以**画面/视频**为主；旁白与 BGM **可后置**，不挡出片）。

**素材按项目隔离**（不是全局共享库）：

```text
<PROJECTS>/<project_id>/assets/
  images/  video/  music/  audio/  copy/  subs/  stock/
```

`produce_init_project` / `produce_ensure_captions_music_dirs` 会预建上述目录。  
用户自带图/音/视频放入**当前** `project_id` 对应目录；新项目不会自动继承旧项目素材。

**不做：** 代用户**首次**选档（选型在 03）；伪造 `approval_text`；静默调付费 API；静默换 provider / 视频渠道；无 03 简报时在本 Skill 内编造 `video_plan`。

## 遵守 openmontage-bootstrap-03-usercheck 锁定（强制）

若简报阶段已确认并写入（`production_profile` 或项目 artifacts / 简报 JSON）：

| 字段 | produce 必须 |
|------|----------------|
| `production_tier` | 按 `light` / `medium` / `heavy` 执行；**不重出**轻中重选档大表 |
| `light_presentation`（轻度） | 按 `still` / `image_carousel` / `motion_text` / `remotion` / `hyperframes` 编排画面 |
| `medium_source`（中度） | `stock` 才走 Stock 下载；`user_assets` 只用项目内素材；无 Stock Key 禁止走 stock |
| `ai_video=disabled` 或不存在 | **禁止**调用付费 AI 视频生成 |
| `ai_video=enabled` + `video_channel` / `video_model` | **只使用**该渠道与模型；禁止改用其它视频供应商 |
| `video_plan`（表 3） | 按已确认分段的画面/文案要点生成与拼接；不得擅自改段数或重写规划而不再问用户。商品片：若 `gap_fill=i2i` 且补图未完成 → **先补图再 I2V**；某段无 `ref_image` 或缺口未关闭 → **不烧该段**，回 usercheck。重点段优先重试与打磨（见 `03-usercheck/references/product-prompt-template.md`） |

**TokenHub（`video_channel=tokenhub`）：** 走 `tools._tokenhub.generate_video`（`hy-video-1.5`）。约 720p、默认并发 1、**无自定义时长**——长片用多段 I2V/T2V 再 ffmpeg 拼接。本地参考图必须 `image.base64`（纯 base64）；公网图才用 `image.url`。YT 系列仍 planned，禁止当可烧。试片脚本：`python scripts/_run_tokenhub_shop_wear_10s.py`（已有成片默认 skip）。

**同渠限流：** 可先并行，遇 429/402/可重试错误后转**串行补片**；已有合格片段跳过。TokenHub 按串行规划。  
**跨渠：** 即使另一渠道已填 Key，也**禁止静默切换**；须向用户提案并获同意，再更新简报锁定字段后继续——通常应**退回 03** 重锁表 2.3 / 表 3。

缺少应有的简报锁定（无档位、无表 3 `video_plan`，或重度启用了 AI 视频却无 channel/model）→ **先回到 `openmontage-bootstrap-03-usercheck`**，不要在 produce 内临时编造规划。

## Required MCP

- 必有：`openmontage-bootstrap`（`produce_*`）  
- 中度且 `medium_source=stock`：另需 `openmontage-providers-stock` + Key  
- 重度：对应视频路径（Agnes 工具 / TokenHub / 或 `openmontage-providers-video` 等已接线通道）+ 已填 Key  
- 付费 TTS / 生图：仅当用户**明确要做**旁白或补图时再要求对应 MCP（**不因未配旁白而阻塞画面出片**）

前提：`openmontage-bootstrap-02-setup` 的 `verify_ready` 通过（或等价 doctor ready）。  
**模糊需求 / 无简报：** 先读并执行 **`openmontage-bootstrap-03-usercheck`**（表 1 → 表 2 → 表 3），确认后再进入本 Skill。

## 档位执行摘要（只读锁定 · 不在此选型）

| 档位 | 画面怎么来 | 旁白 / BGM（本阶段） |
|------|------------|----------------------|
| **轻度** | 模板/静图/轮播/动字/Remotion/HyperFrames（看 `light_presentation`）；无 Stock、无付费 AI 视频 | **可选后置**；不挡出片 |
| **中度** | Stock 或自带（看 `medium_source`） | **可选后置**；不挡出片 |
| **重度** | 付费 AI 视频（锁定渠模）+ `video_plan` 分段 | **可选后置**；付费 TTS **非**出片前置条件 |

用户可读能力说明：`README/说明/02-免费与收费能力.md`（若与本 Skill「旁白后置」冲突，**以本 Skill 为准**）。

### 开场锁定复查（替代旧「选档关卡」）

进入本 Skill 时：

1. 若无 03 锁定 → 交接 03。  
2. 若有锁定 → **一句复查**，例如：`当前锁定：重度 / Agnes / hy… / 三段 video_plan，确认开始出片？`  
3. **不要**再完整展示轻/中/重选型大表。

### 改档回流（强制）

用户明确说「改档 / 升到中度 / 升到重度 / 改回轻度」：

1. **禁止**在 04 内静默改 `production_tier` 后继续烧。  
2. 交接回 **`03-usercheck`**：重走表 1（至少新档位）→ 表 2 → 表 3。  
3. 新简报写入后再回到 04。

## Hard protocol（主流程）

### 0–1. 简报与项目

0. 无已确认简报 → **先交接 03**（表 1→2→3）。  
1. 锁定复查（见上）；`approval_text` 用用户原话。  
2. `produce_init_project`（若简报阶段未建；`pipeline_type=animated-explainer`）→ 预建 `assets/*`。  
3. 核对 / 写入 `production_profile`（简报已写则可跳过或核对）：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",   # 可空：按锁定与档位默认
  tts_source=""       # 旁白后置时可空；用户明确要旁白后再写 edge_tts|paid|…
)
```

默认映射（无更细锁定时）：

| tier | visual_source | tts_source（可后置） |
|------|---------------|----------------------|
| light | template（或按 light_presentation） | （暂缓） |
| medium | stock 或 user | （暂缓） |
| heavy | paid_gen | （暂缓） |

也可用 `produce_write_checkpoint` 的 `artifacts_json` 带同名字段。  
用 `produce_read_state` → 顶层 `production_profile` 读取。

### 2. 脚本等人审关卡（共用）

`produce_write_checkpoint` / `produce_approve_checkpoint`：必须带用户原话 `approval_text`，禁止编造。  
分段以简报 **`video_plan`** 为准，不要另起一套冲突规划。

### 3. 语音分支（可选 · 后置）

**默认：** 先完成画面/视频与 compose；旁白与 BGM **不**作为出片硬前置。旁白**默认推荐** Edge-TTS 男声（可后置到画面通过后再做）。

当用户**明确要求**旁白（或画面已定要加旁白）时：

**轻度 / 中度（中文旁白默认推荐）：Edge-TTS 男声**

| 项 | 约定 |
|----|------|
| 音色 | `zh-CN-YunyangNeural`（男）；rate 建议 `-18%`，pitch 建议 `-2Hz` |
| 依赖 | `edge-tts`；**需联网** |
| 对齐 | **按字幕 SRT 每条 cue** 合成并拟合到 cue 时间窗 |
| 禁止 | 整段一次合成后用静音「垫满」镜头 |
| 参考 | `scripts/_edge_tts_preview_prompt_explainer.py` |
| 离线回退 | 无网 / Edge 失败 → 再问是否 Piper |

**中度可选付费 TTS：** 仅当用户显式要云端语音 → `openmontage-providers-tts` 门禁；禁止因「已有 Key」自动付费。

**重度：** 不强制先做付费 TTS。用户要旁白时再走 providers-tts 或协商 Edge/降级；**禁止**因未配付费 TTS 拒绝出画面成片。

### 4. 画面分支

**轻度：** 不调 stock / 付费 AI 视频。按 `light_presentation`：

- `still` / `image_carousel` / `motion_text` → 模板与字幕/图卡路径  
- `remotion` → Remotion/`Explainer`（图表+对比等）；首次 Demo 参照 `03-usercheck/references/first-run-demo.md` §4 与 `projects/remotion-light-showcase/`  
- `hyperframes` → HyperFrames HTML/GSAP（品牌渐显等）；参照 `first-run-demo.md` §5 与 `projects/hyperframes-jewelry-demo/`；`render_runtime` 须为 hyperframes 且本机可用，否则回 03 改路径，禁止静默换 Remotion

**中度：**

- `medium_source=user_assets` → 使用项目 `assets/` 内素材编排  
- `medium_source=stock` → 交接 `openmontage-providers-stock`：

1. `list_stock_sources`  
2. 按镜头 `stock_search` → 展示候选 → 用户确认  
3. `stock_download(..., confirm=true, project_id=..., scene_id=..., asset_id=...)`  
4. `produce_read_asset_manifest` → 编 `edit_decisions_json`  
5. `produce_compose_preflight` → `produce_compose_start`  

失败不静默换源。无 Key 却锁了 stock → 回 03 改 `medium_source` 或补 Key。

**重度：** 严格按 `video_channel` / `video_model` / `video_plan` 分段生成（Agnes / TokenHub / 已接线的 providers-video 等）。  
产物写入 `asset_manifest`。本 Skill **编排与人审**；禁止换渠硬烧。重度商品须已满足 03 侧 `product-prompt-template` 闸门。

### 5–7. 字幕、BGM 与合成

**字幕 / BGM：** Skill `openmontage-bootstrap-05-captions-music` — **可后置**。  
用户只要画面成片时：可先 `produce_compose_*` 出片，再回头补字幕/BGM。  
需要文稿→字幕、BGM 登记、混音时再走 05。详见 `README/说明/03-字幕与配乐.md`。

也可直接：

1. `produce_generate_subtitles`（已有分段时）  
2. `produce_compose_preflight` → `produce_compose_start` → 轮询 `produce_job_status`  
3. 交付 `renders/final.mp4`；可用 `produce_probe_media` 抽检  

**工具失败时（强制）：** 先读 `openmontage-bootstrap-07-error-handling`，  
`error_capture_context` → `error_plan_recovery` → `error_apply_recovery`，再重试。  
高危覆盖/付费/换 BGM 须 `confirm=true`。

有 explainer stage director 时可读 `skills/pipelines/explainer/`。

## 与其它 Skill 的关系

| Skill | 关系 |
|-------|------|
| setup | 前置环境 |
| openmontage-bootstrap-03-usercheck | 选型与 `video_plan`；改档必须退回 |
| captions-music | 字幕 / BGM（后置可选） |
| error-handling | 工具失败修复 |
| providers | 补 Key |
| providers-stock | 中度 stock |
| providers-tts/image/video | 按需；不挡「先出画面」 |
| installer | 只配 MCP/Skill |

## 商品片执行前素材复查

进入商品片执行前，读取 `asset_requirements` 和 `video_plan`，并逐段核对：

1. 是否存在商品主图（`product_hero`）；
2. 当前图片数是否达到该时长的最低数量；
3. 是否已列出缺少的图片类型；
4. 每个重点段是否有参考图片（`ref_image`）；
5. 缺图处理（`gap_fill`）为图生图时，补图是否已经完成并经过检查；
6. 素材状态是否为“就绪”，或用户已经确认风险的“降级继续”。

执行顺序必须是：

```text
素材复查 → 用户已确认的缺图补充 → 检查补充图片 → I2V/T2V → 拼接出片
```

没有商品主图、状态为“等待用户选择”、或用户尚未确认降级风险时，**禁止**在本 Skill 内自行猜测商品、静默改成概念片或直接烧视频；应退回 `openmontage-bootstrap-03-usercheck`。

`asset_classes`、`ref_image`、`gap_fill` 在执行层继续作为机器字段读取，面向用户的素材类型、参考图片、缺图处理和状态说明统一使用中文。

## Related

- `README/说明/02-免费与收费能力.md`  
- `openmontage-animated-explainer` / `openmontage-production-contract`（若已加载）
