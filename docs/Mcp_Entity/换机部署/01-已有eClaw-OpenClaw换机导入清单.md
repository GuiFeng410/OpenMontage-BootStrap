# 已有 eClaw / OpenClaw —— 换机导入清单

> 日期：2026-07-20  
> 适用：另一台机器**已经**装好 eClaw 与 OpenClaw，只需再接入 OpenMontage 做零 Key 动画解说出片（P1）  
> 不包含：eClaw / OpenClaw 本体安装步骤

**结论先说：**  
不要只导入 MCP 与 Skill。必须带上 **OpenMontage 整仓（或等价最小子集）+ 本机运行时 + 在 OpenClaw 里注册 MCP/Skill**。下面按「必须 / 建议 / 不要带」列出。

---

## 0. 假设前提（本清单默认已具备）

- [ ] eClaw 可正常启动并连到 Agent
- [ ] OpenClaw 已安装，可编辑 `~/.openclaw/openclaw.json`（或厂商等价配置）
- [ ] 能执行 `openclaw mcp` / 配置 `mcp.servers`（路径以实机为准）

若以上任一项没有，先完成宿主安装，再回来用本清单。

---

## 1. 必须导入：OpenMontage 代码仓

在目标机准备一份仓库根目录，记为 `<OPENMONTAGE_REPO_ROOT>`。

### 1.1 推荐方式

- [ ] `git clone` 本仓库到目标机（或拷贝完整工作副本）
- [ ] 检出含 P1 的提交（至少包含 `openmontage/mcp`、`openmontage/skills`）

### 1.2 最小目录（缺一不可）

| 路径 | 用途 |
|------|------|
| `openmontage/mcp/` | doctor + media MCP |
| `openmontage/skills/` | OpenClaw Skill Pack |
| `tools/` | Piper / diagram / video_compose 等 BaseTool |
| `lib/` | checkpoint、pipeline 加载等 |
| `schemas/` | artifact 校验 |
| `pipeline_defs/` | 尤其 `animated-explainer.yaml` |
| `skills/pipelines/explainer/` | 各阶段 director（Skill 会指到这里） |
| `skills/meta/` | Rule Zero、atelier、runtime 选择等 |
| `remotion-composer/` | Remotion 渲染（含 `package.json`） |
| `requirements.txt` | Python 依赖 |
| `scripts/scaffold_atelier_project.py` | atelier 脚手架（强烈建议） |

### 1.3 可不带（换机出片非必须）

- [ ] `projects/` 下旧项目成片（可选参考）
- [ ] `.venv/`（应在目标机重建）
- [ ] `remotion-composer/node_modules/`（应在目标机 `npm install`）
- [ ] 本机 API Key / `.env` 密钥（P1 零 Key 路径不需要付费 Key）

---

## 2. 必须安装：本机运行时（不是「导入 Skill」）

在 `<OPENMONTAGE_REPO_ROOT>` 下：

### 2.1 Python

- [ ] Python 3.10+
- [ ] 创建并激活 venv
- [ ] `python -m pip install -r requirements.txt`（需含 `mcp`、`piper-tts` 等）
- [ ] 确认：`python -c "import openmontage.mcp.doctor; import openmontage.mcp.media"`

### 2.2 Piper（零 Key TTS）

- [ ] `piper` / `piper-tts` 可在 PATH 或 venv 中调用
- [ ] 下载中文模型，例如 `zh_CN-huayan-medium`
- [ ] 设置环境变量：
  - `PIPER_MODEL_DIR=<模型目录>`
  - `OPENMONTAGE_PIPER_MODEL=zh_CN-huayan-medium`

### 2.3 Node + Remotion

- [ ] Node.js 18+
- [ ] `cd remotion-composer && npm install`
- [ ] 确认 `remotion-composer/node_modules` 存在

### 2.4 FFmpeg

- [ ] `ffmpeg`、`ffprobe` 在 PATH

### 2.5 中文字体

