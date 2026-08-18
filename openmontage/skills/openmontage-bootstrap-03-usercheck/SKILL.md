---
name: openmontage-bootstrap-03-usercheck
description: >-
  BootStrap brief before produce: default ecommerce commercial after key scan;
  light Demo only if the user explicitly asks (or chooses the no-key fallback).
  Theme clear → init + Backlot URL; ask one missing field. Tables 1–3 remain
  internal field packs. Writes production_profile + artifacts, hands off to produce.
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

该参考文档规定：默认**普通评审**（方案→试片→初稿/问题片段）；库页「极简」为三停（方案→素材→交付），素材通过后直接生成正式段、不做独立试片；**专业模式仅当用户主动要求**。

本路由不替代当前 03 -> 04 主链，也不改变已经确认的 provider、模型或 render runtime。它只增加商品视频的展示、暂停、修改和用户确认方式。

判断条件不明确时先询问用户，不要仅根据时长自动认定为商品视频。

# openmontage-bootstrap-03-usercheck（成片简报 · 用户确认）

## Scope

**做：** 环境就绪后先扫视频 Key，默认电商宣传片。主题说清则 init 项目并立刻给 Backlot 网址；缺时长/图/预算再问一句。需求不清时再对齐主题与档位，再按档细化，再确认分段规划（商品片落在 Backlot「方案确认 / 素材检查」，见「商品片 ↔ 七阶段」；对用户不必死叫表 1/2/3）。表 3 前先输出 `beat × 所需画面 × 候选图片` 覆盖矩阵，表 3 确认后在 `assets_gate` 关闭补传/I2I/复用/降级与审图子闸。完整分析与选项放网页，聊天一次只问当前一项。只有 `assets_gate=completed` 才交接 `04-produce`。

