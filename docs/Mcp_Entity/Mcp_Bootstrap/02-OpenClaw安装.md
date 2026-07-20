# Bootstrap — OpenClaw 安装

## 1. 手动 clone

```powershell
git clone https://github.com/GuiFeng410/OpenMontage-BootStrap.git
# 或
git clone https://gitee.com/rory_-3232/open-montage-boot-strap.git
```

## 2. 建议先装最小 Python 依赖（以便启动 MCP）

在仓库根：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

（也可用 Skill01 的 `install_python_deps`，但启动 MCP 前至少要能 `import mcp`。）

## 3. 注册 MCP

合并 [templates/bootstrap.mcp.json](./templates/bootstrap.mcp.json)，把 `command` 指到 venv 的 `python`，`cwd` 为仓库根。

## 4. 加载 Skill

`skills.load.extraDirs` → `<REPO>/openmontage/skills`  
启用：`openmontage-bootstrap-setup`、`openmontage-bootstrap-produce`

策略参考：[templates/bootstrap.policy.json5](./templates/bootstrap.policy.json5)

## 5. 对话试跑

> 先检测环境，给我看完整安装计划，不要直接改系统。

确认计划后再说「按计划执行」。出片交给 Skill02。