- [ ] 系统至少一套可渲染中文的字体（Windows 常见：微软雅黑）

### 2.6 项目沙箱目录

- [ ] 创建可写目录，例如 `C:\Users\<you>\OpenMontageProjects` 或仓库内 `projects/`
- [ ] 设置：`OPENMONTAGE_PROJECTS_DIR=<该目录>`
- [ ] Production Agent 另设：`OPENMONTAGE_P1_ALLOW_WRITES=true`
- [ ] 建议：`PYTHONUTF8=1`

---

## 3. 必须导入到 OpenClaw：MCP（两台服务器）

合并模板（改占位符后写入 OpenClaw 配置）：

- 源文件：[../Mcp_P1/templates/p1-openclaw.mcp.json](../Mcp_P1/templates/p1-openclaw.mcp.json)
- 详细步骤：[../Mcp_P1/02-OpenClaw安装.md](../Mcp_P1/02-OpenClaw安装.md)

### 3.1 `openmontage-doctor`

- [ ] `command`: 目标机上的 `python`（建议指向 venv）
- [ ] `args`: `["-m", "openmontage.mcp.doctor"]`
- [ ] `cwd`: `<OPENMONTAGE_REPO_ROOT>`
- [ ] env：`OPENMONTAGE_PROJECTS_DIR`、`PYTHONUTF8=1`
- [ ] Production：`OPENMONTAGE_P1_ALLOW_WRITES=true`
- [ ] Default（只读诊断）Agent：**不要**开写盘 flag；可用 P0 的只读 `toolFilter`

### 3.2 `openmontage-media`

- [ ] `args`: `["-m", "openmontage.mcp.media"]`
- [ ] 同样 `cwd` + `OPENMONTAGE_PROJECTS_DIR` + `PYTHONUTF8`
- [ ] env：`PIPER_MODEL_DIR`、`OPENMONTAGE_PIPER_MODEL`
- [ ] 挂在 **Production** Agent（出片用）

### 3.3 探针

- [ ] `openclaw mcp doctor openmontage-doctor --probe`（或实机等价命令）
- [ ] 能列出 media 工具（至少 `tts_sample` / `compose_start`）

---

## 4. 必须导入到 OpenClaw：Skill

### 4.1 加载方式（二选一）

**A. extraDirs（推荐）**

- [ ] `skills.load.extraDirs` 增加：`<OPENMONTAGE_REPO_ROOT>/openmontage/skills`
- [ ] `watch: true`（开发期建议）

**B. 复制到 OpenClaw skills 目录**

- [ ] 复制整个 `openmontage/skills/*` 到 `~/.openclaw/skills/`（路径以实机为准）

### 4.2 必须启用的 Skill

| Skill 目录名 | 用途 |
|--------------|------|
| `openmontage-animated-explainer` | P1 解说出片主流程 |
| `openmontage-production-contract` | 关卡 / Rule Zero / runtime |

### 4.3 建议一并启用

| Skill 目录名 | 用途 |
|--------------|------|
| `openmontage-router` | 入门路由（P0） |
| `openmontage-gates-intro` | 人审关说明（P0） |
| `openmontage-l3-remotion` | 指向仓内 Remotion Layer3 |
| `openmontage-l3-tts` | 指向仓内 TTS Layer3 |
| `openmontage-l3-ffmpeg` | 指向仓内 FFmpeg Layer3 |

### 4.4 不要误解

- [ ] 明白：OpenClaw Skill **不会**自动带上 `skills/pipelines/explainer/`；那些仍在仓库里，靠 Agent 读文件 / 工作区访问
- [ ] 若 Production Agent `workspaceAccess: none`，需保证它仍能通过 MCP 完成出片，或按实机策略放行对 `<OPENMONTAGE_REPO_ROOT>` 的只读访问（以便读 director）

策略模板：[../Mcp_P1/templates/p1-openclaw.policy.json5](../Mcp_P1/templates/p1-openclaw.policy.json5)

