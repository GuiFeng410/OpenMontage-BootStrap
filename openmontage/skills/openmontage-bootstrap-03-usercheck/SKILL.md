---
name: openmontage-bootstrap-03-usercheck
description: >-
  BootStrap brief before produce: commercial maps to bootstrap-commercial
  stages (brief_locked / assets_gate); first-time three-point card; then
  theme/tier → tier branch → video_plan (legacy Tables 1–3, flexible labels).
  Writes production_profile + artifacts, hands off to produce. Narration deferred.
metadata:
  openclaw:
    requires:
      env:
        - OPENMONTAGE_PROJECTS_DIR
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
      - name: OPENMONTAGE_P1_ALLOW_WRITES
        required: false
    os:
      - win32
      - darwin
      - linux
    emoji: "📋"
---

# 15 秒及以上商品视频路由

当视频用途属于商品宣传、电商商品展示或佩戴演示，且 `duration_seconds >= 15` 时，必须读取并执行：

`references/commercial-video-15s-review.md`

该参考文档规定：默认**普通评审**（方案→试片→初稿/问题片段）；**专业模式**才强制总览表与 3–4 beat 分批逐段卡（≥15s **须显式请用户选择**，不强制专业，但禁止静默不告知）。另含画面构成比例（运镜:AI，软约束）、累计 API 费用卡、三状态、修改清单确认门，以及 AI 段重试用尽后再询问用户的回退规则。用户决策消息统一用本 Skill「Grill 确认卡」。

本路由不替代当前 03 -> 04 主链，也不改变已经确认的 provider、模型或 render runtime。它只增加商品视频的展示、暂停、修改和用户确认方式。

判断条件不明确时先询问用户，不要仅根据时长自动认定为商品视频。

# openmontage-bootstrap-03-usercheck（成片简报 · 用户确认）

## Scope

**做：** 需求不清时先对齐主题与档位，再按档细化，再确认分段视频规划（商品片落在 Backlot「方案确认 / 素材检查」，见「商品片 ↔ 七阶段」；对用户不必死叫表 1/2/3）。商品片在首个正式决策前初始化只读 Backlot 并给出固定网址；完整分析与选项放网页，聊天一次只问当前一项（三点卡等固定小包可合并）。确认后写入简报 artifacts，交接 `04-produce`。

**不做：** 跳过确认直接 compose；三张表堆在同一条消息；静默填 Key / 调 Stock / 付费 API；伪造用户原话；有视频 Key 就自动开烧；静默换视频渠道；轻度/中度出示付费视频渠模表；表 3 强塞全文旁白；商品片（含重度商品）跳过 `references/product-prompt-template.md`；缺图时静默图生图或静默硬烧佩戴支。

**旁白 / BGM：** 本 Skill 主表**不定**；脚注写「稍后安排」。需要时再交接 `05-captions-music` 或后续配音流程。

安装未闭环（5 MCP / 6 Skill 未齐）→ 先交接 `openmontage-bootstrap-01-installer`。

## 何时触发

- 用户要做视频但主题/档位/规划不清  
- 已装好环境，尚未进入正式 produce  
- produce 发现缺少「用户确认过的简报」或用户要求改档时回到本 Skill  

## 出片导览 · 缺步路由 · 就绪接话（入口必读）

用户说「**我想生成视频** / 做个…片 / 帮我出片」等时，**先走路由**（内部判断），再决定接话与下一步 Skill。勿跳过路由直接开烧。

### 能力关系（给用户看的简版）

出片线分三层；**03+04 是主链**（03 面向用户确认，04 面向项目执行）：

```text
【装机层】① installer + ② setup     → 仓 / MCP / 依赖 / verify_ready
【出片主链】③ usercheck + ④ produce  → 表 1→2→3 确认 → 项目里出片
【补充层】⑤ 字幕配乐  ⑥ Key 引导  ⑦ 出错修复（按需）
```

用户问「现在到哪一步 / 我漏了什么」时，可贴上图并标明**当前步骤**。

### 缺步路由（Agent 内部 · 按序检查）

| 检查 | 未满足时 | 交接 Skill | 对用户一句话 |
|------|----------|------------|--------------|
| 安装闭环（5 MCP + 6 Skill） | 先装 | **01-installer** | 还没完成安装，我先带你把环境配齐。 |
| `verify_ready` / 环境未就绪 | 先装依赖 | **02-setup** | 环境还没就绪，我先检测并给你安装计划。 |
| 无已确认简报（表 1–3 / `video_plan`） | 进简报 | **本 Skill（03）** | 可以开始出片了；我们先确认主题、档位和分段规划。 |
| 简报已锁定、用户确认开始 | 执行 | **04-produce** | 按已确认方案开始在项目里出片。 |
| 要字幕 / BGM（可选） | 后置 | **05-captions-music** | 画面好了再加字幕或配乐。 |
| 缺 Stock / 视频 / 付费 Key | 引导 | **06-providers** | 需要 Key 才能用这一档能力，我带你配置。 |
| 工具失败 | 修复 | **07-error-handling** | 出片遇到错误，我先按 playbook 排查。 |

**规则：** ①② 未过 → **禁止**进表 1；表 2/3 未确认 → **禁止**交接 04；用户改档 → 回到本 Skill 重走表 1→2→3。

### 就绪接话（02 已通过 · 进入 03 时必用）

当安装闭环已通过且 `verify_ready` 为真（或等价 ready），用户说「生成视频」类话术时：

**A. 尚无锁定简报（首次 / 新会话出片）→ 非商品片先走「首次 Demo 引导」（推荐非强制）**，读 `references/first-run-demo.md`，再用类似接话：

> **可以开始出片了。** 环境已就绪。  
> **推荐**：先试一支 **10s 或 30s（默认推荐 30s）** 的**轻度短解说 / 品牌 demo**，熟悉流程；旁白与 BGM 可后置。  
> 也可以 **跳过**，按你自己的主题走完整三步简报（主题档位 → 画面方式 → 分段规划）。  
> 我先根据本机可用引擎给出 **Demo 确认卡**（有啥推啥）。

**B. 用户跳过 Demo / 已有部分简报** → 再用完整三表路径：

> 接下来分三步确认：**① 主题与档位 → ② 画面方式 → ③ 分段规划**。  
> 旁白默认推荐 Edge-TTS 男声，可后置。我先出 **表 1**。

