# OpenMontage BootStrap — Agent 契约（短版）

**契约修订：`doc-r1`（2026-08-21）** · 产品版：`v0.6.0`

本文是日常出片契约。上游 YAML pipeline / atelier / registry 长文已迁到 [`AGENT_GUIDE-upstream.md`](AGENT_GUIDE-upstream.md)——**默认不读**；仅用户点名 pipeline、或七 Skill 盖不住时再开。

门口一页纸：[`AGENTS.md`](AGENTS.md)。

---

## 0. 文档地图

| 文件 | 何时读 |
|------|--------|
| [`AGENTS.md`](AGENTS.md) | 新会话第一页：是什么、读序、缺步、Skill 一行、Git |
| **本文** | 流程 + 职责 + 双通道硬规则 |
| 当前 BootStrap Skill `skills/bootstrap/...` | 执行该步时通读对应 `SKILL.md` |
| [`AGENT_GUIDE-upstream.md`](AGENT_GUIDE-upstream.md) | 上游 pipeline / atelier / preflight |
| [`README/agent/PRODUCT_MAP.md`](README/agent/PRODUCT_MAP.md) · [`PROJECT_CONTEXT.md`](README/agent/PROJECT_CONTEXT.md) | 熟悉项目（Goal1） |
| `Agent-Docs/Phase/A_01-session-handoff/` | 本机交接（gitignore） |

### 冲突裁决（硬）

优先级从高到低：

1. **本文 + `AGENTS.md` 的通道规则**（默认网站 / 纯聊天、不静默付费等）
2. **当前通道对应 Skill 章节**（网站走 B2/intent；聊天走 Grill）
3. Skill 内与通道冲突的旧写法 → **以通道规则为准**（03/04 下一轮再对齐正文）
4. 上游附录 → 仅显式需要时

---

## 1. 共享装机链（01 → 02 → 03）

```text
01-installer（新装/更新仓库）→ 02-setup（检测→计划确认→安装→verify_ready）→ 03-usercheck（扫 Key · 锁定简报）
```

硬规则：

- 先口述计划 → 用户确认 → 再改系统；高风险工具默认 `dry_run=true`
- `verify_ready` 未真 → **禁止**进表 1 / 正式出片
- **开口先读** `.openmontage/install-state.json`（gitignore）
  - `verify_ready: true` → 禁止再走安装话术
  - 无状态文件但 `projects/` 已有 `project.json` → 禁止再 clone，按 `verify_ready` 决定是否走 02
  - 无状态且无项目 → 01/02

环境口径（02）：旁白主推 **Edge-TTS**；**HyperFrames 建议装、可跳过**（不挡 `verify_ready`）；**Piper 仅离线可选**，默认不下载模型。

---

## 2. 出片双通道

### 2.1 默认：网站通道（Backlot）

适用：模糊「做个视频」、电商宣传片、用户给了网址且未声明只要聊天。

Agent 职责：

1. 03 扫 Key、锁定简报（默认电商；缺网址就问一句）
2. 创建/打开项目后给出看板 URL（`python -m backlot open` 或项目页）
3. 之后以 **面板 intent + runner** 推进；Agent 读盘、写 checkpoint、消费 intent，**不要**用聊天 Grill 代替面板按钮
4. 浏览器不调付费 API；付费须用户授权后由 runner/Agent 执行

`python -m backlot open` 失败时：出片可继续，但须说明看板未开；默认通道仍以「给网址」为目标，不要静默改成纯聊天。

### 2.2 可选：纯聊天通道

适用：用户明确说「只要聊天 / 不要看板 / 纯对话出片」等。

Agent 职责：

1. **不要求**、也不强推看板 URL
2. 03 锁定简报后交接 04；按 Skill 的聊天路径（Grill / 检查点口述）推进
3. 产出仍落在 `projects/<id>/`（artifacts / assets / renders）
4. 其余硬规则相同：不静默付费、不静默换渠道、空 Key 禁止调用

### 2.3 通道选择一句话

- 未声明 → **网站**
- 明确只要聊天 → **纯聊天**
- 中途改口 → 跟用户确认后切换，并在 `decision_log` / 交接里记一笔

---

## 3. 缺步路由（Goal2）

| 现状 | 动作 |
|------|------|
| 未 clone / 未装 MCP·Skill | **01** |
| 未 `verify_ready` | **02** |
| 简报未锁（表 2/3） | **03** → 再 **04** |
| 简报已锁，要出片 | **04** |
| 要字幕/本地 BGM | **05**（可后置） |
| 要收费/Stock Key | **06** |
| 工具失败 | **07**（capture → plan → apply，≤3） |

表 2/3 未确认 → **禁止**交接 04。

---

## 4. 新会话 / 续作