**不做：** 未明确要求时先推荐轻度 Demo；跳过确认直接 compose；三张表堆在同一条消息；静默填 Key / 调 Stock / 付费 API；伪造用户原话；有视频 Key 就自动开烧；静默换视频渠道；轻度/中度出示付费视频渠模表；表 3 强塞全文旁白；商品片（含重度商品）跳过 `references/product-prompt-template.md` 或 `references/asset-preprocess-gate.md`；以“总张数够”代替 Beat 覆盖；缺图时静默图生图、静默复用或静默硬烧佩戴支；把 Pixverse/video provider 当生图 provider；把未 approved 候选交给 04。

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
【出片主链】③ usercheck + ④ produce  → 默认电商（扫 Key → 给网址 → 缺啥问一句）→ 项目里出片
【补充层】⑤ 字幕配乐  ⑥ Key 引导  ⑦ 出错修复（按需）
```

用户问「现在到哪一步 / 我漏了什么」时，可贴上图并标明**当前步骤**。

### 缺步路由（Agent 内部 · 按序检查）

**开口前先 `read_install_state`。** 文件在仓根 `.openmontage/install-state.json`（见 `AGENTS.md`）。以 `verify_ready` 判断是否第一次/环境是否已过；再 `scan_video_keys` 并以当场扫描为准。禁止：已就绪还走安装话术；未就绪就进表 1 或假装网页能创建；就绪了却不给看板网址。

| 检查 | 未满足时 | 交接 Skill | 对用户一句话 |
|------|----------|------------|--------------|
| `read_install_state`：文件不存在且本地没有项目 | 第一次 | **01-installer** | 还没完成安装，我先读本机状态再带你配齐。 |
| 状态文件不存在，但 `projects/` 已有项目 | 已用过，勿再 clone | 写/刷新 install-state 后按 `verify_ready` 走 02 或 03 | 仓库已经在用，我按本机状态继续，不再重新下载。 |
| `verify_ready` 不为真（仓已在） | 先装依赖 | **02-setup** | 环境还没就绪，我先检测并给你安装计划。 |
| 安装闭环（5 MCP + 6 Skill） | 先装 | **01-installer** | 还没完成安装，我先带你把环境配齐。 |
| 无已确认简报（表 1–3 / `video_plan`） | 进简报 | **本 Skill（03）** | 可以开始出片了；先扫 Key，默认按电商宣传片确认方案。 |
| 简报已锁定、用户确认开始 | 执行 | **04-produce** | 按已确认方案开始在项目里出片。 |
| 要字幕 / BGM（可选） | 后置 | **05-captions-music** | 画面好了再加字幕或配乐。 |
| 缺 Stock / 视频 / 付费 Key | 引导 | **06-providers** | 需要 Key 才能用这一档能力，我带你配置。 |
| 工具失败 | 修复 | **07-error-handling** | 出片遇到错误，我先按 playbook 排查。 |

**规则：** ①② 未过 → **禁止**进表 1；表 2/3 未确认 → **禁止**交接 04；商品片另须 `assets_gate=completed`；用户改档 → 回到本 Skill 重走表 1→2→3 与受影响的素材闭环。

### 就绪接话（02 已通过 · 进入 03 时必用）

当安装闭环已通过且 `verify_ready` 为真（或等价 ready），用户说「生成视频」类话术时：

**0. 开口前先读状态文件再扫 Key（强制）**  
先 `read_install_state`。若 `verify_ready` 已为真：**禁止**再走 01 安装话术，**必须**继续给看板网址（用户也可在库页点「开始创建项目」）。若文件不存在：先看 `projects/` 或返回里的 `existing_project_count`——有项目就视为已下载使用过，禁止再 `clone_repo`，刷新快照后若 `verify_ready` 仍假则走 02。无文件且无项目才交接 01。

然后调用 `scan_video_keys`（只读，**不返回 Key 值**），再 `snapshot_install_state`。以返回的 `video_key_present` 为准。可对照 `read_install_state`，仍以当场扫描为准。只认 `.env-example.md`「视频生成专项」里的 KEY/TOKEN/SECRET 变量名，检查仓根 `.env` 与当前 MCP 进程环境。空 Key 禁止付费 generate。

- **有可用视频 Key**（`video_key_present=true`）→ 第一次即可走电商宣传片（渠模仍须用户确认后才 generate）。
- **无可用视频 Key** → 先告知「当前没有可用视频模型 Key」，再二选一：去填 Key（交接 `06-providers`），或这次走免费轻度（才读 `references/first-run-demo.md`）。

**A. 尚无锁定简报（首次 / 新会话）→ 默认电商宣传片**  
禁止先推荐轻度 Demo。仅当用户明确说「讲解 / Demo / 轻度短片 / 先试流程」，或无 Key 且选了免费轻度，才走「首次 Demo 引导」。

主题已说清（商品 + 用途，或图文件夹等）→ 直接 `bootstrap-commercial`：`produce_init_project(create_new)`、立刻 `backlot open`、聊天必须出现 `你可以查看该网址了解详细信息：{URL}`；缺时长 / 图 / 预算再问**一句**；不推轻度、不把表 1–3 一次丢进聊天。整片时长上限 **75s**（不是单段；单段仍按渠道切，如 Pixverse ~5s）。字幕/BGM 开头不单独问，看板上标可选可后补。

**结束导出：** 看板按钮「结束并导出项目」只写 `project_export` intent；聊天备选口令精确为 `结束导出`。本机（runner 或 `produce_apply_project_export`）把 `renders/final.mp4` 拷到该项目 `exports/`，`project.json` 写 `lifecycle_status=completed`。没有成片则提示，不静默标完成。画面签收、补字幕、再出片都不算结束。已结束后不要自动对该项目 `resume`；换商品/换主题用 `create_new`。

示例接话（有主题、有 Key）：

> **可以开始出电商宣传片了。** 环境已就绪；已检测到可用视频 Key。  
> 你可以查看该网址了解详细信息：{URL}  
> （若缺一项）还差：时长 / 图片位置 / 实验预算，请回这一项。

**B. 用户明确要求轻度 / Demo，或无 Key 选了免费轻度** → 读 `references/first-run-demo.md`，出 Demo 确认卡；确认后同样必须开板并发完整 URL。

**C. 已有部分简报** → 说明卡在哪一步，只补未确认项，勿三张重头来（除非用户说改档或重来）。

### 首次 Demo 引导（仅明确要求或无 Key 退路）

**硬规则：** 不是首次默认推荐；不静默开烧；**只推荐本机已就绪的引擎**（有啥推啥）。电商与轻度退路都开板、都发完整网址。

1. 探测 `video_compose` / doctor 的 Remotion、HyperFrames 是否可用（见 `references/first-run-demo.md` §2）。  
2. 出示 **一张 Demo 确认卡**（可与就绪接话同条或紧随下一条）：

| 项 | 提案 |
|----|------|
| 档位 | 轻度（锁死） |
| 时长 | **30s（推荐）** / 10s |
| 引擎路径 | 仅列出可用项：Remotion（图表+双栏）和/或 HyperFrames（品牌渐显 logo/字） |
| 主题 | 预设（见 reference）或 AI 现拟同结构 |
| 旁白/BGM | 可后置 |

3. 用户确认「按推荐开始 / 用 10s / …」后：按 reference 写入 `production_tier=light`、`light_presentation`、`duration_seconds`、`video_plan` 等；立刻 `backlot open` 并发完整 URL → 交接 **04-produce**。  
4. Remotion 样板反推：`projects/remotion-light-showcase/`（成片 `renders/showcase-60s.mp4`）。  
5. HyperFrames 样板反推：`projects/hyperframes-jewelry-demo/`（成片 `renders/hyperframes_jewelry_20s.mp4`）。

## 出示节奏（强制）

| 步骤 | 何时出示 | 同一条消息？ |
|------|----------|--------------|
| **消息 0 · 扫 Key + 网址** | 首次且无锁定简报、默认电商 | 告知 Key 有/无；init 后必须发完整 URL；缺时长/图/预算只问一句 |
| **消息 0b · Demo 确认卡** | **仅**用户明确要轻度/Demo，或无 Key 且选了免费轻度 | 仅确认卡（+ 短脚注）；**不要**同时堆表 1–3 |
| **消息 1 · 表 1** | 电商路径上，仅当主题/档位仍缺且无法从原话锁定；完整字段写入网页 | 聊天不甩整张表 1 |
| **消息 2 · 表 2** | 表 1 字段已确认档位后 | 仅表 2（按档分支 2.1 / 2.2 / 2.3）；网页可用时聊天只问当前一项 |
| **消息 3 · 表 3** | 表 2 已确认后；**三档都出** | 仅表 3；「确认规划」后才可交接 produce |

禁止把表 1 + 表 2 + 表 3 堆在同一条回复里。Demo 确认卡确认后**不必**再走完整三表（已写入等价锁定字段）。

## 商品片：看板点选 + 聊天退路（强制）

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
2. 立即运行 `python -m backlot open <project_id>`，其中 `<project_id>` 必须是初始化工具返回的实际 ID。把命令输出的完整项目网址主动发给用户；03→04 全程复用同一网址。**无论 open 成功或超时，聊天都必须发出完整 URL**（见下条固定话术）。禁止用「看板暂不可用」「网址打不开」代替发链接。开板失败不得判为出片失败，简报与 produce 继续；看板不可用时后续决策改用完整 Grill 卡。
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
0) 严格前序阶段已是 completed；否则停在当前阶段补证据
1) 先物化本阶段 canonical artifact 及其项目内媒体路径；Backlot 显示“未挂接媒体”只表示待修复，不是合法阶段证据
2) produce_append_decision（本阶段每一项用户原话已写入）
3) 本阶段应展示的全量证据写入 checkpoint（合并写入，勿传残缺对象覆盖掉 brief/video_plan）
   - 方案确认封板至少：brief + video_plan + segment_cards（含 overall_prompt_zh 与各段文案/镜头/素材安排）
   - 另尽量带 asset_precheck；有识图则 asset_vision
4) canonical artifact 与媒体路径均可读取后，才可 produce_approve_checkpoint / produce_write_checkpoint(status=completed 或 awaiting_human)
   → 工具会合并同阶段旧 artifacts，并落盘 artifacts/*.json
5) 聊天先发封板句（禁止跳过）：
   「方案确认阶段证据已写入看板（已确认决定 + 整体方案 + 分段规划）。请刷新面板核对；确认无误后再继续。」
6) 用户有机会刷新后，再写下一阶段 in_progress 并发：
   「已进入第 N 阶段：{中文名}。…」
```