商品片首次需求已明确包含商品、用途、时长或素材位置时，**跳过首次 Demo 与整张表 1**，改走下文「首次商品三点确认卡」。
若简报已部分确认（例如只有表 1）：说明**卡在哪一步**，只补未确认表，勿三张重头来（除非用户说改档或重来）。  
非首次（已有完成简报/成片）：可一句带过「也可再试短 demo」，默认进完整三表。

### 首次 Demo 引导（推荐 · 非强制）

**硬规则：** 不静默开烧；用户可随时说「跳过」进表 1；**只推荐本机已就绪的引擎**（有啥推啥）。

1. 探测 `video_compose` / doctor 的 Remotion、HyperFrames 是否可用（见 `references/first-run-demo.md` §2）。  
2. 出示 **一张 Demo 确认卡**（可与就绪接话同条或紧随下一条）：

| 项 | 提案 |
|----|------|
| 档位 | 轻度（锁死） |
| 时长 | **30s（推荐）** / 10s |
| 引擎路径 | 仅列出可用项：Remotion（图表+双栏）和/或 HyperFrames（品牌渐显 logo/字） |
| 主题 | 预设（见 reference）或 AI 现拟同结构 |
| 旁白/BGM | 可后置 |

3. 用户确认「按推荐开始 / 用 10s / …」后：按 reference 写入 `production_tier=light`、`light_presentation`、`duration_seconds`、`video_plan` 等 → 交接 **04-produce**。  
4. Remotion 样板反推：`projects/remotion-light-showcase/`（成片 `renders/showcase-60s.mp4`）。  
5. HyperFrames 样板反推：`projects/hyperframes-jewelry-demo/`（成片 `renders/hyperframes_jewelry_20s.mp4`）。

## 出示节奏（强制）

| 步骤 | 何时出示 | 同一条消息？ |
|------|----------|--------------|
| **消息 0 · Demo 确认卡** | 首次且无锁定简报时**推荐先出**（可跳过） | 仅确认卡（+ 短脚注）；**不要**同时堆表 1–3 |
| **消息 1 · 表 1** | 跳过 Demo 后，或非首次完整简报 | 仅表 1（+ 短脚注） |
| **消息 2 · 表 2** | 表 1 已确认档位后 | 仅表 2（按档分支 2.1 / 2.2 / 2.3） |
| **消息 3 · 表 3** | 表 2 已确认后；**三档都出** | 仅表 3；「确认规划」后才可交接 produce |

禁止把表 1 + 表 2 + 表 3 堆在同一条回复里。Demo 确认卡确认后**不必**再走完整三表（已写入等价锁定字段）。

## 商品片：只读网页 + 聊天决策协议（强制）

适用：商品宣传、种草、详情展示、产品佩戴演示等进入 `bootstrap-commercial` 的任务。非商品片继续使用下文完整 Grill 卡。

1. 环境已 `verify_ready`，且已获得最基本的商品主题后，在**表 1 前**先判定项目模式：
   - **默认新建独立项目**。只要用户没有明确说“继续 / 修改某个旧项目”，都按新项目处理；引用旧图片不等于续作。
   - 仅当用户明确指定旧 `project_id` 并确认续作时，才恢复旧项目。
   - 新建时生成稳定英文候选 ID；若同名已存在，工具会返回带日期与序号的实际新 ID。之后必须使用返回的 `project_id`，禁止继续使用候选 ID。

```text
默认新建：
produce_init_project(project_id, title, pipeline_type="bootstrap-commercial", mode="create_new")

明确续作：
produce_init_project(old_project_id, title, pipeline_type="bootstrap-commercial", mode="resume")
```

   固定管线口径：`pipeline_type=bootstrap-commercial`。

   新项目复用旧图时，只复制用户明确选择的原始图片：

```text
produce_import_project_images(source_project_id, target_project_id, filenames_json)
```

   该工具只复制 `assets/images/` 中列出的图片，不复制 checkpoint、旧视频、旧渲染或其它 artifact。禁止用目录整体复制代替。
2. 立即运行 `python -m backlot open <project_id>`，其中 `<project_id>` 必须是初始化工具返回的实际 ID。把命令输出的完整项目网址主动发给用户；03→04 全程复用同一网址。打开失败只说明“看板暂不可用”，随后退回完整 Grill 卡，**不得阻塞简报或出片**。
3. **网址强制话术（首次决策前必发，禁止等用户追问）：** 在三点卡 / 表 1 等任何确认问题之前，聊天必须先出现固定句式：  
   `你可以查看该网址了解详细信息：{Backlot完整URL}`  
   之后每进入新阶段（写完该阶段 `in_progress` / `awaiting_human` checkpoint 后），再发：  
   `已进入第 N 阶段：{中文阶段名}。请打开看板查看最新证据（若未自动更新请刷新页面）。`  
   不得假设用户已记住网址；不得只写 project_id 让用户自己拼链接。
4. 网页可用时，每个中间决策先写 `brief_locked/in_progress`（素材缺口写 `assets_gate/in_progress`），并用 `metadata_json` 提供：

```json
{
  "needs_user_decision": true,
  "decision_title_zh": "当前选择名称",
  "decision_context_zh": "为什么现在需要决定",
  "decision_prompt_zh": "用户当前只需回答的问题",
  "decision_options": [
    {
      "id": "option_id",
      "label_zh": "选项名称",
      "description_zh": "适用场景与取舍",
      "impact_zh": "对质量、时间或费用的影响",
      "recommended": true
    }
  ],
  "recommendation_zh": "推荐项及原因",
  "examples_zh": "用户可直接发送的回复"
}
```

5. 此时聊天正文只保留：**项目网址（或「已进入第 N 阶段」句）+ 当前一个问题 + 推荐项 + 一条回复示例**。表 1/2/3 的完整分析仍须生成，但放入网页证据，不在聊天重复大表。若网页不可用，才使用下文完整 Grill 卡。
6. 用户回复后，用 `produce_append_decision` 追加决定；`user_response_text` 必须是用户原话，修改既有选择时沿用相同 `category + subject`。随后刷新 checkpoint，清除旧的 `needs_user_decision`，再展示下一项。
7. 表 3 完整产物就绪后，写 `brief_locked/awaiting_human`，其中必须带 `brief`、`asset_precheck`、`video_plan` 与 `segment_cards`（内联对象或项目内 JSON 路径）。`segment_cards` 必须含 `version`、正数 `duration_seconds`、非空 `overall_prompt_zh`，且每段都有 `beat`、`time`、`copy_plan_zh`、`shot_plan_zh`、`asset_plan_zh`。用户回复“确认规划”后用 `produce_approve_checkpoint` 完成阶段；审批必须保留原 artifacts、metadata 与费用。

