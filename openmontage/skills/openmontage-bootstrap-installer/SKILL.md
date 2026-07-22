---
name: openmontage-bootstrap-installer
description: >-
  BootStrap installer/updater for OpenClaw: after user confirms each step, the
  agent may execute (clone/pull, path checks). Default: register 5 MCPs together
  (facade+tts+image+video+stock) and enable 6 Skills (incl. production_to_usercheck);
  Keys optional via .env-example.md. Closed-loop checklist before setup/produce.
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
用户说「我想生成视频 / 更新 BootStrap」等时启用本 Skill。

仓内路径（供你拷贝）：`openmontage/skills/openmontage-bootstrap-installer/`

**外置同步提醒（必说）：** 本 installer 在 OpenClaw 是外置拷贝，**不会**随 `extraDirs` / `git pull` 自动更新。  
每次仓库更新本 Skill 后，须再从 `<TARGET>/openmontage/skills/openmontage-bootstrap-installer/` **覆盖拷贝**到用户 Skill 目录并确认仍已启用。

其它仓内 Skill（setup/produce/…）靠 `extraDirs` 指向 `<TARGET>/openmontage/skills`，`git pull` 即新，一般不必再拷。

## 硬规则

1. **先口述计划 → 用户确认 → 再代操作。** 未确认前不改配置、不跑会改系统的命令；用户说「确认 / 可以 / 继续」后，Agent **应主动代跑**（clone、pull、venv、路径核对等）。OpenClaw 图形里的 MCP/Skill 开关若无法代点，则给出精确粘贴内容并等用户点完后用验收口令确认。  
2. 拉仓优先 GitHub，失败再用 Gitee；**已有仓库走更新分支（U）**，禁止重复 clone 覆盖。  
3. 安装/更新默认目标：**5 个 MCP 一并注册可启动** + **6 个 Skill 一并启用** + 闭环检查通过。  
4. **付费 Key / Stock Key 安装时不必填。** 已注册即可；没 Key 则后续**不调用**对应能力（轻度零 Key 仍可出片）。  
5. Key 引导：请用户先看 `<TARGET>/.env-example.md` 分类填写，再写入真实配置（仓库 `.env` 和/或 OpenClaw 各 MCP 的 `env`）；需要高质量/中重度时再填。  
6. 口述与代操作时用真实路径替换 `<TARGET>`、`<PROJECTS_DIR>`；MCP 模板优先从 `<TARGET>/README/配置/templates/` 复制。  
7. 仓内 Skill 靠 `extraDirs`；**唯独本 installer 必须外置拷贝并在更新后提醒再同步。**

## 默认配齐清单

### MCP（5 个，安装时一次性注册）

| # | Server | 模板 |
|---|--------|------|
| 1 | `openmontage-bootstrap` | `bootstrap.mcp.json` |
| 2 | `openmontage-providers-tts` | `providers-tts.mcp.json` |
| 3 | `openmontage-providers-image` | `providers-image.mcp.json` |
| 4 | `openmontage-providers-video` | `providers-video.mcp.json` |
| 5 | `openmontage-providers-stock` | `providers-stock.mcp.json` |

Stock / 付费 Key 可空；空 Key **不使用**该通道。

### Skill（6 个，安装时一并启用）

| # | Skill | 作用 |
|---|-------|------|
| 1 | `openmontage-bootstrap-setup` | 环境检测 / 装依赖 |
| 2 | `production_to_usercheck` | 成片简报表 · 用户确认（模糊需求先过此关） |
| 3 | `openmontage-bootstrap-produce` | 出片（轻/中/重） |
| 4 | `openmontage-bootstrap-providers` | 收费 Key 引导 |
| 5 | `openmontage-bootstrap-error-handling` | 失败 capture→plan→apply |
| 6 | `openmontage-bootstrap-captions-music` | 文稿字幕 + 本地 BGM |

另：`extraDirs` = `<TARGET>/openmontage/skills`。  
付费执行 Skill（`openmontage-providers-tts` / `image` / `video`）与 `openmontage-providers-stock` **执行 Skill** 在要用对应能力且已填 Key 时再开（见 E.3）。

## 闭环（新装与更新共用）

```text
① 外置 installer 已启用（若刚 pull 过仓，提醒再拷外置副本）
② 仓库在 <TARGET>（clone 或 pull）
③ 5 个 MCP 一并注册可启动 + extraDirs + 6 个 Skill 已启用
④ 「安装闭环检查通过」→ setup → verify_ready → 模糊需求先 production_to_usercheck → produce
```

## 触发话术

- 我想生成视频 / 按 BootStrap 安装  
- 仓库已在本地，帮我更新并检查 MCP/Skill  
- 安装 OpenMontage / BootStrap  

## 流程

### A. 新装还是已有仓库？

1. 问是否已有仓库。  
2. **已有** → `<TARGET>` → **U**。  
3. **没有** → 约定 `<TARGET>` + `<PROJECTS_DIR>` → **B → C → D → E → F → G**。

每步：口述 → 用户确认 → 代操作/代整理配置内容。

---

## U. 已有仓库：更新辅助

### U.1 pull 与依赖

用户确认后代跑或给出命令并代跑：

```powershell
cd "<TARGET>"
git remote -v
git status
git pull
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**提醒：** 覆盖拷贝外置 `openmontage-bootstrap-installer` 到 OpenClaw 用户 Skill 目录。  

**验收口令：**「仓库已 pull；外置 installer 已按仓内副本更新」

### U.2 补齐 5 个 MCP

对照 D：缺则**一次性补齐 5 个**；`OPENMONTAGE_PROJECTS_DIR` 五处一致；门面有 `P1_ALLOW_WRITES=true`；Key 可空。

**验收口令：**「五个 MCP 已注册并可启动」

### U.3 补齐 6 个 Skill + extraDirs

`extraDirs` 指向当前 `<TARGET>/openmontage/skills`；六个 Skill 均启用（含 `production_to_usercheck`）。

**验收口令：**「extraDirs 正确；六个 Skill 已启用」

### U.4 → F → G

---

## B. clone（仅新装）

用户确认后代跑：

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git "<TARGET>"
# 失败则：
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git "<TARGET>"
```

