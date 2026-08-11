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

当当前项目是商品视频且 `duration_seconds >= 15` 时，执行过程中必须遵守：

`openmontage/skills/openmontage-bootstrap-03-usercheck/references/commercial-video-15s-review.md`

- **普通**：方案→试片→初稿/问题片段；不强制逐 beat 分批卡。  
- **专业**：按 3–4 个 beat 分批展示预览，AI 先做初审，用户反馈后先生成修改清单，并在用户回复 `1` 同意后才执行修改。默认只修改被指出的 beat；衔接问题才扩大到相邻片段。所有批次确认后，才能进行最终 Remotion 时间线合成。  
- **比例**：遵守简报 `motion_mix` 作为推荐目标（软约束）；审查改方式后允许偏离。  
- **失败**：AI 段重试用尽后再问用户，说明可能原因（网络不稳、余额不足等），禁止未询问就静默整段改运镜。

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

### 商品片只读看板交接（强制）

商品片从 03 接收 `bootstrap-commercial` 的 `project_id` 和固定 Backlot 网址。进入 04 后：

1. 必须接收 03 初始化工具返回的实际 `project_id`。先调用 `produce_read_state` 核对管线，再运行 `python -m backlot open <project_id>`；主动把**同一网址**发给用户，不创建第二个看板项目。聊天须含：`你可以查看该网址了解详细信息：{URL}`。进入 04 后**禁止重新调用 produce_init_project**；缺少项目 ID、状态或完整简报时退回 03，不得猜测新建或续作。
2. 每进入试片 / 分段 / 初稿 / 合成 / 交付阶段并写完对应 checkpoint 后，聊天固定一句：`已进入第 N 阶段：{中文名}。请打开看板查看最新证据（若未自动更新请刷新页面）。`
3. 试片、专业批次、初稿和交付需要用户裁定时，先用 `produce_write_checkpoint` 写入当前阶段证据：`artifacts_json` 带阶段产物，`metadata_json` 带当前唯一决策、选项、推荐、回复示例和 `partial_progress`，`cost_snapshot_json` 带累计费用。
4. 网页可用时，完整审查卡、候选、抽帧、费用明细放网页；聊天只发“网址或阶段句 + 当前一个问题 + 推荐 + 回复示例”。网页不可用时退回完整 Grill 卡，流程继续。
5. 用户在聊天回复后，先 `produce_append_decision` 保存用户原话，再 `produce_approve_checkpoint`；审批调用默认合并当前 checkpoint，禁止以空 artifacts 覆盖证据。
6. 网页始终只读。不得要求用户在网页点击审批，不得从页面静默进入下一批或付费调用。

### 阶段封板（强制 · 与 03 同协议）

进入下一阶段的聊天提示之前：

1. 本阶段产物写入 checkpoint（合并，勿残缺覆盖）并落盘 `artifacts/*.json`
2. 用户裁定类决定已 `produce_append_decision`
3. 聊天先发：「{阶段中文名}证据已写入看板，请刷新核对后再继续。」
4. 再发：「已进入第 N 阶段：…」

试片/分段/初稿/交付同理；禁止只聊天宣布进入下阶段而面板仍空或缺上阶段已确认内容。

### 七阶段证据写入契约（强制）

`bootstrap-commercial` 的 Backlot 只读取项目内 checkpoint 与 `artifacts/*.json`。每阶段封板前，必须写入下表对应的**完整对象**；不得仅写最终 `final.mp4` 代替中间证据。

**顺序硬门：** 只有严格前序阶段已为 `completed`，才可进入下一阶段。每个阶段必须先把 canonical artifact 和其中引用的项目内媒体路径实际物化、确认可读取，再写 `completed` 或 `awaiting_human`；不得先写状态后补文件。Backlot 若展示“未挂接媒体”，只是提示修复 artifact/媒体关联，**不是**合法阶段证据。

