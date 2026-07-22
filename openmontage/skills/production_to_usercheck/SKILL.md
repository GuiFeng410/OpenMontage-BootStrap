---
name: production_to_usercheck
description: >-
  User-facing brief checklist before BootStrap produce: when the user asks to
  make a video vaguely, present a simple confirmation table (theme, duration,
  visuals, subs, narration, BGM, tier/key path). Default is zero-key light;
  on disagreement guide free Stock keys or paid keys via .env-example.md.
  After user confirms, hand off to produce (and write production_profile).
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

**做：** 需求模糊时（「做个视频」「帮我做解说」）先对齐成片要素，用**一张表**给用户过目；默认方案可一键继续；有意见则改表或升档引导。确认后交接 `openmontage-bootstrap-produce`（并写入 `production_profile`）。  

**不做：** 跳过确认直接 compose；静默填 Key；静默调 Stock/付费 API；伪造用户原话。

安装未闭环（5 MCP / 6 Skill 未齐）→ 先交接 `openmontage-bootstrap-installer`。

## 何时触发

- 用户要做视频但主题/素材/时长不清  
- 已装好环境，尚未进入正式 produce 关卡  
- produce 发现缺少「用户确认过的简报」时，应先回到本 Skill  

## Hard protocol

### 1. 收集已知项

从用户话里提取：主题、时长、是否自带素材、要不要字幕/解说/BGM、平台（横/竖）。  
缺的先**不要连环追问**；用下面默认表填满，再请用户改。

### 2. 展示「成片简报表」（必做）

直接贴表（可按用户已说内容改单元格）。示例：

| 项 | 默认 / 当前提案 | 说明 |
|----|-----------------|------|
| 主题 | （用户已有则照写；否则列 2–3 个候选） | 用户选定或改写一句 |
| 时长 | 45–60 秒 | 可改；竖屏短视频可建议 30–45 秒 |
| 画面来源 | **零 Key：模板 + 字幕轨** | 无 Stock / 无 AI 生图视频 |
| 字幕 | 开（文稿→SRT） | 可关 |
| 解说音频 | 本地 Piper（零 Key） | 可改云端 TTS（须 Key） |
| 背景音乐 | 可选；无则跳过或零 Key 合成回退 | 自带则放入 `assets/music/` |
| 自带素材 | 无 / 路径说明 | 放入该 `project_id` 的 `assets/images\|video\|audio\|music` |
| 平台 | 横屏解说 16:9 | 可改竖屏 9:16 |
| 出片档位 | **轻度（零 Key）** | 见下方限制与升档 |

**零 Key 限制（表下必写）：**

- 不用 Pexels/Pixabay，不调用付费 TTS/生图/生视频  
- 画面以模板/字幕为主，表现力有限  
- 适合先跑通流程；要素材丰富或画质更高再升档  

话术：

> 上表是默认开工方案。回复「默认继续 / 确认」即按此开做；要改某一格直接说。

### 3. 主题与时长

- 用户已有主题/时长 → **照用户**写入表，不强行改。  
- 没有 → 自动推荐 **2–3 个**主题候选 + 建议时长（如 45s / 60s），等用户选或改。

### 4. 素材与 Key 路径（用户对默认有意见时）

先说明默认无 Key；若用户同意 → 进入步骤 5（轻度），并再次提醒限制。  

若用户要更好画面/声音，只推荐两条（勿同时强推付费）：

| 方式 | 做什么 | 档位 |
|------|--------|------|
| **方式一** | 申请免费 Stock Key（Pexels / Pixabay），按 `.env-example.md` 填写 → 写入 `.env` 与 MCP `openmontage-providers-stock` 的 `env` → 重启 MCP → 启用执行 Skill `openmontage-providers-stock` | 中度 |
| **方式二** | 申请付费模型 Key（TTS/图/视频），同样经 `.env-example.md` → 真实配置 → 重启对应 MCP → 启用 `openmontage-providers-tts` / `image` / `video` | 重度（或中度+付费 TTS） |

**未写入真实 Key 前：** 禁止调用 Stock 下载与付费 generate。  
自带本地文件：指导放入当前项目 `assets/*`，不依赖 Key。

### 5. 用户确认后（默认继续 = 确认）

1. 若安装未闭环 → installer，完成后再回来。  
2. `produce_init_project`（若尚无项目；`pipeline_type=animated-explainer`）。  
3. **自动写入档位**（与表一致）：

```text
produce_set_production_profile(
  project_id,
  production_tier="light|medium|heavy",  # 表内档位
  visual_source="",  # 可空用档位默认；自带素材可注 template/stock/paid_gen
  tts_source=""      # light/medium 默认 piper；付费 TTS 则 paid
)
```

4. 用用户确认原话做主题/简报相关 `approval_text`（禁止编造）。  
5. 交接 **`openmontage-bootstrap-produce`**，从脚本关卡继续；字幕/BGM 走 `openmontage-bootstrap-captions-music`。  
6. 工具失败 → `openmontage-bootstrap-error-handling`。

### 6. 改档

表已确认后若要升/降档：须用户明确说「升到中度 / 升到重度 / 改回轻度」，更新表与 `production_profile`，再检查 Key/Skill 前置。

## 与其它 Skill

| Skill | 关系 |
|-------|------|
| installer | 环境未齐时先装 |
| setup | 简报确认后若未 `verify_ready`，先检测 |
| produce | 简报确认后的出片主编排 |
| captions-music | 字幕 / BGM |
| providers | Key 分类引导（可与方式一/二并用） |
| error-handling | 出片失败修复 |

## 成功标准

- 模糊需求下，用户至少见过一次简报表并确认（含「默认继续」）  
- 零 Key 限制已展示  
- 确认后已写 `production_profile` 并交接 produce  
- 无 Key 时未调用 Stock/付费  