### 阶段封板（强制 · 进入下一阶段提示之前）

用户反馈痛点：聊天已确认，刷新看板却看不到上阶段选择/整体方案。根因是证据未完整落盘，或残缺 `artifacts_json` 覆盖了先前字段。

**在聊天写出「已进入第 N+1 阶段」之前，必须完成封板：**

```text
1) produce_append_decision（本阶段每一项用户原话已写入）
2) 本阶段应展示的全量证据写入 checkpoint（合并写入，勿传残缺对象覆盖掉 brief/video_plan）
   - 方案确认封板至少：brief + video_plan + segment_cards（含 overall_prompt_zh 与各段文案/镜头/素材安排）
   - 另尽量带 asset_precheck；有识图则 asset_vision
3) produce_approve_checkpoint / produce_write_checkpoint(status=completed 或下一阶段 in_progress)
   → 工具会合并同阶段旧 artifacts，并落盘 artifacts/*.json
4) 聊天先发封板句（禁止跳过）：
   「方案确认阶段证据已写入看板（已确认决定 + 整体方案 + 分段规划）。请刷新面板核对；确认无误后再继续。」
5) 用户有机会刷新后，再发：
   「已进入第 N 阶段：{中文名}。…」
```

禁止：只在聊天复述方案却不写 `segment_cards` / `decision_log`；禁止用空或半截 `artifacts_json` 覆盖已有 brief/video_plan。  
面板侧：后续阶段仍保留「已确认方案档案 / 已确认决定」；点顶栏「方案确认」可回看文案规划。

商品片决定使用固定分类，禁止临时发明 category：主题/时长/渠道用 `brief_selection`，评审方式用 `review_mode_selection`，轻/中/重档用 `production_tier_selection`，候选策略用 `candidate_mode_selection`，运镜/AI 比例用 `motion_mix_selection`，素材取舍用 `asset_decision`，试片/初稿等阶段裁定用 `stage_review_decision`，最终交付确认用 `delivery_signoff`，全程审批策略用 `approval_policy`。

**只读边界：** 网页不放审批按钮、不直接写 JSON、不唤醒 Agent。用户始终在聊天中作出决定，Agent 是唯一写入者。

## 商品片 ↔ 七阶段（强制对照）

管线：`pipeline_defs/bootstrap-commercial.yaml`。面板顶栏七阶段与 Skill 职责如下。  
**原则：** 聊天仍一次确认一项（固定小包如「首次三点卡」可合并）；面板按当前阶段展示全貌证据；对用户可说「方案确认 / 素材检查…」，不必死守「表 1/2/3」话术。内部仍可用表号指代字段包。

| # | 阶段（Backlot） | Skill | 原「表」落点（对用户可改叫法） | 面板展示 | 聊天 |
|---|-----------------|-------|--------------------------------|----------|------|
| 1 | `brief_locked` 方案确认 | **03** | 三点卡 → 主题/档位/时长/预算/评审（旧表1）→ 按档细化（旧表2）→ 比例卡 → **分段规划全文（旧表3）** | 方案摘要、选项、推荐、费用、`video_plan` 文案 | 逐项确认；规划就绪后「确认规划」 |
| 2 | `assets_gate` 素材检查 | **03** | 素材预检闸（表2后表3前已扫的，在此收口分类/缺口） | **用户原图 + AI 扩展占位**按初步计划落入时间片段卡；预检摘要；**不出入片视频** | 确认分类或缺口策略；进阶段须发「已进入第 2 阶段」 |
| 3 | `sample_review` 试片确认 | **04** | — | 试片成片、费用 | 试片是否过关 / 是否全长 |
| 4 | `segment_build` 分段制作 | **04** | — | Beat 胶片、**镜提示词全文**、候选/抽帧（专业） | 专业：分批审查；普通：少打断 |
| 5 | `draft_review` 初稿审查 | **04** | — | 初稿、问题片段、修改清单 | 确认修改清单后再改 |
| 6 | `final_compose` 合成终稿 | **04** | — | 合成进度/技术检查 | 一般不强制问 |
| 7 | `delivery_signoff` 交付确认 | **04** | — | 终稿合集、质量与累计费用 | 最终签收 |

**方案确认阶段内的推荐推进顺序（弹性）：**

```text
三点卡（若适用）
→ 主题与目标是否正确
→ 档位
→ 时长 + 评审模式（≥15s 须出示普通/专业差异）
→ 实验预算（¥8+ 须主动确认）
→ 按档：轻度表现 / 中度素材源 / 重度渠模
→ （启用 AI 视频时）运镜:AI 比例
→ 素材扫描摘要可先写入面板；分类确认可留在「素材检查」阶段若用户想先锁规划
→ 分段规划（旧表3）全文进面板 → 聊天「确认规划」→ brief_locked/awaiting_human
```

允许跳过已从用户原话锁定且用户刚确认过的项，但**禁止**跳过：档位、≥15s 评审模式明示、重度渠模、规划确认、素材主图缺口关闭（或已确认降级）。

非商品片：仍可用完整 Grill「表 1→2→3」话术；不强制七阶段商品板。

### 首次商品三点确认卡（表 1 前强制）

首次用户若已说出“我要做商品宣传视频”、时长和素材位置，禁止直接抛出表 1 或一整套方案。先初始化 Backlot，再只询问下列三点；用户确认后才生成表 1 的完整证据与下一张单项决策卡：

**极简需求：** 表 1 仍用 Grill / 追问补全；付费 AI 镜描述的写法在 **04-produce** 强制读 `openmontage-seedance-prompt`，本 Skill 不扩写镜提示词。

```text
请确认以下 3 点
1. 商品与目标：我理解为「{商品名}」的 {时长} 秒{渠道}宣传视频，是否正确？
2. 制作档位：推荐中度（商品展示 + 有节奏的分段运镜）。轻度适合图文/文字讲解；重度适合需要 AI 视频片段或复杂佩戴演示。
3. 图片识别授权：如素材是可公开访问的 HTTPS 图片链接，是否同意仅将这些链接发送给 Agnes 识别可见特征与建议分类？不会生成图片或视频。

示例回复：
1. 正确，商品是……
2. 选中度
3. 同意识别
```

规则：