**验收口令：**「clone 成功，仓库在 `<TARGET>`」

## C. venv

用户确认后代跑：

```powershell
cd "<TARGET>"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

记下：`<TARGET>\.venv\Scripts\python.exe`  

**验收口令：**「venv 与依赖已装好」

## D. 注册 MCP（5 个一并注册）

### D.1 在哪改

OpenClaw **MCP / Servers**（写在 OpenClaw，不写进 git）。  
用户确认「可以配 MCP」后：整理好 5 份完整 JSON（路径已替换）交给用户粘贴，或在可写配置时代写。

### D.2 五个默认 server

模板目录：`<TARGET>/README/配置/templates/`

| # | Server | 模板 | args |
|---|--------|------|------|
| 1 | `openmontage-bootstrap` | `bootstrap.mcp.json` | `["-m", "openmontage.mcp.bootstrap"]` |
| 2 | `openmontage-providers-tts` | `providers-tts.mcp.json` | `["-m", "openmontage.mcp.providers_tts"]` |
| 3 | `openmontage-providers-image` | `providers-image.mcp.json` | `["-m", "openmontage.mcp.providers_image"]` |
| 4 | `openmontage-providers-video` | `providers-video.mcp.json` | `["-m", "openmontage.mcp.providers_video"]` |
| 5 | `openmontage-providers-stock` | `providers-stock.mcp.json` | `["-m", "openmontage.mcp.providers_stock"]` |

### D.3 字段对照

| 字段 | 应填 | 常见错 |
|------|------|--------|
| `command` | venv python **绝对路径** | 裸 `python` |
| `args` | 上表 | 漏 `-m` |
| `cwd` | `<TARGET>` | 子目录 |
| `env.OPENMONTAGE_PROJECTS_DIR` | 同一 `<PROJECTS_DIR>` | 五个不一致 |
| `env.PYTHONUTF8` | `1` | 漏 |
| 门面 `OPENMONTAGE_P1_ALLOW_WRITES` | `true` | 漏 |
| Key（含 Pexels/Pixabay） | **可空** | 空时禁止调用该能力 |

### D.4 一并注册与验收

一次性写入 5 个 → 统一重载。  

**验收口令：**「五个 MCP 已一并注册并可启动」  
（可细分为门面 / tts / image / video / stock 五条。）

任一个失败 → D.5，**不要**跳到 E。

### D.5 常见错误

1. `command` 不是 venv python  
2. `cwd` 不是仓库根  
3. 漏 `-m` / 模块名错  
4. 未重载 MCP  
5. 门面缺 `P1_ALLOW_WRITES`  
6. 五个 `OPENMONTAGE_PROJECTS_DIR` 不一致  
7. Stock 未注册却以为「可选后补」——**现为默认第五个**

## E. 启用仓内 Skill（6 个一并）

### E.1 extraDirs

`<TARGET>/openmontage/skills`  

**验收口令：**「extraDirs 已指向仓内 skills」

### E.2 六个默认 Skill（安装时全部启用）

| Skill | 作用 |
|-------|------|
| `openmontage-bootstrap-setup` | 环境 |
| `production_to_usercheck` | 成片简报 · 用户确认 |
| `openmontage-bootstrap-produce` | 出片 |
| `openmontage-bootstrap-providers` | Key 引导 |
| `openmontage-bootstrap-error-handling` | 错误处理 |
| `openmontage-bootstrap-captions-music` | 字幕配乐 |

**验收口令：**「六个 Skill 已启用」

### E.3 用到再开（执行层）

| Skill | 何时 |
|-------|------|
| `openmontage-providers-tts` / `image` / `video` | 已填付费 Key 且要跑付费生成 |
| `openmontage-providers-stock` | 已填 Stock Key 且中度要用免费素材 |

本 installer 外置；更新后**再次提醒拷贝**。

## F. 闭环检查（新装与更新相同；含 stock 与 6 Skill）

下列**全部**为真：

1. 仓库在 `<TARGET>`，venv 可 `import openmontage`  
2. **五个 MCP**均能启动（Key 可空）  
3. `extraDirs` = `<TARGET>/openmontage/skills`  
4. **六个 Skill**均已启用（setup / production_to_usercheck / produce / providers / error-handling / captions-music）  
5. 五个 MCP 的 `OPENMONTAGE_PROJECTS_DIR` 相同  
6. （提醒项）外置 installer 已与仓内副本同步  

**验收口令：**「安装闭环检查通过」

## G. 交接

> 先检测环境，给我看完整安装计划，不要直接改系统。

**setup** → `verify_ready` → 用户说「做个视频」等模糊需求时先走 **`production_to_usercheck`**（简报表确认）→ **produce**。

### Key 引导（需要质量再填）

1. 打开 `<TARGET>/.env-example.md`，按分类填写（含 Pexels/Pixabay、付费 TTS/图/视频等）。  
2. 写入真实配置：复制为 `<TARGET>/.env`，并同步到 OpenClaw 对应 MCP 的 `env`。  
3. 重启相关 MCP；中度用 Stock / 重度付费前再启用 E.3 执行 Skill。  
4. **未填 Key：禁止调用** Stock 下载与付费 generate。

操作索引：`<TARGET>/README/00-INDEX.md`  
模板：`<TARGET>/README/配置/templates/`  
Key 白话说明：`<TARGET>/.env-example.md`