| 阶段 | 必写 artifact | Backlot 用户可见证据 |
|---|---|---|
| 方案确认 | `brief` / `asset_precheck` / `video_plan` / `segment_cards` | 已确认主题、渠模、素材预检、整体方案与分段规划 |
| 素材检查 | `asset_ledger` | 已确认素材角色、项目内路径与缺口处理 |
| 试片确认 | `sample_reel` | `path`、时长、状态与用户确认原话；路径应指向试片，不得指向终稿 |
| 分段制作 | `segment_cards` / `review_overview` | 每个 beat 的时间段、文案/镜头/提示词、`asset_path` 或 `ref`、实际片段路径；专业模式另写批次评审 |
| 初稿审查 | `full_draft_pro` | 初稿 `path`、`issue_segments`（beat + 时间 + 中文问题）、`modification_list`（有序中文修改项） |
| 合成终稿 | `final_review` | `output_path`、审查结论、`technical_probe`（时长、分辨率、帧率、音频、问题） |
| 交付确认 | `final_review` + `cost_log` + `decision_log` | 终稿路径、质量结论、累计费用、`category=delivery_signoff` 的用户原话与签收结果 |

- 不存在某项证据时，写明确的空数组或状态说明；禁止把整个 artifact 省略后声称阶段完成。
- `sample_reel.path`、各 beat 的片段路径、`full_draft_pro.path`、`final_review.output_path` 必须是项目内可访问相对路径。Backlot 会按当前阶段只显示对应媒体。
- 旧项目若有 `sample_gate`、`full_production` 等非七阶段 checkpoint，保留用于审计；不要继续写入，也不要把它们当作新的进度节点。

### 直接出片 / 快速模式 v1.0（执行）

用户只说“直接出片”时，禁止把它当审批证据；若尚无合法决定，退回 03 展示 `commercial-video-15s-review.md` §0.5 的单问题授权卡。启用前必须从最新 `decision_log` 读到 schema 合法的 `approval_policy`：固定 `subject="Commercial fast-track production"`、`selected="fast_track_v1"`、`user_approved=true` 与包含完整授权语义的用户原话。

1. `brief_locked` 完成后，可在 canonical `asset_ledger` 与素材媒体路径已物化、且前序完成的前提下自动完成 `assets_gate`，再进入 `sample_review`。
2. `sample_review` **必须停下**等待用户明确批准试片；快速模式授权原话不能替代试片裁定。
3. 试片通过后，逐项比对授权时已披露的 provider/model/runtime、预估单价、总成本区间、预算基线、质量目标、分辨率与实际候选/审查结果。全部无实质变化且无“需修改”，才可自动推进 `segment_build` 和 `draft_review`。
4. 正常在已披露预算基线与总成本区间内累计消费不算变化；但预估单价、总成本区间或预算基线改变，即使尚未越限也必须暂停。质量目标或分辨率变化、候选结果低于承诺、审查发现需修改，同样暂停。
5. 自动完成 `draft_review` 时，`full_draft_pro` 必须已物化；先按 §0.5 的 schema 示例追加可追溯的 `stage_review_decision`（引用 `approval_policy.decision_id`、记录渠模/费用/质量基线比对，`user_approved=true`，`user_response_text` 复用完整授权原话），并把两条 decision ID、固定 subject、`approval_source="fast_track_v1"` 和比对结果写入 checkpoint metadata。
6. 随后必须调用 `produce_approve_checkpoint(project_id, stage="draft_review", approval_text=<完整授权用户原话>, ...)`，保留 `full_draft_pro`、metadata 与费用快照；调用成功后才能自动进入 `final_compose`。只写 `completed`、只写 metadata 或只引用“直接出片”均无效。
7. provider/model/runtime 变化或第 4 条任一费用/质量变化发生时，立即暂停并一次只问一个问题；变更决定须按原 `category + subject` 追加，不得静默替换。
8. `delivery_signoff` 永远写 `awaiting_human` 并停下等待签收。

快速模式只减少中间打断，不得跳过证据物化、试片、项目 preflight、provider registry/MCP availability、费用闸、付费调用确认或最终签收。网页继续只读。

### 付费 AI 镜提示词：Skill 引用与面板递进（强制）

适用：商品片或重度、且该段将调用付费 I2V/T2V。纯 Remotion/本地运镜段跳过。

**写之前必须先读（按序）：**

1. `openmontage/skills/openmontage-seedance-prompt/SKILL.md`（契约 + 镜头结构）
2. 同目录 `references/seedance-prompt-skill.md`（完整写法）
3. `03-usercheck/references/commercial-prompt-lexicon.md`
4. `03-usercheck/references/product-prompt-template.md`（槽位）