1. 第 3 点只在用户明确同意后，才调用 `produce_analyze_public_product_images(image_urls_json, user_authorized=true)`；先写入 `asset_decision` 决策日志，记录“仅公开 URL、仅可见特征分析、未生成素材”。
2. 当前不支持把本地路径、`file://`、Data URI 或内网地址发送给 Agnes。用户只提供本地路径时，先说明“安全导入/临时上传尚未启用”，继续确认第 1、2 点；不得要求用户手写图片内容，也不得假装已识图。
3. 没有公开 URL、用户拒绝授权或识别失败时，保留 `suggested_class=unknown`，在素材预检闸统一让用户确认分类与缺口。
4. 三点中，已从用户原话明确的信息可以预填，但仍须让用户用编号确认或修正。

## Grill 确认卡（用户决策消息强制）

凡需要用户**选择或确认**的节点（表 1、表 2.x、比例卡、表 3、试片/初稿裁定），默认对用户可见正文必须用下列结构，**禁止**只甩内部表格或「请确认表 N」而不列选项。唯一例外：商品片只读网页已正常打开时，完整结构写入网页，聊天按上节压缩为“网址 + 当前问题 + 推荐 + 回复示例”。

```text
请确认选择以下点
1. …
2. …
3. …
补充说明：
1. …
2. …
示例回复：
1. 我选择…
2. 我确认…
3. …需要修改
```

**规则：**

1. 每一「点」= 一个决策项；预填推荐值，但必须显式请用户确认或改选。  
2. 难词在选项旁用**括号短注**（一句话内）；超过一句的解释放「补充说明」。  
3. 「示例回复」须可复制改写，编号与上面的点对应。  
4. 技术字段名（`video_channel`、`review_mode` 等）默认不进用户正文；必须出现时附中文释义。

### 命名防混（Token* 强制）

| 名称 | 含义 | 用户可见写法 |
|------|------|--------------|
| **Agnes** | 付费**视频/图片渠道**（厂商） | `Agnes（付费视频渠道）` |
| **TokenPlan** | Agnes 账号的**付费/并发档**（`AGNES_ACCOUNT_TIER`） | 仅出现在 Agnes 行说明：`有 TokenPlan 档时并发更高`；**不是**渠道选项 |
| **TokenHub** | **腾讯**视频网关（同一 Key；下挂混元 / Pixverse 等模型） | 须带子名：`TokenHub·混元…` 或 `TokenHub·Pixverse…` |

**禁止：** 把 TokenHub 写成 Agnes 订阅/套餐；把 TokenPlan 写成独立视频渠道；对用户甩光秃秃的 `TokenHub` 而不带括号；把 **Pixverse** 叫成「混元」或把混元叫成 Pixverse。  
**自检：** 写到「Token*」时先分清——**渠道**才进表 2.3 选项；**套餐/档**只挂在 Agnes 说明里。记忆钩子：`Hub=腾讯渠`，`Plan=Agnes 档`，`混元≠Pixverse`。

## Hard protocol

### 1. 收集已知项

从用户话提取：主题、时长、用途、自带素材等。  
缺的**不要连环追问**；用表 1 默认填满再请用户改。

### 2. 消息 1 — 表 1（主题 + 档位）

对用户**必须**用 Grill 确认卡（见上），不要只贴内部表。内部对照字段如下：

| 点 | 提案 | 状态 |
|----|------|------|
| 主题 | （已有则照写；否则先给 2–3 个候选再填入选定） | 默认可改 |
| 档位 | 轻度 / 中度 / **重度（商品宣传推荐）** | **必选** |
| 时长 | 默认 30 秒（竖屏短视频可建议 15–30；商品试片常 10/30） | 默认可改；**≥15s** 须出示评审模式选项 |
| 实验 API 预算 | 微额 ¥1 / 轻量 ¥3 / 经济 ¥5 / **标准 ¥8（默认）** / 充裕 ¥12 | 重度或商品片出示；**¥8 及以上须主动询问确认**；&lt;¥8 仅提示；**非售价** |
| 评审模式 | **普通（默认，快）** / **专业（≥15s 商品推荐）** | ≥15s 商品片**必须显式请用户选**；不强制专业，但须写清差异 |

**档位说明（可放入补充说明）：**

| 档位 | 擅长 | 效果 | 需要 |
|------|------|------|------|
| 轻度 | 简单技术讲解，如现象动画解说、技术讲解 | 由提示词、文案、提供的素材编排决定 | 项目本身配置即可，下载完依赖即可使用 |
| 中度 | 风景、人物展示解说，如自然风光讲解 | 尤其受 **Pixabay** 与 **Pexels** 素材影响 | 需获取 Pixabay / Pexels Key 并配置（也可用自带素材） |
| 重度 | 较精致复杂展示，如商品宣传、电商详情 | 由视频模型、提示词、文案决定 | 需获取视频模型 Key 并填入 |

**表 1 Grill 卡示例（≥15s 商品 · 可改写）：**

```text
请确认选择以下点
1. 主题：…（可改）
2. 档位：重度（商品宣传推荐）/ 中度 / 轻度
3. 时长：20 秒（可改；建议首次 10–30s）
4. 实验 API 预算：标准 ¥8（默认，非售价）/ ¥1 / ¥3 / ¥5 / ¥12
5. 评审模式：普通（默认，快）/ 专业（≥15s 商品推荐，可控性更高）
补充说明：
1. 实验 API 预算 = 本任务调用模型的费用上限，不是成片售价；选 ¥8 或 ¥12 需你明确确认。
2. 专业模式：方便你进一步提高对视频生成的可控性（总览表、分批逐段审查）；15s 以上商品片推荐可选。普通模式：默认方案，快，只过试片+初稿。
3. 旁白默认推荐 Edge-TTS，可后置；付费视频渠道要等确认「重度」后才出现。
示例回复：
1. 主题按提案
2. 我选择重度
3. 时长 20s
4. 我确认预算 ¥8
5. 我选择普通（或：我选择专业）
```

**表 1 短脚注（Agent 自用 · 可并入补充说明）：**

1. 第一次使用建议先生成 **10s–30s** 以内；熟悉后再做 45s–60s；**不建议超过 60s**。  
2. 本轮主流程**先定视频**；旁白与 BGM **可以后置**。  
3. 付费视频渠道/模型**仅在选重度之后**才出示。  
4. 选 **¥8 或 ¥12** 必须**主动询问**确认；首次达标成本含被拒候选。  
5. ≥15s 商品：**禁止**静默默认普通而不出示专业选项差异。  
6. 确认本表后**另开消息**出示表 2；重度锁渠模后、表 3 前另出比例卡。

主题没有时：在贴卡前或点 1 内注明 2–3 个候选，等用户选后再定「提案」。

### 3. 消息 2 — 表 2（按档分支）

