---
name: openmontage-bootstrap-03-usercheck
description: >-
  User-facing brief before BootStrap produce: Table A (incl. AI-video gate),
  optional Table B upgrades, then channel/model lock and AI planning table when
  needed (S1 fields + S2 step pacing). After confirms, write production_profile /
  brief artifacts and hand off to produce.
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

**做：** 需求模糊时先对齐成片要素。用**表 A（必看·主表瘦身）**降低选择压力；**表 B（选看·升档）**不挡默认路径。  
若启用 AI 视频（或用户要求 AI 设计文案）：按 **S2 分步**再确认 **表 ② 渠道/模型** → **表 ③ AI 规划表**，全部确认后才交接 `openmontage-bootstrap-04-produce`，并写入 `production_profile` / 简报 artifacts。

**不做：** 跳过确认直接 compose；一上来甩出完整升档大表或三张表堆在同一条消息；静默填 Key / 调 Stock/付费 API；伪造用户原话；有视频 Key 就自动开烧；静默更换视频渠道。

安装未闭环（5 MCP / 6 Skill 未齐）→ 先交接 `openmontage-bootstrap-01-installer`。

## 何时触发

- 用户要做视频但主题/素材/时长不清  
- 已装好环境，尚未进入正式 produce  
- produce 发现缺少「用户确认过的简报」时回到本 Skill  

## 出示节奏（S2 · 强制）

| 步骤 | 何时出示 | 同一条消息？ |
|------|----------|--------------|
| **消息 1 · 表 A** | 始终先出 | 仅表 A（+ 短脚注）；高级字段默认折叠 |
| **消息 2 · 表 ②** | 仅当表 A「AI 视频=启用」且用户已确认表 A 相关项 | 单独一条；确认后再出表 ③ |
| **消息 3 · 表 ③** | 见下方「AI 规划表触发」 | 单独一条；「确认规划」后才可交接 produce |

禁止把表 A + 表 ② + 表 ③ 堆在同一条回复里。

## Hard protocol

### 1. 收集已知项

从用户话提取：主题、时长、平台、自带素材等。  
缺的**不要连环追问**；用表 A 默认填满再请用户改。

### 2. 消息 1 — 表 A（必看 · 主表约 7 行）

检测视频渠道 Key：**仅** `AGNES_*` 与 `EROUTER_*`（尚未配置 eRouter 时只认 Agnes）。其它 Key（如 `FAL_KEY`）**不**触发本产品「AI 视频」闸门。

用户已说的内容写入「提案」列。

**表 A — 主表**

| 项 | 提案 | 状态 |
|----|------|------|
| 主题 | （已有则照写；否则先给 2–3 个候选再填入选定） | 默认可改 |
| 时长 | 45–60 秒（竖屏短视频可建议 30–45；商品试片常 10/30） | 默认可改 |
| 平台 | 横屏 16:9（可含用途一句，如电商详情） | 默认可改 |
| 解说 | Edge-TTS 男声（`zh-CN-YunyangNeural`，需联网） | 默认可改 |
| 字幕 | 开（文稿→SRT；与旁白 cue 对齐） | 默认可关 |
| 自带素材 | 有 / 无（有则注明项目 `assets/images|video|...`） | 默认可改 |
| **AI 视频** | 见下方规则 | 见下方规则 |

**AI 视频行规则**

| 检测结果 | 提案列默认 | 状态 |
|----------|------------|------|
| 无 AGNES/EROUTER Key | **不启用（无视频渠道 Key）** | 不可改为启用 |
| 有上述 Key | **不启用**（安全默认） | 可改为「启用」 |

**表 A 短脚注（必写）：**

1. 「默认继续」= 按表 A 且 **AI 视频=不启用** → **轻度**：不调用 Stock / 付费 TTS / AI 生图视频。  
2. 视频渠道 Key 仅认 `AGNES_*` / `EROUTER_*`；有 Key ≠ 自动开烧。  
3. 旁白须**按字幕 cue 对齐**；禁止整段合成后静音垫时长。无网/Edge 失败再离线 Piper。  
4. 启用 AI 后：将**另开消息**确认渠道/模型，再确认 AI 规划表，全部通过才出片。

