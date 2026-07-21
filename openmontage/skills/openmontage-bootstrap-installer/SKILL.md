---
name: openmontage-bootstrap-installer
description: >-
  BootStrap installer Skill for OpenClaw: when the user wants to make a video,
  guide cloning OpenMontage-BootStrap and narrate MCP/Skill setup steps (no auto
  config edits). Registers facade + three providers MCPs; paid Keys stay optional.
  Includes field-by-field OpenClaw checklists and acceptance prompts.
metadata:
  openclaw:
    os:
      - win32
      - darwin
      - linux
    emoji: "📦"
---

# OpenMontage BootStrap Installer（安装 Skill）

## 分发方式（重要）

本 Skill **先单独复制**到 OpenClaw 用户本地 Skill 目录（不依赖仓库已存在）。  
用户说「我想生成视频 / 做个解说片」等时启用本 Skill。

仓内路径（供你拷贝）：`openmontage/skills/openmontage-bootstrap-installer/`

## 硬规则

1. **不自动修改** OpenClaw 配置文件；只**口述**逐步操作，等用户确认完成后再进入下一步。  
2. 拉仓优先 GitHub，失败再用 Gitee。  
3. 安装阶段目标：项目可跑 + **4 个 MCP 已注册可启动** + **3 个 Skill 已启用**。  
4. **付费 API Key 安装时不必填**；MCP 可先用占位/空 Key 启动。项目与零 Key 路径跑通后，再可选填 Key。  
5. 不要跳过「用户确认已 clone / 已改配置」的检查点。  
6. 口述时用**本机真实路径**替换 `<TARGET>`、`<PROJECTS_DIR>`；优先让用户从模板复制再改。

## 触发话术（示例）

- 我想生成视频  
- 帮我做个动画解说  
- 安装 OpenMontage / BootStrap  

## 流程

### A. 询问安装目录

问用户要把仓库克隆到哪个本地路径，记为 `<TARGET>`（例如 `D:\OpenMontage-BootStrap`）。  
同时约定项目沙箱目录 `<PROJECTS_DIR>`（例如 `D:\om-projects`，可先不存在，后续 setup 会建）。

### B. 口述 clone（可代跑终端则代跑；否则只给命令）

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git "<TARGET>"
# 若失败：
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git "<TARGET>"
```

**验收口令（须用户原话确认）：**「clone 成功，仓库在 `<TARGET>`」

### C. 口述最小 Python（启动 MCP 需要）

```powershell
cd "<TARGET>"
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

记下 **venv Python 绝对路径**（Windows 示例）：

`<TARGET>\.venv\Scripts\python.exe`

**验收口令：**「venv 与依赖已装好」

### D. 口述注册 MCP（门面 + 三个 providers，共 4 个）

#### D.1 在 OpenClaw 里改哪里

请用户打开 OpenClaw 的 **MCP / Servers 配置**（名称因版本可能是「MCP」「Tools」「Servers」）。  
对本仓库：**配置写在 OpenClaw，不写在项目 `.git` 里。**

对每个 server：新建或粘贴 JSON，再按下面替换占位符。

#### D.2 模板位置与四个必配 server

模板目录：`<TARGET>/README/配置/templates/`

| # | Server 名称（须一致） | 模板文件 | args |
|---|----------------------|----------|------|
| 1 | `openmontage-bootstrap` | `bootstrap.mcp.json` | `["-m", "openmontage.mcp.bootstrap"]` |
| 2 | `openmontage-providers-tts` | `providers-tts.mcp.json` | `["-m", "openmontage.mcp.providers_tts"]` |
| 3 | `openmontage-providers-image` | `providers-image.mcp.json` | `["-m", "openmontage.mcp.providers_image"]` |
| 4 | `openmontage-providers-video` | `providers-video.mcp.json` | `["-m", "openmontage.mcp.providers_video"]` |

#### D.3 每个 MCP 必填字段（对照检查）