表 1 确认后，**单独一条消息**只出示对应该档的表 2。未完成表 2 确认前，不出表 3、不交接 produce。

#### 3.1 轻度 — 表 2.1 表现方式（互斥单选）

| # | 选项 | 说明 |
|---|------|------|
| 1 | 静态图片 | 少图/单图 + 字幕卡 |
| 2 | 多图顺序轮播（可带文案） | 多张图按序切换，可叠文案 |
| 3 | 动态文字解说 | 以文字动效为主 |
| 4 | Remotion 动画 | 图表 / 双栏对比 / 技术讲解；本机可用时 **可标推荐** |
| 5 | HyperFrames 动画 | 品牌渐显 logo/动能文字；本机可用时 **可标推荐** |

用户必须只选 **一项**。确认后进入表 3。  
**有啥推啥：** 选项 4/5 仅在本机对应引擎就绪时标为推荐；不可用则注明并勿当作默认。

**表 2.1 脚注：**  
- **Remotion：** cut 组合与样板见 `references/light-remotion-showcase.md`（`projects/remotion-light-showcase/`，成片 `showcase-60s.mp4`）。  
- **HyperFrames：** 品牌渐进结构见 `references/first-run-demo.md` §5（`projects/hyperframes-jewelry-demo/`，成片 `hyperframes_jewelry_20s.mp4`）。  
- **首次短 demo：** 优先读 `references/first-run-demo.md`。

写入字段建议：`light_presentation` = `still` / `image_carousel` / `motion_text` / `remotion` / `hyperframes`。

#### 3.2 中度 — 表 2.2 素材来源 + 文案提示

| 方式：中度 | 素材来源 | 文案提示词 |
|------------|----------|------------|
| | Pixabay 和 Pexels | （主题相关检索/文案方向） |
| | 自带图片和视频 | （路径或「将放入 assets/…」） |

**闸门：**

- 已填至少一个 `PEXELS_API_KEY` / `PIXABAY_API_KEY` → 两行都可选。  
- **未填 Stock Key** → 仍出示本表，但「Pixabay 和 Pexels」行标为**不可用**；用户只能选「自带图片和视频」。可脚注指引去 `.env-example.md` / `06-providers` 补 Key。  
- 未写入真实 Key 前：**禁止**调用 Stock 下载。

写入字段建议：`medium_source` = `stock` | `user_assets`；附文案提示原文。

#### 3.3 重度 — 表 2.3 付费视频渠道 / 模型（仅重度）

**仅当表 1 档位=重度时出示。** 轻度/中度禁止出示本表。对用户用 **Grill 确认卡**。

检测视频渠道 Key：**仅** `AGNES_*`、`TOKENHUB_*`（及日后文档标明已接线的渠道）。`FAL_KEY` 等**不**单独作为本产品重度主渠闸门，除非另有约定。eRouter 视频仍 **planned** 时标 ❌，勿当可烧。

**推荐规则：**

- 只列出已填 Key 且可出片的渠道/模型。  
- 若 Agnes 与 TokenHub **都有 Key** → 默认推荐 **Agnes**，并写清差异（如并发、分辨率）。  
- 仅一家有 Key → 推荐该家，仍须用户确认。  
- **无任何可用视频 Key** → **不**出示「假可用」表；提示：先补 Key（`06-providers` / `.env-example`），或**改档**到轻度/中度。禁止假装能烧重度。

**表 2.3 Grill 卡示例：**

```text
请确认选择以下点
1. 视频渠道：Agnes（付费视频渠道，默认推荐）
            / TokenHub·混元（腾讯混元，约720p，无自定义时长）
            / TokenHub·Pixverse（腾讯 Pixverse，可设时长，默认5s/720p）
2. 模型：随上项锁定
   - Agnes → agnes-video-v2.0
   - 混元 → hy-video-1.5
   - Pixverse → pixverse-video-v6.0
补充说明：
1. Agnes 与 TokenHub 是两条独立付费渠道；TokenHub 下混元与 Pixverse 共用 TOKENHUB_API_KEY，但接口/模型不同，不要混叫。
2. TokenPlan 是 Agnes 账号的付费/并发档（不是渠道）；有 TokenPlan 档时 Agnes 并发通常更高。
3. TokenHub·混元：约 720p、默认一次一段、无自定义时长；长片靠多段拼接；本地图可用 base64。
4. TokenHub·Pixverse：可设每段 duration（默认 5s）、quality（默认 720p）；图生需公网图片 URL，或按 3.3.1 在当前项目明确授权后临时上传项目内本地图。
5. 禁止静默换渠；若要换渠道须你明确说。
示例回复：
1. 我选择 Agnes
2. 模型按默认
（或：1. 我选择腾讯混元 / TokenHub·混元）
（或：1. 我选择 Pixverse / TokenHub·Pixverse）
```

**Agent 内部对照表（勿直接甩给用户光秃秃渠道名）：**

| 用户可见名 | 内部 channel | 模型 | 说明 |
|------------|--------------|------|------|
| Agnes（付费视频渠道） | `agnes` | `agnes-video-v2.0` | 推荐；TokenPlan=档位不是渠道 |
| TokenHub·混元（腾讯混元，约720p） | `tokenhub` | `hy-video-1.5` | 并发 1；无自定义时长；本地图 OK |
| TokenHub·Pixverse（可设时长） | `tokenhub` | `pixverse-video-v6.0` | 同 Key；可写 `video_duration_sec`/`video_quality`/`aspect_ratio`；I2V 需公网 URL，或经本项目明确授权后把项目内本地图临时传 OSS |
| eRouter | — | — | ❌ 未实现，勿当可烧 |

写入：`ai_video=enabled`；`video_channel`；`video_model`；选 Pixverse 时可写 `video_duration_sec`（默认 5）、`video_quality`（默认 `720p`）、`aspect_ratio`（如 `16:9` / `9:16`）。  
非重度：`ai_video=disabled`；渠/模为空。

#### 3.3.1 Pixverse 本地图临时上传（可选阿里云 OSS）

触发条件：用户锁定 `video_model=pixverse-video-v6.0`，某段使用本项目 `assets/images/` 内的本地图，且已配置 OSS。

1. **03 只确认并记录，不上传。** 聊天一次只问：
   > Pixverse 图生需要公网 URL。是否允许本项目把所选图片临时上传到你的私有阿里云 OSS，生成默认 6 小时签名 URL，生成结束后尽量删除？Secret 和签名 URL不会进入看板。
