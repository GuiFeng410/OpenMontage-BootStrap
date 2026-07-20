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
| 付费 MCP（可选） | `providers_tts` / `providers_image` / `providers_video` |
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

## 3. 只注册 1 个门面 MCP（口述/手改配置）

最小路径只需门面。要点：

- `command`：venv 的 `python`
- `args`：`["-m", "openmontage.mcp.bootstrap"]`
- `cwd`：`<REPO>`
- `env`：`OPENMONTAGE_PROJECTS_DIR`、`PYTHONUTF8=1`、`OPENMONTAGE_P1_ALLOW_WRITES=true`

安装 Skill **不会**自动改 OpenClaw 配置，需你按口述完成。

收费 TTS/图/视频：**另**注册 providers MCP，见 [04](./04-收费Providers接入.md) 与 [templates/](./templates/)。

门面模板：[templates/bootstrap.mcp.json](./templates/bootstrap.mcp.json)

## 4. 启用仓内 Skill（出片主路径）

`skills.load.extraDirs` → `<REPO>/openmontage/skills`

- `openmontage-bootstrap-setup`（Skill01）
- `openmontage-bootstrap-produce`（Skill02）
- （可选）`openmontage-bootstrap-providers`（Skill03，收费接入）
- （可选）`openmontage-bootstrap-installer` 供以后新机引导

**下一步 →** [02-环境检测与安装.md](./02-环境检测与安装.md)