**递进协议：**

```text
按上列 Skill 起草/改写提示词
→ 写入项目 artifacts / checkpoint（全文）
→ Backlot「分段制作」等证据区只读展示全文
→ 聊天只发：网址 + 当前镜/批问题 + 推荐 + 回复示例（禁止整段粘贴长 prompt）
→ 用户聊天确认后 produce_append_decision → 再烧或再改
```

- **专业**：改 prompt 或重试前，修改清单须先上屏再聊天确认（与 `commercial-video-15s-review.md` 一致）。  
- **普通**：试片/初稿关仍问过关与否；单镜 prompt 默认上屏备查，不强制每镜口头确认，除非用户要求或一致性重试涉及改写。  
- 渠模以 03 锁定为准；禁止因提示词 Skill 擅自换渠。

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
| `motion_mix` | 按推荐目标**大概**安排整片 AI 生成总秒数（±约 15%）；不按段数硬凑。审查中用户改 beat 方式后更新计划，**允许终稿偏离**；偏离只告知，不否决交付 |
| `budget_cny` | 实验 API 上限（¥1/3/5/8/12）。单笔 beat 计划费用 ≥¥5 → **提示即可**（不论累计）。触顶停烧仍走 B6 |

**TokenHub（`video_channel=tokenhub`）：** 走 `tools._tokenhub.generate_video`，按 `video_model` 分流：

| `video_model` | 路径 | 注意 |
|---------------|------|------|
| `hy-video-1.5`（默认） | 混元 `/api/video/*` | 约 720p、无自定义时长；本地参考图 `image.base64`；公网图 `image.url`；长片多段 + ffmpeg |
| `pixverse-video-v6.0` | Pixverse `/wand/pixverse/*` | 传 `duration`（简报 `video_duration_sec`，默认 5）、`quality`（`video_quality`，默认 `720p`）、`aspect_ratio`；I2V 用公网 `image_url`，或在当前项目已明确授权且 OSS 已配置时传项目内 `image_path`；T2V 无图；长片仍多段 + ffmpeg |

YT 系列仍 planned，禁止当可烧。试片：混元 `python scripts/_run_tokenhub_shop_wear_10s.py`；Pixverse `python scripts/_run_tokenhub_pixverse_smoke.py --mode t2v`（I2V 可加 `--image-url https://...`，或项目内 `--image-path ... --confirm-cloud-upload`）。

### 项目计划、Pixverse 与 OSS 预检（强制）

在最终锁定/恢复视频渠道前，以及**每次付费调用前**，调用只读 `produce_provider_preflight(project_id)`；它只读取已落盘的 `project.json`、`artifacts/brief.json`、`artifacts/video_plan.json` 与 `decision_log`，检查项目计划、Pixverse 模式/图源、OSS 配置和项目上传授权证据，不上传、不生成、不扣费。

- **边界：** 该工具不检查 `TOKENHUB_API_KEY` / `AGNES_API_KEY`，也不探测 provider 在线可用性。付费前仍须另查 provider registry / 对应 MCP availability、所需 Key 与费用闸。
- `ready=false`：停在当前 checkpoint 阶段，按项目证据 `blockers` / `missing_config_fields` / `next_action_zh` 修复；禁止开烧或静默换渠。
- `ready=true`：只表示项目计划/Pixverse/OSS/授权证据通过，不代表 Key 有效、provider 在线、费用获准、上传获准或人审闸已通过。
- Pixverse 只承担 **T2V/I2V**。T2I/I2I 商品补图改走 Agnes / Flux / DashScope / OpenAI / Kling / Google / Grok 等已配置 image provider；若该本地成图随后用于 Pixverse I2V，才进入 OSS 暂存链。
- Pixverse T2V、Pixverse 公网图 I2V、Agnes 均不需要 OSS；只有 Pixverse **当前项目本地图 I2V** 同时要求 OSS 配置和项目上传授权。
- 配置 OSS 后必须重启/刷新 MCP，再调用 preflight 复检 **OSS readiness**。另查 registry/MCP availability 后才恢复阻塞前的原 checkpoint 阶段；不重走表 1–3、不自动越级，也不因 OSS 已配置而自动上传。