2. 用户明确同意后，用 `produce_append_decision` 写入当前项目：
   - `category="asset_decision"`
   - `subject="Pixverse local image temporary OSS upload"`（之后变更必须保持同一 subject）
   - `options_considered` 至少含 `option_id="approved"` 与 `option_id="denied"`，每项按 schema 写 `label/score/reason`
   - `selected="approved"`、`user_approved=true`
   - `user_response_text` 必须是用户原话。
3. 只认当前 `project_id` 的最新同 subject 决策；新项目不得继承旧项目授权。用户撤销时追加 `selected="denied"`，不得改写旧记录。
4. 未配置或用户拒绝：继续用公网 `image_url`；若要改 Agnes / 混元，按换渠协议重新确认，禁止静默切换。
5. 授权不是全局开关。04 每次本地图调用仍须显式传 `project_id` 与 `user_authorized_upload=true`；工具层默认拒绝。

#### 3.4 画面构成比例（运镜:AI · ≥15s 且可烧 AI 时）

**触发：** `duration_seconds >= 15`，且（重度已锁视频 Key / `ai_video=enabled`，或商品片明确要用付费视频生成）。  
**时机：** 表 2.3（或等价渠模）确认之后、**表 3 之前**单独一条消息；对用户用 **Grill 确认卡**。普通与专业都要出示；普通默认预勾推荐项。

| 选项 | 运镜:AI生成 | AI生成视频约占 | 说明 |
|------|-------------|---------------|------|
| A | **1:1** | ~50% | **推荐（普通默认）** |
| B | 1:2 | ~67% | 更动感；**成本可能上涨**；物品/人物不一致风险升高 |
| C | 0:1 | ~100% | 几乎全模型；强提示成本与一致性风险 |
| D | 2:1 | ~33% | **（更省可选；可能有幻灯片感）** |

**Grill 卡要点示例：** `1. 画面比例：A 1:1（推荐）/ B 1:2 / C 0:1 / D 2:1`

**规则：**

1. 比例是**推荐目标**，按整片 **AI 模型生成时长合计** 大概符合即可（约 ±10%–15%）；beat 怎么切可自由安排，**不按段数硬凑**。  
2. 审查中用户可把某段从运镜改成 AI（或反过来）；**终稿不强制贴死**原比例；偏离时口头告知观感/费用/一致性即可。  
3. 无可用视频 Key：不出 B/C，或标灰并说明「未配置视频 Key，无法提高 AI 占比」。  
4. 写入：`motion_mix`（`1:1`/`1:2`/`0:1`/`2:1`）、`motion_mix_source`（`default_recommend`|`user_selected`）。普通未改选 → `1:1` + `default_recommend`。

### 4. 消息 3 — 表 3（分段视频规划 · 三档都出）

#### 4.1 触发

表 2 已确认后，**轻度 / 中度 / 重度均必出**表 3。

用户若无现成文案：Agent **直接生成一版**分段提案供过目；用 **Grill 确认卡**（点：确认规划 / 改某段）；回复确认后锁定。禁止未确认就开烧付费视频。

#### 4.2 重度商品（强制）

若主题/用途为**商品宣传、种草、详情展示、产品佩戴演示**等（含**重度商品**）：

1. **必须先读**本目录 `references/product-prompt-template.md`。  
2. 素材分类、缺图询问（默认 I2I）、切段/重点段、每段主参考图、英文提示词组装——按该参考执行。  
3. 缺口未关闭前**不出最终表 3**、不交接 produce 烧视频。  
4. 禁止静默 I2I / 静默硬烧佩戴支。

非商品片：跳过本小节，按通用表 3 即可。

#### 4.3 结构（强制列）

| 段 | 时长 | 镜头目的 | 画面/文案要点 | 素材（有则填） |
|----|------|----------|---------------|----------------|
| 1 | （如 0–10s） | … | … | 路径或「无」 |

可选总览一行（非强制旁白）：叙事结构（如钩子 → 卖点 → 收束）；重度可写渠道/模型沿用表 2.3。

**禁止：** 在表 3 要求填写「全文旁白」或另选声线。

**表 3 短脚注（必写）：**

1. 回复「确认规划」后才写入简报并交接 produce。  
2. 可只改某一段后要求重贴。  
3. **旁白与 BGM 稍后安排**（本表不定声线）。  
4. 商品片：已按 `product-prompt-template.md` 完成分类/缺图/切段/参考图（若适用）。  
5. **可交付硬门槛**：商品身份一致、无结构断裂、流畅可播且动态不单调。AI 动态秒数是**实验/推荐目标**（由 `motion_mix` 推导整片 AI 总秒数，±约 15% 即可），**不是**单独否决成片的硬门槛。  
6. 出片顺序：先 **10–15s 试片** 确认，再全长；普通模式只展开问题片段（可说「切专业」看逐 beat）。  
7. 已锁 `motion_mix` 时：表 3 按推荐 AI 总秒数**大概**排布；审查中可改某段方式，允许终稿偏离比例。

若已锁比例：排表前用 `recommended_ai_seconds(duration, motion_mix)` 或等价心算，避免有 Key 却几乎全是运镜。

### 5. 全部确认后写入并交接

适用：表 1 + 表 2 + 表 3 均已确认。

步骤：