**高级（默认折叠；用户说「看高级」再贴，勿塞进主表）：**  
目标分辨率 · BGM · 画面说明（模板 vs AI 分段等）。

**首句话术（必用）：**

> 先看表 A。回复「默认继续」= 按表 A 且不启用 AI 视频（轻度）。  
> 要启用 AI 视频请改最后一行；想升档再看表 B / 说「看高级」。

主题没有时：在贴表前或表内注明 2–3 个候选，等用户选后再定「提案」。

### 3. 表 B（选看 · 以后要更好再改）

**默认开工时不要强迫用户填表 B。** 可紧接一句「可选升档见下表」；若用户只要默认，可省略展开细节，但须告知「升档时看表 B / 说升到中度或重度」。

用户说「想更好 / 看升档 / 升到中度」时再完整展示：

**表 B — 可选升档（默认可整表跳过）**

| 想升级什么 | 怎么做 | Key |
|------------|--------|-----|
| 免费实拍/图素材 | 启用 Stock（中度） | **免费** Pexels/Pixabay → `.env-example.md` → `.env` / MCP `env` → 重启 → Skill `openmontage-providers-stock` |
| 更好人声 | 付费云端 TTS（非 Edge） | **付费** → 同上路径 → Skill `openmontage-providers-tts` |
| 离线旁白 | 本地 Piper | 无需 Key；仅无网或 Edge 失败时 |
| AI 生图 | 付费生图 | **付费** → Skill `openmontage-providers-image` |
| AI 生视频 | 见表 A「AI 视频」行 → 启用后走表 ② / 表 ③ | **付费** · 渠道 Key 仅 AGNES/EROUTER |
| 自带 BGM / 图片 / 视频 | 放入本项目 `assets/music\|images\|video\|audio` | 无需 Key |

**未写入真实 Key 前：** 禁止调用 Stock 下载与付费 generate。

### 4. 消息 2 — 表 ② 渠道 / 模型（仅 AI 视频=启用）

表 A 确认且第 7 行为**启用**后，**单独一条消息**出示表 ②。未完成表 ② 确认前，不出表 ③、不交接 produce。

**候选过滤：** 只列出已填 Key 且可用的渠道（Agnes / eRouter）。  
**v1 推荐渠道：Agnes。**

| 情况 | 行为 |
|------|------|
| 两家都可用 | 请用户选渠道（推荐标在 Agnes），或回「按推荐」 |
| 仅一家可用 | **自动锁定**该渠道，说明原因，仍须用户确认表 ② |
| 锁定渠道后仅一个模型 | **自动锁定**该模型，汇总后请用户确认 |
| 多模型 | 再请用户选模型 |

**表 ② — 主表（约 3 行）**

| 项 | 值 |
|----|-----|
| 渠道 | Agnes / eRouter（推荐或自动锁结果） |
| 模型 | （该渠道下的模型 id / 名称） |
| 能力摘要 | 一行：如 I2V、约 10s/段规划、约 1080p 请求等 |

**表 ② 短脚注（必写）：**

1. 生成策略：TokenPlan 下可 **先并行，失败/429/402 转串行补片**；已有合格片段跳过。  
2. **禁止**静默换渠；跨渠须再问用户并记录决策。  
3. 确认本表后，才出示 AI 规划表。

预估段数/消耗等放脚注即可，勿撑主表。

### 5. 消息 3 — 表 ③ AI 规划表

#### 5.1 触发（A 主 + C 补）

| 条件 | 是否出表 ③ |
|------|------------|
| AI 视频=启用 | **必出**（含 ≤10s 单段：时长规划=1） |
| 用户明确「文案由 AI 设计」（即使 AI 视频=不启用） | **必出**；提示词约束列填 **N/A（本单无 AI 视频）** |
| 仅「默认继续」且 AI=不启用、未要求 AI 文案 | **不出** |

#### 5.2 顺序

