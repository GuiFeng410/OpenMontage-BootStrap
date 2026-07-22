---
name: openmontage-bootstrap-installer
description: >-
  BootStrap installer Skill for OpenClaw: guide first-time clone OR update an
  existing local repo; narrate MCP/Skill setup (no auto config edits). Register
  all four required MCPs together; paid Keys optional. Closed-loop checklist
  before handing off to setup/produce.
metadata:
  openclaw:
    os:
      - win32
      - darwin
      - linux
    emoji: "📦"
---

# OpenMontage BootStrap Installer（安装 / 更新 Skill）

## 分发方式（重要）

本 Skill **先单独复制**到 OpenClaw 用户本地 Skill 目录（不依赖仓库已存在）。  
用户说「我想生成视频 / 做个解说片 / 更新 BootStrap」等时启用本 Skill。

仓内路径（供你拷贝）：`openmontage/skills/openmontage-bootstrap-installer/`  
外置拷贝建议在仓库大更新后**再同步一次**本目录（其它仓内 Skill 靠 extraDirs，一般不用再拷）。

## 硬规则

1. **不自动修改** OpenClaw 配置文件；只**口述**逐步操作，等用户确认完成后再进入下一步。  
2. 拉仓优先 GitHub，失败再用 Gitee；**已有仓库则走更新分支**（见 A / U），不要重复 clone 覆盖。  
3. 安装/更新阶段目标：项目可跑 + **4 个 MCP 已注册可启动** + **必开 3 Skill** + **强烈建议 2 Skill**（error-handling、captions-music）已启用。  
4. **付费 API Key 安装时不必填**；MCP 可先用占位/空 Key 启动。  
5. 不要跳过「用户确认已 clone/已 pull / 已改配置」的检查点。  
6. 口述时用**本机真实路径**替换 `<TARGET>`、`<PROJECTS_DIR>`；优先让用户从模板复制再改。  
7. 仓内 Skill 靠 `extraDirs` 指向 `<TARGET>/openmontage/skills`；`git pull` 后即同步，**不必**再拷贝 setup/produce 等到 `~/.openclaw/skills`。  
8. **注册 MCP：默认一次性配齐 4 个必配 server**（可粘贴四份模板后统一保存/重载）；Stock MCP 仍为可选后补。

## 闭环（新装与更新共用；检查项不变）

```text
① OpenClaw 已启用本 installer（外置）
② 仓库在 <TARGET>（新装 clone / 已有则 pull 更新）
③ 4 个 MCP 一并注册且能启动 + extraDirs + 必开/建议 Skill
④ 「安装闭环检查通过」→ setup → verify_ready → 可出片
```

**闭环检查条目（F）不因「更新」而减少或改写。**

## 触发话术（示例）

- 我想生成视频 / 按 BootStrap 安装  
- 仓库已经在本地了，帮我更新 / 检查 MCP 和 Skill  
- 安装 OpenMontage / BootStrap  

## 流程

### A. 先问：新装还是已有仓库？

1. 问用户本机是否**已经**有 BootStrap / OpenMontage-BootStrap 仓库。  
2. **已有** → 记下路径为 `<TARGET>`，跳到 **U. 已有仓库：更新辅助**。  
3. **没有** → 问要克隆到哪，记为 `<TARGET>`，并约定沙箱 `<PROJECTS_DIR>`（例如 `D:\om-projects`），继续 **B → C → D → E → F → G**。

---

## U. 已有仓库：更新辅助

适用于：仓库已在本地，用户要同步新代码 / 补 MCP / 补 Skill。

### U.1 确认路径与远端

确认 `<TARGET>` 指向仓库根（内含 `openmontage/`、`README/`）。  
口述（或代跑）：

```powershell
cd "<TARGET>"
git remote -v
git status
git pull
# 若 GitHub 失败，可改用已配置的 gitee / bootstrap 远端再 pull
```

可选依赖刷新：

```powershell
.\.venv\Scripts\Activate.ps1   # 或等价激活
pip install -r requirements.txt
```

**验收口令：**「仓库已 pull 到最新，路径是 `<TARGET>`」

### U.2 核对 / 补齐 MCP（可一并注册）

对照 D.2 / D.3：四个必配 MCP 是否都在、字段是否正确。  

- **缺哪个补哪个**；若几乎未配，**一次性把 4 个模板都注册进去**（同 D.4）。  
- 四个 server 的 `OPENMONTAGE_PROJECTS_DIR` 必须一致；门面须有 `OPENMONTAGE_P1_ALLOW_WRITES=true`。  
- Key 仍可空；不要因为更新而强迫填付费 Key。

**验收口令：**「四个必配 MCP 已注册并可启动」

### U.3 核对 / 补齐 Skill

1. `extraDirs` = `<TARGET>/openmontage/skills`（路径是否仍指向当前仓库）。  
2. 必开 3 个是否启用；**补开**强烈建议的 error-handling、captions-music（若尚未启用）。  
3. 若用户新加了 Stock / 付费执行需求，再按 E.4 补 Skill（及可选 stock MCP）。

**验收口令：**「extraDirs 正确；必开与建议 Skill 已启用」

### U.4 闭环检查 → 交接

直接执行 **F. 闭环检查**（条目不变）。通过后走 **G. 交接**（可提示：已装机器用 setup 做增量检测即可）。

---

