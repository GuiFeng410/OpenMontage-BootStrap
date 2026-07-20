# OpenClaw 配置草案（首版 · 手动 clone 后）

> 与 [01-实现计划.md](./01-实现计划.md) 配套；编码落地后以 `templates/` 为准。

## 前提

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git
# 或
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git
```

记 `<REPO>` = 克隆根目录；`<PROJECTS>` = 可写沙箱（可先由 Skill01 `configure_sandbox` 创建）。

## MCP（仅 1 个）

```json
{
  "mcp": {
    "servers": {
      "openmontage-bootstrap": {
        "command": "python",
        "args": ["-m", "openmontage.mcp.bootstrap"],
        "cwd": "<REPO>",
        "env": {
          "PYTHONUTF8": "1",
          "OPENMONTAGE_PROJECTS_DIR": "<PROJECTS>",
          "OPENMONTAGE_P1_ALLOW_WRITES": "true"
        }
      }
    }
  }
}
```

说明：首版仍依赖仓内已有 Python；用户用系统 Python 或随后由 Skill01 建 venv 后，把 `command` 改成 venv 的 python。

## Skills

`skills.load.extraDirs` → `<REPO>/openmontage/skills`

启用：

- `openmontage-bootstrap-setup`
- `openmontage-bootstrap-produce`

（实现后目录名以仓库为准。）