必须在表 ② 渠道/模型已锁定之后（若本单需要表 ②）。  
旁白声线**跟表 A「解说」行**，不在规划表另选声线。

#### 5.3 结构（强制；素材有则填）

**总览（强制）**

| 项 | 内容 |
|----|------|
| 总提示词 | 整片视觉方向 |
| 全文旁白 | 连贯口播全文 |
| 叙事结构 | 如：钩子 → 卖点 → 收束 |
| 一致性 | 如：同一产品/人物前后段一致 |
| 沿用 | 声线=表 A · 渠道/模型=表 ②（无表 ② 时写 N/A） |

**分段列表（强制列）**

| 段 | 时长 | 镜头目的 | 文案 | 提示词约束 | 素材（有则填） |
|----|------|----------|------|------------|----------------|
| 1 | （如 10s） | … | … | … 或 N/A | 路径或「无」 |

**表 ③ 短脚注（必写）：**

1. 回复「确认规划」后才写入简报并交接 produce；未确认不开烧 AI 视频。  
2. 可只改某一段后要求重贴。  
3. 口播按段长控制（如约 10s）；过长须删句或拆段（可在脚注说明，不必每段强制「字数列」）。  
4. 素材/参考图有则填。

**高级（折叠）：** 每段画面主体 · 运镜 · 衔接上一镜。

### 6. 全部确认后写入并交接

适用：

- 「默认继续」且 AI=不启用 → 轻度，可直接本步；  
- 或 AI 启用且表 ② + 表 ③ 均已确认；  
- 或仅 AI 文案规划（表 ③）已确认且 AI=不启用。

步骤：

1. 安装未闭环 → installer，完成后再回。  
2. 未 `verify_ready` → setup。  
3. `produce_init_project`（若尚无项目；`pipeline_type=animated-explainer`）。  
4. 写入档位与视频锁（表 A 默认轻度为 light；启用 AI 视频通常 medium/heavy，按实际升档语义）：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",
  tts_source=""
)
```

5. **简报扩展字段（约定；工具暂无参数时写入项目 artifacts / 简报 JSON，并在交接说明中点明）：**

| 字段 | 含义 |
|------|------|
| `ai_video` | `enabled` / `disabled` |
| `video_channel` | `agnes` / `erouter` / 空 |
| `video_model` | 模型 id；未启用则空 |
| `ai_plan` | 表 ③ 总览 + 分段列表（或等价结构） |

6. `approval_text` 用用户原话（禁止编造）。  
7. 交接 **`openmontage-bootstrap-04-produce`**；字幕/BGM → `openmontage-bootstrap-05-captions-music`。  
8. 失败 → `openmontage-bootstrap-07-error-handling`。

**闸门：** 需要表 ② / 表 ③ 却未确认时，**禁止**交接 produce、禁止开始付费视频生成。

### 7. 改档（表 A 确认之后）

须用户明确说「升到中度 / 升到重度 / 改回轻度」或指定表 B 某一行；更新 `production_profile` 并检查 Key/Skill 前置。  
若改为启用 AI 视频或改渠道/模型，须重新走表 ②（如需要）与表 ③。

## 与其它 Skill

| Skill | 关系 |
|-------|------|
| installer | 环境未齐时先装 |
| setup | 简报后若未 ready，先检测 |
| produce | 简报确认后的出片编排；须遵守本 Skill 锁定的渠道/模型/规划表 |
| captions-music | 字幕 / BGM |
| providers | Key 引导（配合表 B） |
| error-handling | 出片失败修复 |

## 成功标准

- 模糊需求下用户至少见过 **表 A** 并确认（含「默认继续」）  
- 未强迫新用户先消化完整升档表；未把三张表堆在同一条消息  
- 表 A 脚注含：不启用=轻度、Key 范围、cue 对齐  
- AI 视频启用时：表 ② 与表 ③ 均已确认后才交接 produce  
- 触发规划表时：结构含总览强制项 + 分段强制列；无 AI 视频时提示词为 N/A  
- 已写 `production_profile`；扩展字段已写入 profile 或 artifacts  
- 无 Key / 未启用时未调用付费 AI 视频  