## B. 口述 clone（仅新装）

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git "<TARGET>"
# 若失败：
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git "<TARGET>"
```

**验收口令（须用户原话确认）：**「clone 成功，仓库在 `<TARGET>`」

## C. 口述最小 Python（启动 MCP 需要）

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

## D. 口述注册 MCP（门面 + 三个 providers，共 4 个，一并注册）

### D.1 在 OpenClaw 里改哪里

请用户打开 OpenClaw 的 **MCP / Servers 配置**。  
对本仓库：**配置写在 OpenClaw，不写在项目 `.git` 里。**

### D.2 模板位置与四个必配 server

模板目录：`<TARGET>/README/配置/templates/`

| # | Server 名称（须一致） | 模板文件 | args |
|---|----------------------|----------|------|
| 1 | `openmontage-bootstrap` | `bootstrap.mcp.json` | `["-m", "openmontage.mcp.bootstrap"]` |
| 2 | `openmontage-providers-tts` | `providers-tts.mcp.json` | `["-m", "openmontage.mcp.providers_tts"]` |
| 3 | `openmontage-providers-image` | `providers-image.mcp.json` | `["-m", "openmontage.mcp.providers_image"]` |
| 4 | `openmontage-providers-video` | `providers-video.mcp.json` | `["-m", "openmontage.mcp.providers_video"]` |

### D.3 每个 MCP 必填字段（对照检查）

| 字段 | 应填什么 | 常见错法 |
|------|----------|----------|
| `command` | **venv 的 python 绝对路径**（推荐） | 用系统 Python → 缺包 |
| `args` | 上表模块，两项字符串 | 漏 `-m` 或模块名写错 |
| `cwd` | `<TARGET>`（仓库根） | 指到子目录 |
| `env.OPENMONTAGE_PROJECTS_DIR` | `<PROJECTS_DIR>` 绝对路径 | 四个 server 不一致 |
| `env.PYTHONUTF8` | `1` | 漏掉 |
| 门面另加 `OPENMONTAGE_P1_ALLOW_WRITES` | `true` | 漏了 → produce 写不进沙箱 |
| 付费 Key | **此时可空** | 不必安装时填 |

### D.4 一并注册与验收

**默认做法：** 按四个模板**一次性**全部写入 OpenClaw（统一替换 `<TARGET>` / `<PROJECTS_DIR>` / venv python），保存后**统一重载/重启 MCP**。  

然后请用户确认（可一条口令概括，或分四条）：

1. 「门面 MCP 已启动」  
2. 「providers-tts 已启动」  
3. 「providers-image 已启动」  
4. 「providers-video 已启动」  

也可合并为：**「四个必配 MCP 已一并注册并可启动」**。  

任一个失败 → 对照 D.3 / D.5，**不要**跳到 Skill。

### D.5 常见错误（口述排查）

1. `command` 不是 `.venv\Scripts\python.exe`  
2. `cwd` 不是仓库根 `<TARGET>`  
3. `args` 少了 `-m` 或模块路径错  
4. 改完配置**未重启/重载** MCP  
5. 门面缺 `OPENMONTAGE_P1_ALLOW_WRITES=true`  
6. 四个 server 的 `OPENMONTAGE_PROJECTS_DIR` 不一致  

## E. 口述启用仓内 Skill

### E.1 extraDirs（多数只需做一次）

`skills.load.extraDirs`（或等价项）增加：

`<TARGET>/openmontage/skills`

**验收口令：**「extraDirs 已指向仓内 skills」

### E.2 安装必开（3 个）

| Skill 名 | 作用 |
|----------|------|
| `openmontage-bootstrap-setup` | Skill01 环境 |
| `openmontage-bootstrap-produce` | Skill02 出片（含三档） |
| `openmontage-bootstrap-providers` | Skill03 收费 Key 引导 |

**验收口令：**「三个必开 Skill 已启用」

### E.3 强烈建议一并启用

| Skill | 作用 |
|-------|------|
| `openmontage-bootstrap-error-handling` | 失败：capture → plan → **apply**（含零 Key 合成 BGM） |
| `openmontage-bootstrap-captions-music` | 文稿→字幕；本地 BGM；compose 输入 |

**验收口令（建议）：**「error-handling 与 captions-music 已启用」

### E.4 按需启用

| Skill | 何时开 |
|-------|--------|
| `openmontage-providers-tts` / `image` / `video` | 填了 Key、要跑付费执行时 |
| `openmontage-providers-stock` | 后补注册了 stock MCP 后 |

本安装 Skill 留在外置目录；仓内其它 Skill 只靠 `extraDirs` 同步。

## F. 闭环检查（齐了再交接；新装与更新相同）

请用户确认下列**全部**为真（条目固定，不删减）：

1. 仓库在 `<TARGET>`，venv 可 import `openmontage`  
2. 四个 MCP 均能启动（Key 可空）  
3. `extraDirs` = `<TARGET>/openmontage/skills`  
4. 必开 3 Skill 已启用；建议 2 Skill 已启用  
5. 四个 MCP 的 `OPENMONTAGE_PROJECTS_DIR` 相同  

**验收口令：**「安装闭环检查通过」

## G. 交接（先零 Key；再选档）

告知用户下一步对 Agent 说：

> 先检测环境，给我看完整安装计划，不要直接改系统。

路径：**setup** → `verify_ready` → **produce**（主题确认后选档，见 `README/说明/02-免费与收费能力.md`）。

**付费 Key（可选）：** 「按 Skill03 帮我填 Key」；只改 MCP `env` 并重启，不必重装。  

**免费 Stock（可选后补）：** 模板 `providers-stock.mcp.json` + Skill `openmontage-providers-stock`；**不要**塞进必配 4 个 MCP。

操作索引：`<TARGET>/README/00-INDEX.md`  
模板目录：`<TARGET>/README/配置/templates/`