禁止：只在聊天复述方案却不写 `segment_cards` / `decision_log`；禁止用空或半截 `artifacts_json` 覆盖已有 brief/video_plan。  
面板侧：后续阶段仍保留「已确认方案档案 / 已确认决定」；点顶栏「方案确认」可回看文案规划。

商品片决定使用固定分类，禁止临时发明 category：主题/时长/渠道用 `brief_selection`，评审方式用 `review_mode_selection`，轻/中/重档用 `production_tier_selection`，候选策略用 `candidate_mode_selection`，运镜/AI 比例用 `motion_mix_selection`，素材取舍用 `asset_decision`，试片/初稿等阶段裁定用 `stage_review_decision`，最终交付确认用 `delivery_signoff`，全程审批策略用 `approval_policy`。

**只读边界：** 网页不放审批按钮、不直接写 JSON、不唤醒 Agent。用户始终在聊天中作出决定，Agent 是唯一写入者。

### 直接出片 / 快速模式 v1.0（冻结）

用户说“直接出片”时，**只能触发** `references/commercial-video-15s-review.md` §0.5 的单问题“商品片快速模式 v1.0”授权卡；该短句本身不是全程预授权，禁止立即写 `approval_policy`。

授权卡必须填入当前实际 provider/model/runtime、预估单价、总成本区间、预算基线、质量目标与分辨率，并一次讲清：自动 `assets_gate`；`sample_review` 必停；试片通过后，只有这些已披露基线及审查结果均无实质变化，才能用本次完整原话作为 `draft_review` 审批证据并自动推进 `final_compose`；任何变化或需修改即暂停；`delivery_signoff` 必停。用户回复包含 reference 给出的**完整同意语义**后，才按其中 schema 合法 JSON 示例调用 `produce_append_decision`。

完整推进、暂停条件、固定话术与回复示例以 §0.5 为唯一展开处。快速模式不允许跳过 canonical artifact、素材证据、项目 preflight、provider registry/MCP availability、试片、费用闸或付费确认，且聊天仍一次只问一个问题。

### Backlot B2 面板 intent / 快速模式 v2

商品片首轮正式选择可在 Backlot 面板勾选后点击「进入下一步」（旧称「提交待确认」）；网页只写待确认 interaction intent，不代表批准，也不得在浏览器直接 apply。主路径是网页停点：本机 runner apply 后写下一停点卡片；本轮不写推荐、不调付费生视频。聊天口令「确认面板选择」仅作退路。

聊天中**只认完全一致的口令** `确认面板选择`。`直接出片`、`好的`、`确认` 都不是面板 intent 的审批证据；其中「直接出片」仍只打开上一节 v1.0 完整确认卡，不能代替该口令。

收到准确口令后，Agent 固定按当前 checkpoint revision 执行：

```text
1. produce_list_interaction_intents
2. produce_plan_approval_bundle（使用当前 checkpoint revision）
3. 只展示 plan 返回的一份中文摘要
4. produce_apply_approval_bundle(confirm_phrase="确认面板选择")
```

`produce_plan_approval_bundle` 必须把面板 pending `decision`（同一 `intent_id`）提升为完整 §6.3 `approval_bundle`：用项目 `project.json` / `production_profile` / `artifacts/brief.json` 与面板 selections 填齐必填授权字段后再 pending→planned。禁止要求用户或网页直接 POST 审批包。项目证据不足、plan/apply 失败、revision drift 或 intent expired 时**不得 apply**，应回退现有完整 Grill 确认卡，一次只问一个问题。用户也可退回 B1 copy-summary（文案摘要）逐项确认。

若 intent 列表为空，同样不得 apply，回退 Grill。

新的商品片快速授权统一写 `selected="fast_track_v2"`；记录选项时用 `option_id="fast_track_v2"`，后续 checkpoint metadata 的 `approval_source` 也写 `fast_track_v2`。已有项目中的 `fast_track_v1` 继续按历史协议只读并保持有效：禁止改写历史，也不得仅因 v2 上线要求用户重新授权。

v2 仍遵守既有硬门：网页只读、聊天一次只问一个问题、不静默付费、不静默换渠道/模型，所有生成图必须经过用户审查。完整 evaluate 推进规则见 reference §0.5.1 与 04-produce「快速模式 v2（执行）」。

## 商品片 ↔ 七阶段（强制对照）

管线：`pipeline_defs/bootstrap-commercial.yaml`。面板顶栏七阶段与 Skill 职责如下。  
**原则：** 底层仍是七阶段证据名。对人展示的停点由 `production_profile.review_mode_preset` 决定（见 `lib/review_interrupt.py`）：极简三停、普通五停、专业七停。聊天仍一次确认一项；面板只画当前档位的确认停。

| # | 阶段（Backlot） | Skill | 原「表」落点（对用户可改叫法） | 面板展示 | 聊天 |
|---|-----------------|-------|--------------------------------|----------|------|
| 1 | `brief_locked` 方案确认 | **03** | 三点卡 → 主题/档位/时长/预算/评审（旧表1）→ 按档细化（旧表2）→ 比例卡 → 表 3 前覆盖矩阵 → **分段规划全文（旧表3）** | 方案摘要、缺口四选（图够则下一步；不标推荐）、费用、`video_plan`；点同意锁定计划，本页不展示生成结果 | 网页主路径；口令退路 |
| 2 | `assets_gate` 素材检查 | **03** | 按已确认计划完成补传/I2I/显式复用/降级；生成图审查是本阶段内部子闸 | 已存在图片写 `asset_ledger.entries`；I2I 生命周期写 `planned_entries`；展示候选、复用范围与 unified matrix；**不显示视频** | 所有档位/评审方式均确认生成图；普通可批量，专业逐张；完成后才交接 04 |
| 3 | `sample_review` 试片确认 | **04** | — | 试片成片、费用 | **普通/专业**停；**极简不展示、不等人审** |
| 4 | `segment_build` 分段制作 | **04** | — | Beat 胶片、**镜提示词全文**、候选/抽帧（专业） | 专业：分批审查；普通/极简：少打断 |
| 5 | `draft_review` 初稿审查 | **04** | — | 初稿、问题片段、修改清单 | **普通/专业**停；**极简自动过**（技术/费用失败除外） |
| 6 | `final_compose` 合成终稿 | **04** | — | 合成进度/技术检查 | 一般不强制问 |
| 7 | `delivery_signoff` 交付确认 | **04** | — | 终稿合集、质量与累计费用 | 最终签收（三档都停） |

