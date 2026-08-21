# OpenMontage BootStrap — Agent 入口

**MANDATORY: 回复任意用户消息前，先读 [`AGENT_GUIDE.md`](AGENT_GUIDE.md)。**

未读完不要动手。其中有路由规则：先走哪条 Skill、何时进 pipeline、Git 推送约定。跳过会导致装错环境或越级出片。

## 交付方式（G6.1）

**主路径：git 克隆本仓 + Agent 宿主协同**（Cursor / Claude 等读本文件与 `AGENT_GUIDE.md`，配 MCP + BootStrap Skill）。

- 人读操作长文：[`README/00-INDEX.md`](README/00-INDEX.md)（仓内跟踪，随 clone 带走）
- 本机草稿/私货：`Agent-ReadMe/`（gitignore，**不是**公开真源）
- G4 `pack` / 下载运行包装机验收：**样品与远期**，不是当前主验收

## 本仓是什么

本仓库是 **OpenMontage-BootStrap**（日常发布到 `gitee` + `bootstrap`），在上游 OpenMontage 之上叠了 **门面 MCP + BootStrap Skills**，让 Agent 用「安装 → 环境 → 简报 → 出片」闭环出片。上游完整 pipeline 规则仍在 `AGENT_GUIDE.md`，日常「做个视频」**优先走 BootStrap 七 Skill**，不要直接 improvise 调工具。

## 新会话先看

1. [`AGENT_GUIDE.md`](AGENT_GUIDE.md)（总契约 + BootStrap 路由）
2. 本地交接：`Agent-Docs/Phase/A_01-session-handoff/00-新对话请先读.md` → 同目录**日期最新**长篇交接（本机工作区，gitignore）
3. 人读操作：[`README/00-INDEX.md`](README/00-INDEX.md)；本机副本可选 [`Agent-ReadMe/00-INDEX.md`](Agent-ReadMe/00-INDEX.md)

## 本机工作区（name-to-workspace）

因 Windows 大小写不敏感，不用 `Docs/`/`ReadMe/`/`Temp/`（会与 `docs/`/`README/` 冲突），改用：

| 目录 | 用途 | Git |
|------|------|-----|
| `Agent-Docs/` | 对话、要点、计划、阶段（套 **name-to-docs**：Goal/Plan/Phase/Platform…） | **默认不提交** |
| `Agent-ReadMe/` | 人读说明的**本机副本/草稿**；公开真源在仓内 `README/` | **默认不提交** |
| `Agent-Temp/` | `mats/` 素材 · `results/` 产物 · `other/` 暂存 | **默认不提交** |

- 仓内 `README/` 为人读操作真源；`docs/` 为遗留快照。历史报告与演示已迁 `archive/`（G6.1）。
- 仓根宿主 stub（`CLAUDE.md` / `CURSOR.md` / `CODEX.md` / `COPILOT.md`）**保留不搬**；架构正文在 `README/agent/PROJECT_CONTEXT.md`（仓根仅跳转 stub）。
- 未获用户明确要求时，禁止对 Agent-\* 做 `add` / `commit` / `push`。

## 七个 BootStrap Skill（路由摘要）

仓内路径：`skills/bootstrap/`（BootStrap 01–07）。安装默认启用 02–07；`01-installer` 常外置拷贝（更新后须再同步）。宿主 extraDirs 三条：`skills/bootstrap`、`skills/providers`、`skills/production`。

| # | Skill | 何时读 / 启用 |
|---|--------|----------------|
| **01** | `openmontage-bootstrap-01-installer` | 新装 / 更新仓库、补齐 **5 MCP + 6 Skill** |
| **02** | `openmontage-bootstrap-02-setup` | 环境检测 → 计划确认 → 装依赖 → `verify_ready` |
| **03** | `openmontage-bootstrap-03-usercheck` | 模糊「做个视频」：先扫 Key，**默认电商宣传片**（给网址；缺啥问一句）；轻度 Demo 仅明确要求 |
| **04** | `openmontage-bootstrap-04-produce` | 按 03 已锁定简报执行出片（默认不重选档） |
| **05** | `openmontage-bootstrap-05-captions-music` | 字幕 / 本地 BGM（可后置，不挡画面） |
| **06** | `openmontage-bootstrap-06-providers` | 收费 / Stock Key 引导（空 Key 禁止调用） |
| **07** | `openmontage-bootstrap-07-error-handling` | 工具失败：capture → plan → apply（≤3） |

```text
【装机】01-installer → 02-setup（verify_ready）
【出片主链】03-usercheck（默认电商 · 扫 Key · 给网址）→ 04-produce → renders/final.mp4
【补充】05 字幕配乐 · 06 Key · 07 排错（按需）
```

**硬规则：** 安装/环境未就绪 → 禁止进表 1；表 2/3 未确认 → 禁止交接 04；先口述计划 → 用户确认 → 再改系统；不静默付费、不静默换渠道。

**环境口径（02）：** 旁白主推 **Edge-TTS**；**HyperFrames 建议装、可跳过**（不挡 `verify_ready`）；**Piper 仅离线可选**，默认不下载模型。

细节、缺步路由、Git 双推、与上游 pipeline 的关系 → **全部见 `AGENT_GUIDE.md`**。

## 版本身份（v0.6.0）

- 逻辑分层地图：[`README/agent/PRODUCT_MAP.md`](README/agent/PRODUCT_MAP.md)（仓根 `PRODUCT_MAP.md` 为跳转 stub）
- Python 包：`src/openmontage/`（`python -m openmontage.mcp.bootstrap` 不变；仓根 `openmontage/` 是加载器 shim）
- 内核：`src/openmontage/lib/`（`from lib.…` 不变；仓根 `lib/` 是转发 shim）
- 发布清单：[`distribution/manifests/release-manifest.json`](distribution/manifests/release-manifest.json)
- **G6.1：** 仓根精简 + 克隆/Agent — `Agent-Docs/Goal/03-G6.1…` · `Plan/33`；文档二分见 `Plan/34`
- **本机状态文件：** 仓根 `.openmontage/install-state.json`（gitignore，**不提交、不写密钥**）
 - 字段：`verify_ready`、`repo_root`、`projects_dir`、`latest_project_id`、`existing_project_count`、`video_key_present`、`stock_key_present`（及非空变量名）
 - MCP：`read_install_state` / `scan_video_keys` / `snapshot_install_state` / `ensure_env_file`；`verify_ready` 通过后会写入
 - **不会随 git clone / pull 出现**（gitignore）。会在：02 `verify_ready`、库页成功创建、Backlot `serve` 启动时写入或刷新
 - **开口 / 网页创建前先读此文件。** `verify_ready` 为真 → 禁止再走安装话术，必须给看板网址；文件不存在但 `projects/` 已有 `project.json` → 已用过本仓，禁止再 clone，仍按 `verify_ready` 决定是否走 02；文件不存在且无项目 → 01/02
 - 看板：`python -m backlot open` 只开网页服务看库；创建或库页「继续这个项目」才起唯一 runner（消费面板 intent 与结束导出；用户授权后可调已锁付费 API；浏览器不调）