**Pixverse 本地图硬门禁：**

1. 先读当前项目 `decision_log`；只接受最新 `category=asset_decision`、固定 `subject="Pixverse local image temporary OSS upload"`，且严格三项批准证据同时成立：`selected=approved`、`user_approved=true`、非空 `user_response_text`（用户原话）。
2. 调用 `tools._tokenhub.generate_video` 时必须同时传：
   - `image_path=<project>/assets/images/...`
   - `project_id=<当前项目>`
   - `user_authorized_upload=true`
3. 缺任一项即停止并回 03 确认；禁止把授权布尔值凭空设为 true。
4. signed URL 仅在内存中交给 Pixverse，禁止写入 checkpoint、decision、asset ledger、Backlot 或聊天。
5. 工具每次生成使用独立临时对象：成功或明确终态失败后尽量删除；轮询超时保留并写 `artifacts/oss_staging.json`，不阻断仍可能运行的 Pixverse 任务。

**同渠限流：** 可先并行，遇 429/402/可重试错误后转**串行补片**；已有合格片段跳过。TokenHub 按串行规划。  
**跨渠：** 即使另一渠道已填 Key，也**禁止静默切换**；须向用户提案并获同意，再更新简报锁定字段后继续——通常应**退回 03** 重锁表 2.3 / 表 3。

缺少应有的简报锁定（无档位、无表 3 `video_plan`，或重度启用了 AI 视频却无 channel/model）→ **先回到 `openmontage-bootstrap-03-usercheck`**，不要在 produce 内临时编造规划。

## Required MCP

- 必有：`openmontage-bootstrap`（`produce_*`）  
- 中度且 `medium_source=stock`：另需 `openmontage-providers-stock` + Key  
- 重度：对应视频路径（Agnes 工具 / TokenHub / 或 `openmontage-providers-video` 等已接线通道）+ 已填 Key  
- 付费 TTS / 生图：仅当用户**明确要做**旁白或补图时再要求对应 MCP（**不因未配旁白而阻塞画面出片**）；Pixverse 不属于生图 provider

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
2. 若有锁定 → **一句复查**，必须点出：档位 / 渠模（重度）/ **实验 API 预算（¥1|3|5|8|12，非售价）** / **画面比例 motion_mix** / 段数 / **评审模式（普通|专业）** / 候选模式（自适应|稳定双候选）。例如：  
   `当前锁定：重度 / Agnes / 实验预算¥8（非售价）/ 比例1:1（推荐）/ 普通评审 / 自适应候选 / 6 段 video_plan，确认开始出片？`  
3. **不要**再完整展示轻/中/重选型大表。  
4. 用户未确认「开始」前：**禁止**任何付费 API。

### 改档回流（强制）

用户明确说「改档 / 升到中度 / 升到重度 / 改回轻度」：

1. **禁止**在 04 内静默改 `production_tier` 后继续烧。  
2. 交接回 **`03-usercheck`**：重走表 1（至少新档位）→ 表 2 → 表 3。  
3. 新简报写入后再回到 04。

## P0 商品/重度出片闸门（冻结口径）

适用：商品宣传，或重度付费视频。轻/中非商品可跳过试片硬闸，但仍遵守费用闸（若已写预算）。

### B1 试片关（强制）

付费批量生成全长 **之前**，先完成 **10–15s 试片**，须同时包含：

1. 一段商品身份建立（静帧或微运镜即可）；  
2. 一段真实 AI 动态（Agnes 等已锁渠道）；  
3. 一段 Remotion（或已锁确定性）运镜/转场。

写入 `artifacts/sample_reel.json`（或等价），至少含：路径、时长、`approved`/`pending`、用户确认原文。  
**试片未通过 → 禁止**进入完整 60s 批量 Agnes。  
用户可选反馈：效果可以继续 / 商品不一致 / 动态太少 / 抖动或变形 / 节奏不合适。  
试片交付消息须含 **§0.3 费用卡**，并用 Grill 确认卡请用户裁定（是否过关 / 是否继续全长）。

### B2 自适应候选（默认）

| `candidate_mode` | 行为 |
|------------------|------|
| `adaptive`（默认） | 每关键 beat **1** 个候选 → 初审 → 不合格才条件重试（合计约 2 次） |
| `stable_dual` | 关键 beat 直接 2 候选（须简报显式开启） |