1. 安装未闭环 → installer。  
2. 未 `verify_ready` → setup。  
3. 复查表 1 前 `produce_init_project` 返回的实际项目 ID；商品片此处禁止再次初始化。非商品片若尚无项目，也默认 `mode=create_new`；只有用户明确续作时才用 `mode=resume`。
4. 写入档位：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",   # light→template；medium→stock|user；heavy→paid_gen（可按锁定细化）
  tts_source="",      # 本轮可空或暂缓；旁白后置
  api_budget_tier="standard",   # micro|lite|economy|standard|ample；默认 standard
  budget_cny="8",               # 1|3|5|8|12；实验 API 预算上限，非售价；默认 8
  review_mode="normal",         # normal|pro；默认普通
  candidate_mode="adaptive",    # adaptive=单候选+条件重试；stable_dual=关键 beat 双候选
  motion_target_band="60s_cost_ref",  # 可选实验带；有 motion_mix 时以 mix 推导为主
  motion_mix="1:1",             # 1:1|1:2|0:1|2:1；推荐目标（软约束）
  motion_mix_source="default_recommend",  # default_recommend|user_selected
  duration_seconds="30",        # 写入以便推导 AI 秒数带
  style_label_zh="",            # 可选中文名：高端极简/生活方式/电商清晰展示
  style_playbook=""             # 可选内部 styles id；勿强制第四表
)
```

商品/重度未明示预算时：**默认** `api_budget_tier=standard`、`budget_cny=8`，且须**主动询问确认**（¥8+）。  
未明示评审模式时：**默认** `review_mode=normal`。  
未明示候选策略时：**默认** `candidate_mode=adaptive`（禁止默认双候选）。  
未明示画面比例且已触发比例卡：默认 `motion_mix=1:1`、`motion_mix_source=default_recommend`，并向用户念清配置。

5. **简报扩展字段**（写入项目 artifacts / 简报 JSON，交接时点明）：

| 字段 | 含义 |
|------|------|
| `theme` | 表 1 主题 |
| `duration_seconds` | 表 1 时长 |
| `production_tier` | `light` / `medium` / `heavy` |
| `api_budget_tier` | `micro` / `lite` / `economy` / `standard` / `ample` |
| `budget_cny` | `1` / `3` / `5` / `8` / `12`（实验上限，非售价） |
| `needs_choice_confirm` | ¥8+ 为 true（选档须主动询问） |
| `review_mode` | `normal` / `pro` |
| `candidate_mode` | `adaptive` / `stable_dual` |
| `motion_mix` | `1:1` / `1:2` / `0:1` / `2:1`（推荐目标，软约束） |
| `motion_mix_source` | `default_recommend` / `user_selected` |
| `motion_target_band` | `30s_ref` / `60s_cost_ref` / `60s_high_motion`（可选；有 mix 时以 mix 为主） |
| `light_presentation` | 轻度表现方式（含 `remotion` / `hyperframes`）；非轻度可空 |
| `first_run_demo` | 可选；首次 Demo 确认卡路径为 `true` |
| `medium_source` | `stock` / `user_assets`；非中度可空 |
| `ai_video` | 重度且已锁渠模 → `enabled`；否则 `disabled` |
| `video_channel` | `agnes` / `tokenhub` / …；非重度空 |
| `video_model` | 模型 id（如 `agnes-video-v2.0` / `hy-video-1.5` / `pixverse-video-v6.0`）；非重度空 |
| `video_duration_sec` | 可选；Pixverse 每段秒数，默认 `5` |
| `video_quality` | 可选；Pixverse 画质，默认 `720p` |
| `aspect_ratio` | 可选；如 `16:9` / `9:16`（Pixverse T2V） |
| `video_plan` | 表 3 分段规划；商品片须含：切段/重点段、`asset_classes`、`path`、`gap_fill`、每段 `ref_image`（见 references） |

6. 商品片 `brief_locked` 最终 checkpoint 的 `artifacts_json` 必须包含 `brief`、`asset_precheck`、`video_plan`、`segment_cards`；`asset_ledger`（素材角色、路径、候选、是否选中）在素材已确认时一并携带。缺少完整 `segment_cards` 时工具会拒绝封板。
7. `approval_text` 用用户原话（禁止编造）。
8. 商品片调用 `python -m backlot open <project_id>` 复用原网址；向 04 交接 `project_id` 与网址，不要求用户另开页面。
9. 交接 **`openmontage-bootstrap-04-produce`**。字幕/BGM → `05-captions-music`（**后置**，不挡本步交接）。
10. 失败 → `07-error-handling`。

**闸门：** 表 2 / 表 3 未确认时，**禁止**交接 produce、禁止开始付费视频生成。

### 6. 改档

须用户明确说「升到中度 / 升到重度 / 改回轻度」或「改档」。  

- **不要**只改 `production_tier` 数字完事。  
- 应重走 **表 1（至少确认新档位）→ 表 2 → 表 3**，再写回简报。  
- 从轻度/中度升到重度：必须重新走表 2.3（Key 闸门）与表 3。  
- 从重度降档：清空或停用 `ai_video` / 渠模，并重出对应表 2 与表 3。

## 商品片素材需求与中文状态

商品宣传片的素材预处理位于**表 2 后、表 3 前**，是「方案确认」阶段的内部闸门，不新增顶栏阶段。表 2 已锁定档位、时长、是否佩戴与生成路径后，才可以判断素材是否够用；表 3 未确认前禁止开始 I2I / I2V。图片数量是建议和门禁依据，不是要求每个镜头都使用不同图片；图片可以在不同镜头中复用，但重点镜头不应全部依赖同一张图。

**操作细则（必读）：** `references/asset-preprocess-gate.md`  
**提示词词库（写 AI 镜）：** `references/commercial-prompt-lexicon.md`  
**写镜提示词：** 在 `04-produce` 付费 AI 段强制读 `openmontage-seedance-prompt`；03 只锁表与素材闸。

### 素材预处理闸（强制 · 仅商品/电商片）

1. 调用只读 MCP `produce_scan_user_images(project_id)`，扫描 `assets/images/` 的文件名、尺寸、大小、重复文件与**文件名建议分类**；工具不写文件、不生成图片。
2. **可选识图（有 Key 才调）：** 再调 `produce_describe_user_images(project_id)`。Key=`VISION_API_KEY` 或 `DASHSCOPE_API_KEY`；可覆盖 `VISION_BASE_URL` / `VISION_MODEL`。空 Key → 工具降级返回扫描结果，**不中断闸门**。识图结果只辅助 `suggested_class` / 中文描述，**不能**代替用户确认。
3. Agent 将结果整理为 `asset_precheck`（可含 `vision_*` 字段）：`suggested_class` 仅为建议。尽量落盘 `artifacts/asset_precheck.json` 与 `artifacts/asset_vision.json`。
4. 先将 `asset_precheck` 以内联 artifact 写入 `brief_locked/in_progress`（素材收口时写 `assets_gate/in_progress`）。仅在无素材、分类不明、低分辨率、重复、缺少所需角色，或需要补图/降级时，设置 `metadata.needs_user_decision=true` 并出示当前一个问题。
5. 用户需决定时，完整证据在 Backlot；聊天只给网址 +「已进入第 N 阶段」+ 当前问题 + 推荐 + 回复示例。用户原话以 `asset_decision` 写入 `decision_log`。禁止静默补图或静默开始 I2I / I2V。
6. 用户确认分类与缺口处理后，用 `lib.asset_precheck.build_asset_ledger` / `build_asset_requirements`（或等价）写入确认角色、`asset_requirements`、`asset_ledger`，再写入每段 `ref_image` / `gap_fill` 到 `video_plan`。最终 `brief_locked/awaiting_human` 必须同时携带 `brief`、`asset_precheck`、`video_plan`、完整 `segment_cards`（有则带 `asset_ledger`）。
7. 进入顶层 `assets_gate` 前须落盘 `segment_cards`（时间 + `asset_plan_zh` / 缺口文案）与可展示的 `asset_ledger`（按 beat 挂用户图；AI 扩展用 `kind=image` + `note_zh=AI扩展占位` 或缺口字段）。该阶段面板**只显示图片与安排，不显示入片视频**。

**用户可见边界：**

- 方案确认页：素材预检文字摘要；有风险时才折叠文件明细；时间线卡不出媒体。
- 「素材检查」：用户原图 + AI 扩展占位按初步计划落入时间片段卡；视频仍从「试片确认」开始。

| 目标时长 | 最低可运行图片数 | 建议图片数 | 建议覆盖类型 |
|----------|------------------|------------|--------------|
| 10 秒 | 1–2 张 | 2–3 张 | 商品主图、第二角度或细节图；可选佩戴/使用图 |
| 30 秒 | 2–3 张 | 4–6 张 | 商品主图、多个角度、细节图、佩戴/使用图；可选氛围图 |
| 60 秒 | 3–4 张 | 6–10 张 | 主图、正侧背角度、细节图、佩戴/使用图、包装/场景图 |

至少需要 1 张能够清楚识别商品整体的**商品主图**。图片角色统一使用：商品主图（`product_hero`）、角度图（`product_angle`）、细节图（`product_detail`）、佩戴/使用图（`on_body` / `in_use`）、包装图（`packaging`）、生活方式场景（`lifestyle`）、背景图（`background`）。

素材检查状态使用中文，不使用英文状态值：

| 中文状态 | 判断 | 处理 |
|----------|------|------|
| **就绪** | 至少有商品主图，达到最低图片数量，重点段有合理参考图 | 可以按计划继续 |
| **降级继续** | 有商品主图但低于建议数量，或缺少角度/细节/佩戴图 | 必须提示一致性风险；用户确认后可继续，必要时先图生图补充 |
| **等待用户选择** | 没有商品主图，或严格展示具体商品但缺少核心参考图 | 必须让用户选择补图、允许图生图生成概念素材，或改为概念片 |

缺图处理也使用中文显示：**不补图**、**用户补图**、**图生图**、**仅概念素材**。表格面向用户时使用以下中文表头，括号内保留机器字段名以兼容现有 `video_plan`：

| 分段 | 时长 | 镜头目的 | 画面/文案要点 | 素材类型（`asset_classes`） | 参考图片（`ref_image`） | 缺图处理（`gap_fill`） | 素材状态 |
|------|------|----------|---------------|----------------------------|-------------------------|------------------------|----------|
| 1 | 0–5s | 展示商品整体 | … | 商品主图 | `assets/images/hero.png` | 不补图 | 就绪 |
| 2 | 5–10s | 展示商品细节 | … | 细节图 | `assets/images/detail.png` | 图生图 | 降级继续 |

写入简报时，保留 `asset_classes`、`ref_image`、`gap_fill` 作为程序字段；它们的用户可读含义分别是“素材类型”“参考图片”“缺图处理”。商品片还应写入素材需求摘要 `asset_requirements`，至少包含：时长档位（`duration_profile`）、最低图片数（`minimum_image_count`）、建议图片数（`recommended_image_count`）、已有图片数（`available_image_count`）、已有/缺少图片类型（`available_asset_classes` / `missing_asset_classes`）、素材状态（`status`）、补图方式（`fallback`）、质量风险提示（`quality_warning`）和用户是否确认缺口（`user_confirmed_shortage`）。

生成最终表 3 前，必须完成：数量检查 → 图片类型检查 → **分辨率粗检**（过小细节图勿当全屏主参考）→ **身份冲突提示**（色温/款式明显不一致须标待确认）→ 缺失类型提示 → 用户补图或允许补图确认 → 记录素材状态。没有商品主图时不能静默生成具体商品；允许图生图时必须明确“先补图，再 I2V”，并提示商品细节可能不一致。典型用户按 **5 张有效角色图** 模拟（主图/角度/佩戴或使用/细节/背面或场景）；重复同构图不算 5 张有效。

## 与其它 Skill

| Skill | 关系 |
|-------|------|
| 01-installer | 安装未闭环时先装（见上文「缺步路由」） |
| 02-setup | `verify_ready` 未过先检测；通过后用户说「生成视频」→ 本 Skill 就绪接话 |
| 04-produce | 简报确认后的出片执行；须遵守本 Skill 锁定；默认不重选档 |
| 05-captions-music | 字幕 / BGM（后置） |
| 06-providers | Key 引导（中度 Stock / 重度视频） |
| 07-error-handling | 出片失败修复 |

## 成功标准

- 用户说「生成视频」且环境已就绪、无锁定简报时：已按「就绪接话」**先推荐**首次 Demo（可跳过），引擎 **有啥推啥**；读过 `references/first-run-demo.md`  
- 用户确认 Demo 卡后：已写入轻度锁定字段并交接 04，**未**静默开烧  
- 用户跳过 Demo 或非首次：已进入表 1（或说明卡在哪一步）  
- 缺步时已按「缺步路由」交接 01/02，未越级开烧  
- 完整简报路径：用户确认过 **表 1**（主题 + 档位 + 时长；商品/重度含实验 API 预算默认 ¥8 且 ¥8+ 已主动询问、评审模式默认普通）  
- 按档确认过 **表 2**；轻度互斥单选（含 Remotion/HyperFrames，按可用性推荐）；中度遵守 Stock Key 闸门；重度遵守视频 Key 闸门与推荐规则  
- **≥15s 且可烧 AI** 时已确认 **画面构成比例**（或已说明无 Key）；已说明比例为推荐软约束  
- **表 3** 三档都已确认（Demo 卡路径除外）；无全文旁白强求；无文案时已给 AI 提案并获「确认规划」；已说明硬门槛与推荐 AI 秒数目标  
- 重度商品已强制走 `product-prompt-template.md`  
- 已写 `production_profile`（含 `api_budget_tier`/`budget_cny`/`review_mode`/`candidate_mode`/`motion_mix`）与 `video_plan` 等扩展字段  
- 未在轻度/中度展示付费视频渠模；无 Key 时未假装可烧重度  
- 未静默换渠、未静默 I2I、未跳过确认开烧  
- 未把实验 API 预算说成售价；未默认开启双候选  
- 未把 `motion_mix` 当成终稿硬门槛；未在有 Key 时默认把表 3 排成几乎全运镜