**极简执行（强制）：** `review_mode_preset=minimal` 时，04 在 `assets_gate=completed` 后直接生成正式第一段（不是额外试片）。用 `produce_probe_media` 做技术闸；费用闸、空 Key、生成失败 → 暂停回聊天。禁止假装机器已审「好不好看」。

**方案确认阶段内的推荐推进顺序（弹性）：**

```text
三点卡（若适用）
→ 主题与目标是否正确
→ 档位
→ 时长（缺则问一句）；评审默认普通，不主动推销专业；用户说「直接出片」才走快速模式授权
→ 实验预算（¥8+ 须主动确认）
→ 按档：轻度表现 / 中度素材源 / 重度渠模
→ （启用 AI 视频时）运镜:AI 比例
→ 素材扫描并输出「beat × 所需画面 × 候选图片」覆盖矩阵；每张上传图归 used/reuse_pending/unused 并写原因
→ 每个缺口只确认：补传 / I2I / 显式复用 / 降级或不补；无可用 image provider 时 I2I 标不可执行且不推荐
→ 分段规划（旧表3）全文进面板 → 聊天「确认规划」→ brief_locked/awaiting_human
→ brief_locked=completed 后进入 assets_gate，执行补图与审图闭环
→ assets_gate=completed 后才交接 04
```

允许跳过已从用户原话锁定且用户刚确认过的项，但**禁止**跳过：档位、重度渠模、规划确认、覆盖矩阵、素材主图缺口关闭、生成图审查与 `assets_gate=completed`。评审默认普通；专业仅用户主动要。

非商品片（用户明确要讲解/Demo）：仍可用完整 Grill「表 1→2→3」话术；不强制七阶段商品板。默认「做个视频」走电商，不走本句。

### 首次商品三点确认卡（缺啥问一句 · 勿机械甩三点）

主题已说清时：**先 init + 开板给网址**，不要直接抛出表 1 或一整套方案。已从用户原话锁定的项预填并跳过；只问仍缺的时长 / 图 / 预算中的**一句**。三点卡仅在这三项都还没锁、且需要一次对齐商品理解时使用。

**极简需求：** 表 1 字段仍写入网页证据；聊天不甩整张表。付费 AI 镜描述的写法在 **04-produce** 强制读 `openmontage-seedance-prompt`，本 Skill 不扩写镜提示词。

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
4. 三点中，已从用户原话明确的信息预填并跳过；不要为了走完三点再问一遍。未锁定的项才进聊天。

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
缺的**不要连环追问、不要一次甩表 1–3**。主题已清时只问缺的时长/图/预算中的一句。内部仍按表 1 默认填满未锁定字段，再请用户改。整片上限 **75s**；用户提出超过 75s 时说明上限并请改到 ≤75，禁止写入更大值。

### 2. 消息 1 — 表 1（主题 + 档位）

对用户**必须**用 Grill 确认卡（见上），不要只贴内部表。内部对照字段如下：

| 点 | 提案 | 状态 |
|----|------|------|
| 主题 | （已有则照写；否则先给 2–3 个候选再填入选定） | 默认可改 |
| 档位 | 轻度 / 中度 / **重度（商品宣传推荐）** | **必选** |
| 时长 | 默认 30 秒（竖屏短视频可建议 15–30；商品试片常 10/30） | 默认可改；**整片上限 75s**（不是单段）；**≥15s** 须出示评审模式选项 |
| 实验 API 预算 | 微额 ¥1 / 轻量 ¥3 / 经济 ¥5 / **标准 ¥8（默认）** / 充裕 ¥12 | 重度或商品片出示；**¥8 及以上须主动询问确认**；&lt;¥8 仅提示；**非售价** |
| 评审模式 | **普通（默认，快）** / 专业（须用户主动要） | 默认普通，写入 `review_mode=normal`；聊天不主动推销专业；用户明确说「专业 / 逐段审」再切 |

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
5. 评审模式：普通（默认，快）。专业须你主动要，本卡不推销。
补充说明：
1. 实验 API 预算 = 本任务调用模型的费用上限，不是成片售价；选 ¥8 或 ¥12 需你明确确认。
2. 默认普通评审 + 快速模式（仅当你说「直接出片」才授权）。专业模式（总览表、分批逐段）须你主动要；网页可标「可切专业」。
3. 旁白默认推荐 Edge-TTS，可后置；付费视频渠道要等确认「重度」后才出现。
示例回复：
1. 主题按提案
2. 我选择重度
3. 时长 20s
4. 我确认预算 ¥8
5. 我确认普通（或：我要专业）
```

**表 1 短脚注（Agent 自用 · 可并入补充说明）：**

1. 第一次使用建议先生成 **10s–30s** 以内；熟悉后再做 45s–75s；**整片上限 75s**（不是单段；单段仍按渠道切）。  
2. 本轮主流程**先定视频**；旁白与 BGM **可以后置**（开头不单独问）。  
3. 付费视频渠道/模型**仅在选重度之后**才出示。  
4. 选 **¥8 或 ¥12** 必须**主动询问**确认；首次达标成本含被拒候选。  
5. ≥15s 商品：默认普通；**禁止**把专业说成推荐默认；用户主动要专业再切。  
6. 确认本表字段后**另开消息**出示表 2（或网页下一项）；重度锁渠模后、表 3 前另出比例卡。

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
- **首次短 demo：** 仅用户明确要求或无 Key 退路时读 `references/first-run-demo.md`。

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

**项目计划预检（只读硬门）：** 将候选渠模、每段 `t2v|i2v` 与图源先物化到当前项目简报草案后，在最终锁定或恢复渠道前调用 `produce_provider_preflight(project_id)`。它只检查项目计划、Pixverse 模式/图源、OSS 和项目授权证据，**不检查** `TOKENHUB_API_KEY` / `AGNES_API_KEY` 或 provider 在线可用性；渠道可用仍须另查 provider registry / 对应 MCP availability。`ready=false` 时只展示项目证据 blockers 并一次问一个问题，不得锁定或开烧。Pixverse 只提供 **T2V/I2V**，不提供 T2I/I2I；商品缺图由 Agnes / Flux / DashScope / OpenAI / Kling / Google / Grok 等**已配置 image provider**完成。若成图随后选作 Pixverse 本地图 I2V 参考图，才进入 OSS 暂存门，详见 3.3.1 与 04「项目计划、Pixverse 与 OSS 预检」。

**推荐规则：**

- 只列出已填 Key 且可出片的渠道/模型；无 Key 的标灰不可选。  
- 固定顺序：Agnes → TokenHub·混元 → TokenHub·Pixverse。默认取清单里**第一个已填 Key** 的项（不再按「两家都有则必须 Agnes」单独分支，效果上 Agnes 仍排第一）。  
- **无任何可用视频 Key** → **不**出示「假可用」表；提示：先补 Key（`06-providers` / `.env-example`），或**改档**到轻度/中度。禁止假装能烧重度。  
- 看板已锁定 `video_model` 时，聊天退路不得重出本表，除非用户明确要求改选。  
- 能力说明只给一行、可折叠；片长由模型能力决定，超长自动拼接。不在本表让用户选手动秒数。OSS 不进本表，需要时在素材步再问。

**表 2.3 Grill 卡示例：**

```text
请确认选择以下点
1. 视频渠道：Agnes（付费视频渠道，默认推荐）
            / TokenHub·混元（腾讯混元，约720p，无自定义时长）
            / TokenHub·Pixverse（腾讯 Pixverse，可设时长，默认5s/360p/无声）