拒绝/失败候选仍计入首次达标成本；不得入正式时间线。  
**重试用尽**仍失败：须询问用户并说明可能原因（网络不稳、余额不足、限流、一致性未过等）；选项见 `commercial-video-15s-review.md` §11。**禁止**未询问就静默改运镜。

### B3 抽帧与预审

- 内部：用 `visual_qa` / `frame_sampler` 至少抽 **首、25%、50%、75%、尾**；异常点附近加帧。  
- 用户默认展示：首/中/尾三张代表帧；有异常再展开。  
- `review_mode=normal`：整片初稿 + AI 标问题段 → 只展开问题片段 → 修改清单确认。  
- `review_mode=pro`：可走 `commercial-video-15s-review.md` 总分批/逐 beat（≥15s 可选）。  
流程中可提示：「需要更细逐段审查可切换专业模式」。

### B4 动态指标（记录，非硬门槛）

成片/规划须记录：

- `true_video_seconds`：合格 AI 动态秒数  
- `meaningful_composed_motion_seconds`：含 Remotion 有效运镜  
- `motion_mix` / 相对推荐的偏离说明（若有）

有 `motion_mix` 时：以 mix 推导的 AI 秒数带为主（软）；`motion_target_band` 可作脚注参考。  

**禁止**仅因 AI 秒数未达推荐目标就宣称质量失败；硬门槛见 B7。

### B5 初稿合成

试片通过且素材齐后：按锁定时间线 Remotion 合成；文案/Logo 仅确定性层；仅在用户确认回退选项后，失败动态才改已批准静帧/运镜。交付 `renders/` 初稿（如 `final.mp4` 或带版本名）。

### B6 费用闸（强制）

1. 权威账本 = `CostTracker`（USD：estimate → reserve → reconcile）。  
2. 展示/熔断用 `produce_budget_cny_snapshot(project_id, spent_usd, reserved_usd, next_estimate_usd)`（CNY 展示层，**禁止**另起人民币平行账本）。  
3. 「首次达标成本」= 首个可接受版本前所有成功/失败/被拒付费尝试。  
4. `allow_paid_call=false` 时：**停烧**，向用户给出选项：回退确定性段 / 升实验档 / 降 AI 占比；禁止静默续烧。  
5. **单笔计划**（某个 beat）预计费用 **≥ ¥5**：向用户**提示即可**（看 snapshot 的 `single_call_tip`），**不论累计**；不因此单独强制停烧。  
6. 文案始终称 **实验 API 预算上限**，禁止称售价。五档：¥1 / ¥3 / ¥5 / ¥8 / ¥12。  
7. **用户可见累计费用卡（强制）**：试片完成、全长初稿、终稿（及专业模式每批结束后）必须按 `commercial-video-15s-review.md` §0.3 贴出「分项 + 合计 + 预算剩余」；禁止只报单笔或只报合计而不列分项。渠道称呼遵守 03「命名防混」（TokenHub=腾讯混元渠；TokenPlan=Agnes 档）。

### B7 最终裁定

交付前输出：

| 项 | 通过条件 |
|----|----------|
| H1 身份 | 相对锚点同一商品，无明显重构 |
| H2 结构 | 无断裂/融化/换形 |
| H3 播放与节奏 | 流畅可播；动态不单调（Remotion 有效运镜可计入观感） |

附：动态秒数摘要 + **§0.3 费用卡**（USD 账本 + CNY 展示分项合计）。
未通过 → **不得**宣称达标。

试片/初稿请用户裁定时，使用 03 Skill 的 **Grill 确认卡**信息结构。商品片只读网页可用时，完整结构放网页，聊天只保留网址、当前问题、推荐和示例回复；网页不可用时才在聊天展开完整卡。

## Hard protocol（主流程）

### 0–1. 简报与项目