1. 读 `AGENTS.md` → 本文相关节 → 当前 Skill
2. 读 `Agent-Docs/Phase/A_01-session-handoff/` 下**日期最新**交接（若有）
3. 读 `.openmontage/install-state.json`：已就绪则给看板或按通道续作，禁止重装话术
4. 续作：`produce_get_next_stage` / checkpoint / 看板 intent；不要无故新建平行项目

熟悉项目（Goal1）读序：`AGENTS` → 本文 → `PRODUCT_MAP` / `PROJECT_CONTEXT` → 最新交接。

---

## 5. 失败与 07

工具失败时走 **07-error-handling**：`error_capture_context` → `error_classify` → `error_plan_recovery` → 用户确认 → `error_apply_recovery`（同问题 ≤3 次）。不要静默换 provider / 模型。

上游级 blocker 结构（尝试了什么 / 失败了什么 / 选项 / 推荐）见上游附录 Decision Communication；日常仍服从双通道与「先确认再执行」。

---

## 6. 硬规则清单

- 不静默付费、不静默换渠道、不静默从样片切批量
- 空 Key **禁止**调用对应收费工具；先 06
- 安装/环境未就绪 → 禁止正式出片
- 默认电商路径：**给看板网址**；纯聊天路径：**不要求网址**
- 高风险安装类：先计划、用户确认、再 `dry_run=false` + `confirm_execute=true`
- 资产写入必须在 `projects/<project-id>/` 下显式路径
- **禁止** `git push origin`；双推 = `gitee` + `bootstrap`（见 §9）
- 未获用户明确要求：禁止对 `Agent-Docs/` / `Agent-ReadMe/` / `Agent-Temp/` 做 add/commit/push

---

## 7. Skill / MCP 职责（流程 · 职责）

| # | Skill | 职责摘要 |
|---|--------|----------|
| 01 | installer | 仓库/MCP/Skill 装齐 |
| 02 | setup | 环境检测与 `verify_ready` |
| 03 | usercheck | 扫 Key、锁简报、定通道（默认网站） |
| 04 | produce | 按已锁简报出片（网站=intent；聊天=Grill） |
| 05 | captions-music | 字幕 / 本地 BGM（可后置） |
| 06 | providers | 收费与 Stock Key 引导 |
| 07 | error-handling | 失败闭环 ≤3 |

门面 MCP：`user-openmontage-bootstrap`（装机 + 零 Key 出片主链）。收费能力走 `providers-tts` / `image` / `video` / `stock`；一律 dry_run → 估价确认 → sample → 用户 OK → generate。

看板：`python -m backlot open` 只开库页服务；创建或「继续这个项目」才起唯一 runner。

---

## 8. 状态与目录

| 路径 | 谁写 / 用途 |
|------|-------------|
| `.openmontage/install-state.json` | 02/`verify_ready`、库页创建、backlot serve；**无密钥** |
| `projects/<id>/project.json` | 项目标记；看板读取 |
| `projects/<id>/artifacts/` | 各阶段 JSON |
| `projects/<id>/assets/` | 图/视频/音/字幕 |
| `projects/<id>/renders/final.mp4` | 成片 |
| `music_library/` | 用户本地曲库（gitignore） |
| `Agent-Docs/` 等 | 本机工作区；默认不提交 |

---

## 9. Git 推送（Agent）

- **双推** = `gitee` + `bootstrap` only
- **Never** `git push origin`（`origin` 为上游只读）
- 默认 `git push` → `gitee`；需要同步 Bootstrap 远端时再推 `bootstrap`
- 提交说明用中文短句（范围 + 重点）；仅用户明确要求时 commit/push

---

## 10. Don’ts（日常）

- 不要跳过 03 直接 04
- 不要在默认通道不给看板 URL、却假装「已交给用户点选」
- 不要在纯聊天通道强行要求开看板
- 不要未读 Skill 就 improvise 调工具
- 不要把正式计划长期只写在 `Agent-Temp/`
- 不要默认阅读或执行上游附录里的全 pipeline 仪式（除非用户点名）

上游专用 Don’ts / Layer Map / Tool Families → [`AGENT_GUIDE-upstream.md`](AGENT_GUIDE-upstream.md)。

---

## 11. Quick Lookup

| 问题 | 去哪 |
|------|------|
| 今天走哪条 Skill？ | `AGENTS.md` 缺步表 / 本文 §3 |
| 网站还是聊天？ | 本文 §2 |
| 安装怎么做？ | Skill 02 + bootstrap MCP |
| 出片工具名？ | Skill 04 + `list_bootstrap_tools` |
| 付费 Key？ | Skill 06 + providers MCP |
| 工具挂了？ | Skill 07 |
| animated-explainer / atelier？ | `AGENT_GUIDE-upstream.md` |
| 架构地图？ | `README/agent/PRODUCT_MAP.md` |