2. 模型：随上项锁定
   - Agnes → agnes-video-v2.0
   - 混元 → hy-video-1.5
   - Pixverse → pixverse-video-v6.0
补充说明：
1. Agnes 与 TokenHub 是两条独立付费渠道；TokenHub 下混元与 Pixverse 共用 TOKENHUB_API_KEY，但接口/模型不同，不要混叫。
2. TokenPlan 是 Agnes 账号的付费/并发档（不是渠道）；有 TokenPlan 档时 Agnes 并发通常更高。
3. TokenHub·混元：约 720p、默认一次一段、无自定义时长；长片靠多段拼接；本地图可用 base64。
4. TokenHub·Pixverse：可设每段 duration（默认 5s）、quality（默认 360p）、`generate_audio_switch`（默认无声 `false`）；图生需公网图片 URL，或按 3.3.1 在当前项目明确授权后临时上传项目内本地图。要有声或更高清须用户明确说。
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
| TokenHub·Pixverse（可设时长） | `tokenhub` | `pixverse-video-v6.0` | 同 Key；可写 `video_duration_sec`/`video_quality`/`video_generate_audio`/`aspect_ratio`；默认 5s/360p/无声；I2V 需公网 URL，或经本项目明确授权后把项目内本地图临时传 OSS |
| eRouter | — | — | ❌ 未实现，勿当可烧 |

写入：`ai_video=enabled`；`video_channel`；`video_model`；选 Pixverse 时可写 `video_duration_sec`（默认 5）、`video_quality`（默认 `360p`）、`video_generate_audio`（默认 `false`）、`aspect_ratio`（如 `16:9` / `9:16`）。  
非重度：`ai_video=disabled`；渠/模为空。

#### 3.3.1 Pixverse 本地图临时上传（可选阿里云 OSS）

触发条件：候选或已锁定 `video_model=pixverse-video-v6.0`，某个 **I2V** beat 使用本项目 `assets/images/` 内的本地图。Pixverse T2V、Pixverse 公网图 I2V、Agnes 均不需要 OSS。

1. 先调用只读 `produce_provider_preflight(project_id)`。只有返回 `oss_required=true` 的 Pixverse 本地图 I2V 才检查 OSS 与本项目授权；不得因机器已有 OSS 配置就自动上传。
2. **03 只确认并记录，不上传。** 聊天一次只问：
   > Pixverse 图生需要公网 URL。是否允许本项目把所选图片临时上传到你的私有阿里云 OSS，生成默认 6 小时签名 URL，生成结束后尽量删除？Secret 和签名 URL不会进入看板。
3. 用户明确同意后，用 `produce_append_decision` 写入当前项目：
   - `category="asset_decision"`
   - `subject="Pixverse local image temporary OSS upload"`（之后变更必须保持同一 subject）
   - `options_considered` 至少含 `option_id="approved"` 与 `option_id="denied"`，每项按 schema 写 `label/score/reason`
   - 严格三项批准证据必须同时成立：`selected="approved"`、`user_approved=true`、非空 `user_response_text`（用户原话）。
4. 只认当前 `project_id` 的最新同 subject 决策；新项目不得继承旧项目授权。用户撤销时追加 `selected="denied"`，不得改写旧记录。
5. OSS 未配置时交接 06。用户配置后须重启/刷新 MCP，再次调用 preflight 复检 **OSS readiness**；`ready=true` 仍不代表 Key/provider 在线可用。另查 registry/MCP availability 后恢复原 checkpoint 阶段，不重走表 1–3、不自动越级，也不因配置存在而自动上传。
6. 用户拒绝时可继续用公网 `image_url`；若要改 Agnes / 混元，按换渠协议重新确认，禁止静默切换。
7. 授权不是全局开关。04 每次本地图调用仍须显式传 `project_id` 与 `user_authorized_upload=true`；工具层默认拒绝。

#### 3.4 画面构成比例（运镜:AI · ≥15s 且可烧 AI 时）

**触发：** `duration_seconds >= 15`，且（重度已锁视频 Key / `ai_video=enabled`，或商品片明确要用付费视频生成）。  
**时机：** 表 2.3（或等价渠模）确认之后、**表 3 之前**单独一条消息；对用户用 **Grill 确认卡**。普通与专业都要出示。  
**网页已锁定：** 若看板已写入 `video_model` 与 `motion_mix` / `ai_share_pct`，聊天退路**不得**再出表 2.3 与本比例卡，除非用户明确要求改选。