0. 无已确认简报 → **先交接 03**（表 1→2→3）。  
1. 锁定复查（见上）；`approval_text` 用用户原话。  
2. 复用 03 返回的项目与网址，禁止重新初始化。商品片固定 `pipeline_type=bootstrap-commercial`。若简报阶段未建项目，先交回 03 以 `mode=create_new` 或经用户明确确认后的 `mode=resume` 初始化。
3. 核对 / 写入 `production_profile`（简报已写则可跳过或核对）：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",
  tts_source="",
  api_budget_tier="standard",
  budget_cny="8",
  review_mode="normal",
  candidate_mode="adaptive",
  motion_target_band="60s_cost_ref",
  motion_mix="1:1",
  motion_mix_source="default_recommend",
  duration_seconds="30"
)
```

缺 `api_budget_tier`/`budget_cny` 的商品或重度简报：按默认 **standard / 8** 补写后再开烧，并口头告知用户「实验 API 预算默认 ¥8（非售价）」。  
缺 `review_mode` → 默认 `normal`；缺 `candidate_mode` → 默认 `adaptive`。  
缺 `motion_mix` 且本任务应有比例卡 → 默认 `1:1` / `default_recommend`，并在复查中念出。

也可用 `produce_write_checkpoint` 的 `artifacts_json` 带同名字段。  
用 `produce_read_state` → 顶层 `production_profile` 读取。  
付费前先调用 `produce_provider_preflight(project_id)` 核对项目/Pixverse/OSS/授权证据，再检查 provider registry / 对应 MCP availability 与所需 Key，最后调用 `produce_budget_cny_snapshot` 做费用闸；任一不允许时停止。

### 2. 脚本等人审关卡（共用）

`produce_write_checkpoint`：商品片必须按需传 `metadata_json` / `cost_snapshot_json`，让网页获得进度、当前决策和累计费用。
`produce_approve_checkpoint`：必须带用户原话 `approval_text`，禁止编造；默认保留当前 checkpoint 的 artifacts、metadata 与费用。决定同时用 `produce_append_decision` 追加到审计记录。
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
执行顺序（商品/重度）：

```text
开烧确认 → 试片关(B1) →（通过后）按 beat 自适应候选生成(B2)
→ 抽帧预审(B3) → 费用闸贯穿(B6) → 初稿合成(B5) → 最终裁定(B7)
```

普通评审不强制用户确认每一个 beat；专业模式才启用完整分批逐段卡（见 `commercial-video-15s-review.md` §0）。

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

进入商品片执行前，读取 `asset_requirements`、`asset_ledger`（若有）和 `video_plan`，并逐段核对：

1. 是否存在商品主图（`product_hero`）；
2. 当前图片数是否达到该时长的最低数量；
3. 是否已列出缺少的图片类型；
4. 每个重点段是否有参考图片（`ref_image`）；
5. 缺图处理（`gap_fill`）为图生图时，是否已由配置可用的 image provider 完成并经过检查（Pixverse 只做 T2V/I2V）；
6. 素材状态是否为“就绪”，或用户已经确认风险的“降级继续”。

若缺少已确认的 `asset_precheck` / 用户分类确认（商品片），**退回** `03-usercheck` 走 `references/asset-preprocess-gate.md`，禁止在本 Skill 内猜类或静默补图。

写付费 AI 动态段提示词时，**必须先读** `openmontage-seedance-prompt`，全文写入面板证据，聊天只摘要确认（见 04「付费 AI 镜提示词」节）。再读：

- `commercial-prompt-lexicon.md`
- `product-prompt-template.md`
- `openmontage-seedance-prompt/references/seedance-prompt-skill.md`

Remotion / HyperFrames 纯本地运镜段可不读 seedance Skill。渠模以 03 锁定为准，禁止因提示词 Skill 擅自改渠。

执行顺序必须是：

```text
素材复查 → 用户已确认的缺图补充 → 检查补充图片 → 试片关 → I2V/T2V（自适应候选）→ 初稿合成 → 裁定
```

没有商品主图、状态为“等待用户选择”、或用户尚未确认降级风险时，**禁止**在本 Skill 内自行猜测商品、静默改成概念片或直接烧视频；应退回 `openmontage-bootstrap-03-usercheck`。

`asset_classes`、`ref_image`、`gap_fill` 在执行层继续作为机器字段读取，面向用户的素材类型、参考图片、缺图处理和状态说明统一使用中文。

## Related

- `README/说明/02-免费与收费能力.md`  
- `openmontage-animated-explainer` / `openmontage-production-contract`（若已加载）
