---
name: production_to_usercheck
description: >-
  User-facing brief before BootStrap produce: show Table A (must-see default
  zero-key plan) and optional Table B (upgrades needing free/paid keys). User
  can reply 默认继续 on A only. After confirm, write production_profile and
  hand off to produce. Keys via .env-example.md when upgrading.
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

# production_to_usercheck（成片简报 · 用户确认）

## Scope

**做：** 需求模糊时先对齐成片要素。用**表 A（必看·默认开工）**降低选择压力；**表 B（选看·升档）**不挡默认路径。用户可「默认继续」只按表 A。确认后交接 `openmontage-bootstrap-produce` 并写入 `production_profile`。  

**不做：** 跳过确认直接 compose；一上来甩出完整升档大表；静默填 Key / 调 Stock/付费 API；伪造用户原话。

安装未闭环（5 MCP / 6 Skill 未齐）→ 先交接 `openmontage-bootstrap-installer`。

## 何时触发

- 用户要做视频但主题/素材/时长不清  
- 已装好环境，尚未进入正式 produce  
- produce 发现缺少「用户确认过的简报」时回到本 Skill  

## Hard protocol

### 1. 收集已知项

从用户话提取：主题、时长、平台、自带素材等。  
缺的**不要连环追问**；用表 A 默认填满再请用户改。

### 2. 先出表 A（必看 · 默认零 Key）

只展示约 6 行。用户已说的内容写入「提案」列。

**表 A — 默认开工（无需 Key）**

| 项 | 提案 | 状态 |
|----|------|------|
| 主题 | （已有则照写；否则先给 2–3 个候选再填入选定） | 默认可改 · 无需 Key |
| 时长 | 45–60 秒（竖屏短视频可建议 30–45） | 默认可改 · 无需 Key |
| 平台 | 横屏 16:9 | 默认可改 · 无需 Key |
| 画面 | 模板 + 字幕轨 | 默认 · 无需 Key |
| 解说 | 本地 Piper | 默认 · 无需 Key |
| 字幕 | 开（文稿→SRT） | 默认可关 · 无需 Key |

**表 A 脚注（必写）：** 按此表 = **轻度零 Key**：不调用 Stock / 付费 TTS / AI 生图视频；画面以模板+字幕为主，适合先跑通。

**首句话术（必用，降低茫然）：**

> 先看表 A（默认就能开工）。回复「默认继续」= 按表 A 轻度出片。  
> 想画面/声音更好再看表 B；改表 A 某一格直接说即可。

主题没有时：在贴表前或表内注明 2–3 个候选，等用户选后再定「提案」。

### 3. 表 B（选看 · 以后要更好再改）

**默认开工时不要强迫用户填表 B。** 可紧接一句「可选升档见下表」；若用户只要默认，可省略展开细节，但须告知「升档时看表 B / 说升到中度或重度」。

用户说「想更好 / 看升档 / 升到中度」时再完整展示：

**表 B — 可选升档（默认可整表跳过）**

| 想升级什么 | 怎么做 | Key |
|------------|--------|-----|
| 免费实拍/图素材 | 启用 Stock（中度） | **免费** Pexels/Pixabay → `.env-example.md` → `.env` / MCP `env` → 重启 → Skill `openmontage-providers-stock` |
| 更好人声 | 云端 TTS | **付费** → 同上路径 → Skill `openmontage-providers-tts` |
| AI 生图 / 生视频 | 付费模型 | **付费** → Skill `openmontage-providers-image` / `video` |
| 自带 BGM / 图片 / 视频 | 放入本项目 `assets/music\|images\|video\|audio` | 无需 Key |

**未写入真实 Key 前：** 禁止调用 Stock 下载与付费 generate。

### 4. 用户确认后（「默认继续」= 只确认表 A → 轻度）

1. 安装未闭环 → installer，完成后再回。  
2. 未 `verify_ready` → setup。  
3. `produce_init_project`（若尚无项目；`pipeline_type=animated-explainer`）。  
4. 写入档位（表 A 默认 = light；若用户已确认表 B 某升档则 medium/heavy）：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",
  visual_source="",
  tts_source=""
)
```

5. `approval_text` 用用户原话（禁止编造）。  
6. 交接 **`openmontage-bootstrap-produce`**；字幕/BGM → `openmontage-bootstrap-captions-music`。  
7. 失败 → `openmontage-bootstrap-error-handling`。

### 5. 改档（表 A 确认之后）

须用户明确说「升到中度 / 升到重度 / 改回轻度」或指定表 B 某一行；更新 `production_profile` 并检查 Key/Skill 前置。

## 与其它 Skill

| Skill | 关系 |
|-------|------|
| installer | 环境未齐时先装 |
| setup | 简报后若未 ready，先检测 |
| produce | 简报确认后的出片编排 |
| captions-music | 字幕 / BGM |
| providers | Key 引导（配合表 B） |
| error-handling | 出片失败修复 |

## 成功标准

- 模糊需求下用户至少见过 **表 A** 并确认（含「默认继续」）  
- 未强迫新用户先消化完整升档表  
- 表 A 脚注含零 Key 限制  
- 确认后已写 `production_profile` 并交接 produce  
- 无 Key 时未调用 Stock/付费  
