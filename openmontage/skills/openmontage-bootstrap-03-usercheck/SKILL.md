---
name: openmontage-bootstrap-03-usercheck
description: >-
  BootStrap brief before produce: Table 1 (theme + tier), Table 2 (tier branch:
  light presentation / medium stock|assets / heavy paid video channel+model),
  Table 3 (segment video_plan for all tiers). Writes production_profile +
  artifacts, then hands off to produce. Narration/BGM deferred.
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

# openmontage-bootstrap-03-usercheck（成片简报 · 用户确认）

## Scope

**做：** 需求不清时先对齐**主题与档位**，再按档细化（表 2），再确认**分段视频规划**（表 3）。全部确认后写入 `production_profile` / 简报 artifacts，交接 `openmontage-bootstrap-04-produce`。

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

当安装闭环已通过且 `verify_ready` 为真（或等价 ready），用户说「生成视频」类话术时，**先**用类似接话（可略改，勿省略要点）：

> **可以开始出片了。** 环境已就绪。  
> 接下来分三步和你确认：**① 主题与档位 → ② 画面方式 → ③ 分段规划**。  
> 旁白**默认推荐** Edge-TTS 男声，可以画面做好再加；字幕与 BGM 也可稍后。  
> 我先出 **表 1**，你确认后我们再往下。

若用户此前只完成 01/02、从未走过 03：仍用上述接话，**不要**假设已有简报。

若简报已部分确认（例如只有表 1）：接话改为说明**卡在哪一步**，只补未确认表，勿三张重头来（除非用户说改档或重来）。

## 出示节奏（强制）

| 步骤 | 何时出示 | 同一条消息？ |
|------|----------|--------------|
| **消息 1 · 表 1** | 始终先出 | 仅表 1（+ 短脚注） |
| **消息 2 · 表 2** | 表 1 已确认档位后 | 仅表 2（按档分支 2.1 / 2.2 / 2.3） |
| **消息 3 · 表 3** | 表 2 已确认后；**三档都出** | 仅表 3；「确认规划」后才可交接 produce |

禁止把表 1 + 表 2 + 表 3 堆在同一条回复里。

## Hard protocol

### 1. 收集已知项

从用户话提取：主题、时长、用途、自带素材等。  
缺的**不要连环追问**；用表 1 默认填满再请用户改。

### 2. 消息 1 — 表 1（主题 + 档位）

**表 1 — 主表**

| 项 | 提案 | 状态 |
|----|------|------|
| 主题 | （已有则照写；否则先给 2–3 个候选再填入选定） | 默认可改 |
| 档位 | 轻度 / 中度 / 重度（见下方说明表） | **必选** |
| 时长 | 默认 30 秒（竖屏短视频可建议 15–30；商品试片常 10/30） | 默认可改 |

**档位说明（出示给用户）**

| 档位 | 擅长 | 效果 | 需要 |
|------|------|------|------|
| 轻度 | 简单技术讲解，如现象动画解说、技术讲解 | 由提示词、文案、提供的素材编排决定 | 项目本身配置即可，下载完依赖即可使用 |
| 中度 | 风景、人物展示解说，如自然风光讲解 | 尤其受 **Pixabay** 与 **Pexels** 素材影响 | 需获取 Pixabay / Pexels Key 并配置（也可用自带素材） |
| 重度 | 较精致复杂展示，如商品宣传、电商详情 | 由视频模型、提示词、文案决定 | 需获取视频模型 Key 并填入 |

**表 1 短脚注（必写）：**

1. 第一次使用建议先生成 **10s–30s** 以内；熟悉后再做 45s–60s；**不建议超过 60s**（越长越慢，也更易报错）。  
2. 本轮主流程**先定视频**；旁白与 BGM **可以后置**。旁白**默认推荐** Edge-TTS 男声（`zh-CN-YunyangNeural`），不在本表强制选定。  
3. 付费视频渠道/模型**仅在选重度之后**才出示。  
4. 确认本表后，将**另开消息**出示表 2。

**首句话术（必用）：**

> 先看表 1：确认主题与档位（轻度 / 中度 / 重度）。  
> 首次建议时长 10–30s。旁白默认推荐 Edge-TTS，可后置；BGM 稍后。选重度后才会出现付费视频渠道选项。

主题没有时：在贴表前或表内注明 2–3 个候选，等用户选后再定「提案」。

### 3. 消息 2 — 表 2（按档分支）

表 1 确认后，**单独一条消息**只出示对应该档的表 2。未完成表 2 确认前，不出表 3、不交接 produce。

#### 3.1 轻度 — 表 2.1 表现方式（互斥单选）

| # | 选项 | 说明 |
|---|------|------|
| 1 | 静态图片 | 少图/单图 + 字幕卡 |
| 2 | 多图顺序轮播（可带文案） | 多张图按序切换，可叠文案 |
| 3 | 动态文字解说 | 以文字动效为主 |
| 4 | Remotion 动画 | 效果较好，可能更耗时；**可标推荐** |

用户必须只选 **一项**。确认后进入表 3。

**表 2.1 脚注（Remotion 行）：** 选 **Remotion 动画** 时，规划 cut 组合、60s 分段与渲染路径见 `references/light-remotion-showcase.md`（仓内样板 `projects/remotion-light-showcase/`）。

写入字段建议：`light_presentation` = `still` / `image_carousel` / `motion_text` / `remotion`。

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

