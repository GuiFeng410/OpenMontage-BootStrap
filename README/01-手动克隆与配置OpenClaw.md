# 01 — 手动克隆与配置 OpenClaw

> 若走「安装 Skill」路径：先读 [00-安装Skill-先拷贝到OpenClaw.md](./00-安装Skill-先拷贝到OpenClaw.md)。本文用于手动 clone 或核对配置。

## 拉仓后仓内应有的门面组件

| 组件 | 路径 |
|------|------|
| 门面 MCP | `openmontage/mcp/bootstrap/` → `python -m openmontage.mcp.bootstrap` |
| Skill01 环境 | `openmontage/skills/openmontage-bootstrap-setup/` |
| Skill02 出片 | `openmontage/skills/openmontage-bootstrap-produce/` |
| Skill03 收费引导 | `openmontage/skills/openmontage-bootstrap-providers/` |
| 安装 Skill（可再拷到 OpenClaw） | `openmontage/skills/openmontage-bootstrap-installer/` |
| 付费 MCP（安装时一并注册，Key 可后填） | `providers_tts` / `providers_image` / `providers_video` |
| MCP 模板 | [`README/templates/`](./templates/) |

若 clone 后缺少上述目录，说明远程未更新到含门面的提交——请拉取最新 `main`。

## 1. 克隆仓库

优先 GitHub；失败再用 Gitee：

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git
# 或
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git
```

记下仓库根为 `<REPO>`。

## 2. 启动 MCP 前的最小 Python（建议）

```powershell
cd <REPO>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

也可用 Skill01 的 `install_python_deps`；但 OpenClaw 要先能跑起 MCP，通常需要已安装 `mcp` 等依赖。

## 3. 注册 MCP（门面 + 三个 providers；Key 可后填）

安装路径建议**一并注册 4 个** server（模板见 [templates/](./templates/)）：

| Server | 模板 | 说明 |
|--------|------|------|
| `openmontage-bootstrap` | `bootstrap.mcp.json` | 零 Key setup/produce |
| `openmontage-providers-tts` | `providers-tts.mcp.json` | 付费语音（Key 可空） |
| `openmontage-providers-image` | `providers-image.mcp.json` | 付费生图（Key 可空） |
| `openmontage-providers-video` | `providers-video.mcp.json` | 付费生视频（Key 可空） |

共同点：`command` 用 venv python；`cwd`=`<REPO>`；`OPENMONTAGE_PROJECTS_DIR` + `PYTHONUTF8=1`。  
门面另需 `OPENMONTAGE_P1_ALLOW_WRITES=true`。

安装 Skill **不会**自动改 OpenClaw 配置。付费 Key 见 [04](./04-收费Providers接入.md)（项目跑通后再填即可）。

## 4. 启用仓内 3 个 Skill

`skills.load.extraDirs` → `<REPO>/openmontage/skills`

- `openmontage-bootstrap-setup`（Skill01）
- `openmontage-bootstrap-produce`（Skill02）
- `openmontage-bootstrap-providers`（Skill03；无 Key 时不烧钱）

可选：外置保留 `openmontage-bootstrap-installer` 供新机引导。

**下一步 →** [02-环境检测与安装.md](./02-环境检测与安装.md)