| 选项 | 运镜:AI生成 | AI生成视频约占 | 说明 |
|------|-------------|---------------|------|
| A | **0:1** | **~100%** | **默认**；几乎全模型生成。具体生成情况视模型能力而定 |
| B | 1:2 | ~70% | 可选；更动感 |
| C | 1:1 | ~50% | 可选，**不作为推荐** |
| D | 2:1 | ~30% | 仅用户主动要更省时才提 |

**Grill 卡要点示例：** `1. 画面比例：A 100%（默认）/ B 70% / C 50%（可选）`

**规则：**

1. 比例是**推荐目标**，按整片 **AI 模型生成时长合计** 大概符合即可（约 ±10%–15%）；beat 怎么切可自由安排，**不按段数硬凑**。  
2. 审查中用户可把某段从运镜改成 AI（或反过来）；**终稿不强制贴死**原比例。  
3. 无可用视频 Key：不出本卡；提示补 Key 或改档。  
4. 写入：`motion_mix`（`0:1`/`1:2`/`1:1`/`2:1`）、`ai_share_pct`（`100`/`70`/`50`/`30`）、`motion_mix_source`（`default_recommend`|`user_selected`）。未改选 → `0:1` + `ai_share_pct=100` + `default_recommend`。  
5. 对用户只说「具体生成情况视模型能力而定」，不要主动讲费用或商品不像。

### 4. 消息 3 — 表 3（分段视频规划 · 三档都出）

#### 4.1 触发

表 2 已确认后，**轻度 / 中度 / 重度均必出**表 3。

用户若无现成文案：Agent **直接生成一版**分段提案供过目；用 **Grill 确认卡**（点：确认规划 / 改某段）；回复确认后锁定。禁止未确认就开烧付费视频。

#### 4.2 重度商品（强制）

若主题/用途为**商品宣传、种草、详情展示、产品佩戴演示**等（含**重度商品**）：

1. **必须先读**本目录 `references/product-prompt-template.md`。  
2. **必须再读** `references/asset-preprocess-gate.md`，先输出 `beat × 所需画面 × 候选图片` 覆盖矩阵；总张数够不代表段覆盖或关键角度够。每张上传图必须归 `used` / `reuse_pending` / `unused` 并写原因。
3. 每个缺口只允许四选：补传、I2I、显式复用、降级/不补。I2I 不是默认项；无当前可用 image provider 时标“不可执行”且不推荐。**禁止把 Pixverse 或 video provider 当图片生成器**。
4. 表 3 写入已确认的缺口动作，但此时只规划 I2I、不生成：缺图 Beat 写 `gap_fill="i2i"`、`assignment_status="i2i_planned"`、`planned_output_path`、provider/model，`ref_image` 可省略。用户确认表 3 并完成 `brief_locked` 后，进入顶层 `assets_gate` 执行补图、候选重试、审图与复用授权。
5. 生成图确认是 `assets_gate` 内部子闸，不是第八阶段。所有档位、普通/专业/快速模式均须用户审图：普通可一次批量确认全部候选；专业逐张确认并可逐张重生成；快速不能绕过。
6. 未经 `approved` 的生成图不得写入 `ref_image`、不得当实际素材、不得进入试片或 video generation。`assets_gate=completed` 前不交接 produce。

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
4. 商品片：已按 `product-prompt-template.md` 与 `asset-preprocess-gate.md` 输出覆盖矩阵并确认四选一缺口计划；表 3 确认后仍须完成 `assets_gate` 生成/审图闭环。
5. **可交付硬门槛**：商品身份一致、无结构断裂、流畅可播且动态不单调。AI 动态秒数是**实验/推荐目标**（由 `motion_mix` 推导整片 AI 总秒数，±约 15% 即可），**不是**单独否决成片的硬门槛。  
6. 出片顺序：先 **10–15s 试片** 确认，再全长；普通模式只展开问题片段（可说「切专业」看逐 beat）。  
7. 已锁 `motion_mix` 时：表 3 按推荐 AI 总秒数**大概**排布；审查中可改某段方式，允许终稿偏离比例。
8. `assets_gate=completed` 是交接 04 的硬门禁；确认规划不等于确认复用或生成图。

若已锁比例：排表前用 `recommended_ai_seconds(duration, motion_mix)` 或等价心算，避免有 Key 却几乎全是运镜。

### 5. 全部确认后写入并交接

适用：表 1 + 表 2 + 表 3 均已确认。

步骤：