**仅当表 1 档位=重度时出示。** 轻度/中度禁止出示本表。

检测视频渠道 Key：**仅** `AGNES_*`、`TOKENHUB_*`（及日后文档标明已接线的渠道）。`FAL_KEY` 等**不**单独作为本产品重度主渠闸门，除非另有约定。eRouter 视频仍 **planned** 时标 ❌，勿当可烧。

**推荐规则：**

- 只列出已填 Key 且可出片的渠道/模型。  
- 若 Agnes 与 TokenHub **都有 Key** → 默认推荐 **Agnes**，并写清差异（如并发、分辨率）。  
- 仅一家有 Key → 推荐该家，仍须用户确认。  
- **无任何可用视频 Key** → **不**出示「假可用」表；提示：先补 Key（`06-providers` / `.env-example`），或**改档**到轻度/中度。禁止假装能烧重度。

**表示例：**

```text
已检测到可用 Key。请选择视频渠道和模型：
────────────────────────────────────────────────
模型渠道   │ 模型            │ 状态     │ 说明
───────────┼─────────────────┼──────────┼──────────────────
Agnes      │ agnes-video-…   │ ✅ 可用  │ 推荐（有 TokenPlan 时并发更高）
TokenHub   │ hy-video-1.5    │ ✅ 可用  │ 混元 I2V；约 720p；默认并发 1；无自定义时长
eRouter    │ （视频）        │ ❌ 未实现 │ 仅探讨，勿当可烧
────────────────────────────────────────────────
选择：Agnes（默认推荐）
```

**表 2.3 短脚注（必写）：**

1. **禁止**静默换渠；跨渠须再问用户。  
2. TokenHub：本地参考图 I2V 用 `image.base64`（勿把 data URI 塞进 `image.url`）；长片靠多段拼接；YT 系列 planned，勿当可烧。  
3. 确认本表后，才出示表 3（分段规划）。

写入：`ai_video=enabled`；`video_channel`；`video_model`。  
非重度：`ai_video=disabled`；渠/模为空。

### 4. 消息 3 — 表 3（分段视频规划 · 三档都出）

#### 4.1 触发

表 2 已确认后，**轻度 / 中度 / 重度均必出**表 3。

用户若无现成文案：Agent **直接生成一版**分段提案供过目；回复「确认规划」后锁定。禁止未确认就开烧付费视频。

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

### 5. 全部确认后写入并交接

适用：表 1 + 表 2 + 表 3 均已确认。

步骤：

1. 安装未闭环 → installer。  
2. 未 `verify_ready` → setup。  
3. `produce_init_project`（若尚无项目；`pipeline_type=animated-explainer`）。  
4. 写入档位：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",   # light→template；medium→stock|user；heavy→paid_gen（可按锁定细化）
  tts_source=""       # 本轮可空或暂缓；旁白后置
)
```

5. **简报扩展字段**（写入项目 artifacts / 简报 JSON，交接时点明）：

| 字段 | 含义 |
|------|------|
| `theme` | 表 1 主题 |
| `duration_seconds` | 表 1 时长 |
| `production_tier` | `light` / `medium` / `heavy` |
| `light_presentation` | 轻度四选一；非轻度可空 |
| `medium_source` | `stock` / `user_assets`；非中度可空 |
| `ai_video` | 重度且已锁渠模 → `enabled`；否则 `disabled` |
| `video_channel` | `agnes` / `tokenhub` / …；非重度空 |
| `video_model` | 模型 id；非重度空 |
| `video_plan` | 表 3 分段规划；商品片须含：切段/重点段、`asset_classes`、`path`、`gap_fill`、每段 `ref_image`（见 references） |

6. `approval_text` 用用户原话（禁止编造）。  
7. 交接 **`openmontage-bootstrap-04-produce`**。字幕/BGM → `05-captions-music`（**后置**，不挡本步交接）。  
8. 失败 → `07-error-handling`。

**闸门：** 表 2 / 表 3 未确认时，**禁止**交接 produce、禁止开始付费视频生成。

### 6. 改档

须用户明确说「升到中度 / 升到重度 / 改回轻度」或「改档」。  

- **不要**只改 `production_tier` 数字完事。  
- 应重走 **表 1（至少确认新档位）→ 表 2 → 表 3**，再写回简报。  
- 从轻度/中度升到重度：必须重新走表 2.3（Key 闸门）与表 3。  
- 从重度降档：清空或停用 `ai_video` / 渠模，并重出对应表 2 与表 3。

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

- 用户说「生成视频」且环境已就绪时，已按「就绪接话」进入表 1（或说明卡在哪一步）  
- 缺步时已按「缺步路由」交接 01/02，未越级开烧  
- 用户确认过 **表 1**（主题 + 档位 + 时长）  
- 按档确认过 **表 2**；轻度为四选一互斥；中度遵守 Stock Key 闸门；重度遵守视频 Key 闸门与推荐规则  
- **表 3** 三档都已确认；无全文旁白强求；无文案时已给 AI 提案并获「确认规划」  
- 重度商品已强制走 `product-prompt-template.md`  
- 已写 `production_profile` 与 `video_plan` 等扩展字段  
- 未在轻度/中度展示付费视频渠模；无 Key 时未假装可烧重度  
- 未静默换渠、未静默 I2I、未跳过确认开烧  