| 字段 | 应填什么 | 常见错法 |
|------|----------|----------|
| `command` | **venv 的 python 绝对路径**（推荐），不要用裸 `python` 除非 PATH 已指向该 venv | 用系统 Python → 缺包 / 起不来 |
| `args` | 上表模块，两项字符串 | 漏 `-m` 或模块名写错 |
| `cwd` | `<TARGET>`（仓库根，能 import `openmontage`） | 指到子目录 |
| `env.OPENMONTAGE_PROJECTS_DIR` | `<PROJECTS_DIR>` 绝对路径 | 与门面不一致 |
| `env.PYTHONUTF8` | `1` | 漏掉导致中文路径问题 |
| 门面另加 `OPENMONTAGE_P1_ALLOW_WRITES` | `true` | 漏了 → produce 写不进沙箱 |
| 付费 Key | **此时可空 / 删掉占位** | 不必安装时填 |

Windows 路径含空格时：`command`/`cwd` 用完整路径；JSON 里用 `\\` 或正斜杠均可，保持与 OpenClaw 习惯一致。

#### D.4 逐项验收（不要一次糊弄过）

请用户**每配完一个就启动/重载**，并分别回复：

1. 「门面 MCP 已启动」  
2. 「providers-tts 已启动」  
3. 「providers-image 已启动」  
4. 「providers-video 已启动」  

四个都收到后再进 E。若某个失败，先对照 D.3，**不要**跳到 Skill。

#### D.5 常见错误（口述排查）

1. `command` 不是 `.venv\Scripts\python.exe`  
2. `cwd` 不是仓库根 `<TARGET>`  
3. `args` 少了 `-m` 或模块路径错  
4. 改完配置**未重启/重载**该 MCP  
5. 门面缺 `OPENMONTAGE_P1_ALLOW_WRITES=true`  
6. 四个 server 的 `OPENMONTAGE_PROJECTS_DIR` 不一致  

### E. 口述启用仓内 Skill

#### E.1 extraDirs（多数只需做一次）

在 OpenClaw **Skills / 技能加载**配置中，为 `skills.load.extraDirs`（或等价项）增加：

`<TARGET>/openmontage/skills`

**验收口令：**「extraDirs 已指向仓内 skills」

若以前配过 setup/produce，此项通常已有，核对路径仍指向当前 `<TARGET>` 即可。

#### E.2 安装必开（3 个）

| Skill 名 | 作用 |
|----------|------|
| `openmontage-bootstrap-setup` | Skill01 环境 |
| `openmontage-bootstrap-produce` | Skill02 出片（含三档） |
| `openmontage-bootstrap-providers` | Skill03 收费 Key 引导 |

**验收口令：**「三个必开 Skill 已启用」

#### E.3 按需启用（安装时可不急）

| Skill | 何时开 |
|-------|--------|
| `openmontage-providers-tts` / `image` / `video` | 填了对应 Key、要跑付费执行时 |
| `openmontage-providers-stock` | 后补注册了 stock MCP 后 |

本安装 Skill 可继续留在外置目录，供新机引导。

### F. 交接（先零 Key；再选档）

告知用户下一步对 Agent 说：

> 先检测环境，给我看完整安装计划，不要直接改系统。

路径：**setup** → `verify_ready` → **produce**（主题确认后选 **轻度 / 中度 / 重度**，见 `README/说明/02-免费与收费能力.md`）。

**付费 Key（可选，安装后）：** 对 Agent 说「按 Skill03 帮我填 Key」，或读 `<TARGET>/README/说明/02-免费与收费能力.md`。  
只改已注册 MCP 的 `env` 并重启，**不必重装**。

**免费 Stock（可选后补，默认不安）：**  
注册 `openmontage-providers-stock`（模板 `README/配置/templates/providers-stock.mcp.json`），启用 `openmontage-providers-stock`，填 `PEXELS_API_KEY` / `PIXABAY_API_KEY`。  
说明：`<TARGET>/README/说明/02-免费与收费能力.md`。  
**不要**塞进安装必配的 4 个 MCP。

操作索引：`<TARGET>/README/00-INDEX.md`  
模板目录：`<TARGET>/README/配置/templates/`