---

## 5. 建议配置：双 Agent

| Agent | 写盘 | MCP | Skills |
|-------|------|-----|--------|
| Default（诊断） | 关 | 仅 doctor 只读工具 | router + gates-intro |
| Production（出片） | `OPENMONTAGE_P1_ALLOW_WRITES=true` | doctor + media | + explainer + production-contract（+ L3） |

- [ ] Default / Production 已按上表拆开（或至少 Production 配齐）

---

## 6. 换机后自检（勾选通过再开拍）

在仓库根、venv 已激活：

```powershell
$env:PYTHONUTF8 = "1"
$env:OPENMONTAGE_PROJECTS_DIR = "<PROJECTS_DIR>"
$env:OPENMONTAGE_P1_ALLOW_WRITES = "true"
$env:PIPER_MODEL_DIR = "<PIPER_MODEL_DIR>"
python -c "from openmontage.mcp.doctor.tools import run_doctor; d=run_doctor(); print('can_produce=', d['can_produce_video_now']); print(d['next_install_for_p1'])"
python -m pytest tests/mcp_p0 tests/mcp_p1 -q
```

- [ ] `can_produce_video_now == True`
- [ ] pytest 通过（若仓库含测试）
- [ ] OpenClaw 里 Production Agent 能看到 `openmontage-doctor__*` 与 `openmontage-media__*`
- [ ] 对话试跑句：

> 制作一个约 45 秒动画解说，解释天空为什么是蓝色的；零 Key，每个关卡等我确认。

期望：停轮人审 → TTS 先试听再批量 → `renders/final.mp4`。

完整验收见：[../Mcp_P1/03-验收清单.md](../Mcp_P1/03-验收清单.md)

---

## 7. 一页总表（复制给另一台机器的同事）

| # | 要做什么 | 状态 |
|---|----------|------|
| 1 | 克隆/拷贝 OpenMontage 仓（含 §1.2 最小目录） | ☐ |
| 2 | Python venv + `requirements.txt` | ☐ |
| 3 | Piper + 中文模型 + 环境变量 | ☐ |
| 4 | Node 18+ + `remotion-composer` npm install | ☐ |
| 5 | FFmpeg / FFprobe + 中文字体 | ☐ |
| 6 | 创建并设置 `OPENMONTAGE_PROJECTS_DIR` | ☐ |
| 7 | OpenClaw 注册 `openmontage-doctor` + `openmontage-media` | ☐ |
| 8 | OpenClaw 加载 `openmontage/skills`（至少 explainer + production-contract） | ☐ |
| 9 | Production：`OPENMONTAGE_P1_ALLOW_WRITES=true` + 工具策略放行 MCP | ☐ |
| 10 | `doctor` → `can_produce_video_now=true` 后开拍 | ☐ |

---

## 8. 常见卡点

| 现象 | 常见原因 |
|------|----------|
| MCP 起不来 | `cwd` 不是仓库根；用了系统 Python 而非 venv |
| `init_project` / 写盘失败 | 未设 `OPENMONTAGE_P1_ALLOW_WRITES` 或 Default Agent 误开写 |
| `can_produce_video_now=false` | 缺 Piper 模型 / Remotion npm / FFmpeg / explainer Skill 目录 |
| Agent 不会走阶段 | 未启用 `openmontage-animated-explainer`，或读不到仓内 director |
| 成片无中文 | 缺中文字体 |
| eClaw 与文档路径不一致 | 以实机 UI/企业配置为准；技术基线仍是 OpenClaw `mcp.servers` + Skill 目录 |

---

## 9. 明确不需要（P1 零 Key）

- DashScope / OpenAI / ElevenLabs / fal 等付费 Key  
- GPU（CPU 可渲染，会慢一些）  
- 强制安装 HyperFrames（可选）  
- 单独再做一个「出片 MCP」——现有 doctor + media 即 P1 双手