1. 安装未闭环 → installer。  
2. 未 `verify_ready` → setup。  
3. 复查表 1 前 `produce_init_project` 返回的实际项目 ID；商品片此处禁止再次初始化。非商品片若尚无项目，也默认 `mode=create_new`；只有用户明确续作时才用 `mode=resume`。若 `project.json` 已是 `lifecycle_status=completed`，禁止当续作，必须新开项目。
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
  motion_mix="0:1",             # 0:1|1:2|1:1|2:1；默认 0:1（约 100% AI）
  motion_mix_source="default_recommend",  # default_recommend|user_selected
  duration_seconds="30",        # 写入以便推导 AI 秒数带
  style_label_zh="",            # 可选中文名：高端极简/生活方式/电商清晰展示
  style_playbook=""             # 可选内部 styles id；勿强制第四表
)
```

商品/重度未明示预算时：**默认** `api_budget_tier=standard`、`budget_cny=8`，且须**主动询问确认**（¥8+）。  
未明示评审模式时：**默认** `review_mode=normal`。  
未明示候选策略时：**默认** `candidate_mode=adaptive`（禁止默认双候选）。  
未明示画面比例且已触发比例卡：默认 `motion_mix=0:1`、`ai_share_pct=100`、`motion_mix_source=default_recommend`，并向用户念清配置。50% 只作为可选项，不作为推荐。

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
| `motion_mix` | `0:1` / `1:2` / `1:1` / `2:1`（推荐目标，软约束；默认 `0:1`） |
| `ai_share_pct` | `100` / `70` / `50`（看板步进可为其它 10% 档；默认 `100`） |
| `motion_mix_source` | `default_recommend` / `user_selected` |
| `motion_target_band` | `30s_ref` / `60s_cost_ref` / `60s_high_motion`（可选；有 mix 时以 mix 为主） |
| `light_presentation` | 轻度表现方式（含 `remotion` / `hyperframes`）；非轻度可空 |
| `first_run_demo` | 可选；首次 Demo 确认卡路径为 `true` |
| `medium_source` | `stock` / `user_assets`；非中度可空 |
| `ai_video` | 重度且已锁渠模 → `enabled`；否则 `disabled` |
| `video_channel` | `agnes` / `tokenhub` / …；非重度空 |
| `video_model` | 模型 id（如 `agnes-video-v2.0` / `hy-video-1.5` / `pixverse-video-v6.0`）；非重度空 |
| `video_duration_sec` | 可选；Pixverse 每段秒数，默认 `5` |
| `video_quality` | 可选；Pixverse 画质，默认 `360p`（`360p` / `540p` / `720p` / `1080p`） |
| `video_generate_audio` | 可选；Pixverse 原生平音频，默认 `false`（无声）。`true` 才传 `generate_audio_switch=true` |
| `aspect_ratio` | 可选；如 `16:9` / `9:16`（Pixverse T2V） |
| `video_plan` | 表 3 分段规划；商品片须含切段/重点段、`asset_classes`、`path`、`gap_fill`。已有批准素材的 Beat 写真实 `ref_image`；I2I 缺图 Beat 先写 `assignment_status="i2i_planned"`、`planned_output_path`、provider/model，审图 approved 前 `ref_image` 可省略 |

6. 商品片 `brief_locked` 最终 checkpoint 的 `artifacts_json` 必须包含 `brief`、`asset_precheck`、`video_plan`、`segment_cards`；其中分段素材计划必须与表 3 前 unified matrix 一致。缺少完整 `segment_cards` 时工具会拒绝封板。
7. `approval_text` 用用户确认表 3 的原话（禁止编造）；完成 `brief_locked` 后进入现有第 2 阶段 `assets_gate`，不得直接交接 04。
8. 按 `references/asset-preprocess-gate.md` 写 canonical `asset_ledger`，执行已批准的补传/I2I/显式复用/降级。I2I 必须先探测并锁定 provider/model，完整记录 `planned→generating→ready/review_pending→approved|rejected|failed`、`candidate_paths`、`retry_count`、`decision_id` 与真实 `output_path`；审图 decision 由工具写入当前文件 `asset_sha256`，同路径内容变化须重新审图。
9. 对生成图执行用户审查：普通可批量确认，专业逐张确认，快速模式仍须确认。复用决定绑定当前 `project_id`、`stage=assets_gate`、精确 `asset_path + beat_ids` 与用户原话；未批准保持 `reuse_pending`。
10. 重新计算 unified matrix。存在 `missing` / `orphan` / `reuse_pending` / `review_pending` / provider/model 缺失 / 文件缺失时，保持当前阶段并继续处理；全部关闭后才写 `assets_gate=completed`。
11. 商品片调用 `python -m backlot open <project_id>` 复用原网址；向 04 交接 `project_id`、网址、已完成 checkpoint 与 canonical artifacts，不要求用户另开页面。
12. 仅在第 10 步成功后交接 **`openmontage-bootstrap-04-produce`**。字幕/BGM → `05-captions-music`（后置，不挡画面）；失败 → `07-error-handling`。

**闸门：** 表 2 / 表 3 未确认或 `assets_gate` 未 `completed` 时，**禁止**交接 produce、禁止开始 sample 或任何视频生成。

### 6. 改档

须用户明确说「升到中度 / 升到重度 / 改回轻度」或「改档」。  

- **不要**只改 `production_tier` 数字完事。  
- 内部重锁 **表 1（至少新档位）→ 表 2 → 表 3** 字段包，再写回简报；聊天仍一次一项，不甩三张大表。  
- 从轻度/中度升到重度：必须重新走表 2.3（Key 闸门）与表 3。  
- 从重度降档：清空或停用 `ai_video` / 渠模，并重出对应表 2 与表 3。

## 商品片素材需求与中文状态

商品宣传片采用两段式素材协议：

1. **表 2 后、表 3 前**：扫描、分类，并输出 `beat × 所需画面 × 候选图片` provisional unified matrix；每张上传图归 `used` / `reuse_pending` / `unused` 并写原因。
2. **表 3 确认后、交接 04 前**：在七阶段第 2 阶段 `assets_gate` 执行补传/I2I/显式复用/降级和生成图审查；不新增顶栏阶段。

图片数量只用于提示，不能代替 Beat 覆盖和关键角度覆盖。允许复用，但未绑定精确路径、Beat 集与用户原话时只能是 `reuse_pending`。

**操作细则与 schema-valid 示例（必读）：** `references/asset-preprocess-gate.md`
**提示词词库（写 AI 视频镜）：** `references/commercial-prompt-lexicon.md`
**写视频镜提示词：** 在 `04-produce` 付费 AI 段强制读 `openmontage-seedance-prompt`；I2I 图片 prompt 则严格来自对应 Beat 已确认的 `copy_plan_zh`、`shot_plan_zh`、`asset_plan_zh` 和 source image。
**扫描入口：** 先调只读 `produce_scan_user_images(project_id)`；有识图 Key 且符合授权边界时可调 `produce_describe_user_images(project_id)`。两者都不能代替用户分类和审图。

### 固定缺口与审图规则

1. 缺口只允许：**补传、I2I、显式复用、降级/不补**。
2. 无可用 image provider：I2I 标不可执行，不推荐；禁止用 Pixverse/video provider 生图。
3. I2I 先探测并锁定 provider/model，再写 `planned_entries`；换渠模须重新确认。
4. I2I 状态固定：`planned→generating→ready/review_pending→approved|rejected|failed`。必须记录 candidates（`candidate_paths`）、`retry_count`、`decision_id`、最终 `output_path`；真实输出只落 `assets/images/`。`ready` 不能代替审图批准。actual 生成图和 `status="approved"` 的 planned 生成图必须 `candidate_paths` 非空；批准输出必须属于 `candidate_paths`，所有候选路径均须位于当前项目内，批准输出文件必须是真实可解析图片。
5. 普通模式一次批量审全部候选；专业模式逐张审并可逐张重生成；快速模式不能绕过。审图 approved 后才把真实批准 `output_path` 写入 `ref_image` / actual ledger；此前不得进入 sample/video generation。
6. `generated` / `t2i` / `text_to_image` / `i2i` / `image_to_image` / `ai_generated` 均按生成图强校验。actual 与 approved planned 都要求 provider、model、项目内真实 path/output、`review_status="approved"` 和审图 `decision_id`；该 `decision_id` 必须命中当前 `decision_log` 中唯一真实项，且当前 `project_id`、`stage="assets_gate"`、`category="asset_decision"`、`selected="approved"`、`user_approved=true`、非空用户原话、`asset_path` / `subject`、`asset_sha256`、`beat_ids` 与批准输出及 entry 精确一致。后续同路径同 Beat 范围的撤回即使 subject 漂移也使旧批准失效；planned 未 approved 时可有计划 decision_id，但不把它解析为审图批准；来源声明冲突即拒绝。
7. 每个 planned image 必须声明唯一来源；出现计划输出、实际输出、候选、provider/model 或任何生成链状态时，省略来源也按生成图强校验。closed `video_plan` 中已有 `ref` / `ref_image` 必须与矩阵同 Beat 的唯一批准路径一致。
8. `assets_gate=completed` 前扫描 `assets/images/` 全部真实图片并与 ledger 的 actual/planned/source/candidate/output 路径双向对账；拒绝未登记图片和账本引用的伪图片，unused actual 必须写原因。只要 decision log 存在，其 `project_id` 就必须匹配当前项目；多份日志只接受同一追加前缀，分叉、重复冲突 ID 或陈旧批准均拒绝；无决定且文件不存在可省略。
9. `assets_gate=completed` 只在 unified matrix 没有 `missing`、`orphan`、`reuse_pending`、`review_pending`、provider/model 缺失、文件缺失或矩阵漂移时写入。

### Advisory 数量参考（非闭环判定）

| 目标时长 | 最低提示 | 建议提示 | 常见覆盖 |
|----------|----------|----------|----------|
| 10 秒 | 1–2 张 | 2–3 张 | 主图、第二角度或细节 |
| 30 秒 | 2–3 张 | 4–6 张 | 主图、多个角度、细节、佩戴/使用 |
| 60 秒 | 3–4 张 | 6–10 张 | 主图、正侧背、细节、佩戴/使用、包装/场景 |

至少一张清晰商品主图（`product_hero`）。其它角色：`product_angle`、`product_detail`、`on_body` / `in_use`、`packaging`、`lifestyle`、`background`。重复同构图不增加有效角度覆盖。用户可见汇总仍用中文：**就绪 / 降级继续 / 等待用户选择**；机器状态只写 schema/实现支持的值。

### Backlot 边界

- 方案确认页展示预检与 provisional matrix；表 3 仍不展示未生成媒体。
- 素材检查页按 Beat 展示用户图、planned entries、候选与审图状态；只显示图片，不显示视频。
- 生成文件真实落盘后才显示缩略图；`planned_output_path` 不能伪装实际文件。
- 完整证据写入 `asset_precheck`、`asset_ledger`、`video_plan`、`segment_cards`、`decision_log`；用户在聊天决定，网页只读。

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

- 用户说「生成视频」且环境已就绪、无锁定简报时：已调用 `scan_video_keys`（未打印 Key 值），**默认电商宣传片**；已发完整 Backlot URL；未明确要求时**未**先推轻度 Demo；评审默认普通，未推销专业  
- 无 Key 时已告知有/无，并给出二选一（填 Key 或这次免费轻度）  
- 主题已清时未把表 1–3 一次丢进聊天；缺时长/图/预算只问了一句；整片未超 75s  
- 用户明确要求 Demo / 无 Key 选轻度后：已读 `references/first-run-demo.md`，确认卡后已开板给网址并交接 04，**未**静默开烧  
- 缺步时已按「缺步路由」交接 01/02，未越级开烧  
- 完整简报路径：用户确认过 **表 1**（主题 + 档位 + 时长；商品/重度含实验 API 预算默认 ¥8 且 ¥8+ 已主动询问；评审默认普通，未把专业当推荐）  
- 按档确认过 **表 2**；轻度互斥单选（含 Remotion/HyperFrames，按可用性推荐）；中度遵守 Stock Key 闸门；重度遵守视频 Key 闸门与推荐规则  
- **≥15s 且可烧 AI** 时已确认 **画面构成比例**（或已说明无 Key）；已说明比例为推荐软约束  
- **表 3** 三档都已确认（Demo 卡路径除外）；无全文旁白强求；无文案时已给 AI 提案并获「确认规划」；已说明硬门槛与推荐 AI 秒数目标  
- 商品片已强制走 `product-prompt-template.md` 与 `asset-preprocess-gate.md`；表 3 前已展示 Beat 覆盖矩阵，每张上传图均有归宿和原因
- 缺口仅使用补传/I2I/显式复用/降级不补；无 image provider 时未推荐 I2I，未把 Pixverse/video provider 当生图
- 复用批准已绑定当前项目、`assets_gate`、精确路径与 Beat 集；I2I 已锁 provider/model，候选、重试、决定和真实输出路径可追溯
- 所有档位/评审模式中的生成图均获用户批准；普通可批量、专业逐张、快速未绕过
- unified matrix 已关闭全部开放状态并成功写入 `assets_gate=completed`，之后才交接 04
- 已写 `production_profile`（含 `api_budget_tier`/`budget_cny`/`review_mode`/`candidate_mode`/`motion_mix`）与 `video_plan` 等扩展字段  
- 未在轻度/中度展示付费视频渠模；无 Key 时未假装可烧重度  
- 未静默换渠、未静默 I2I、未跳过确认开烧  
- 未把实验 API 预算说成售价；未默认开启双候选  
- 未把 `motion_mix` 当成终稿硬门槛；未在有 Key 时默认把表 3 排成几乎全运镜
