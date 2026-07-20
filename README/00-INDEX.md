# 操作说明集合（README/）

> BootStrap 用户请按顺序阅读。更细的工程归档在 `docs/Mcp_Entity/`（会提交进仓库）。

## 两种用法

| 用法 | 适合谁 | 从哪开始 |
|------|--------|----------|
| **A. 安装 Skill（推荐新机）** | OpenClaw 已装好，还没有本仓库 | [00-安装Skill-先拷贝到OpenClaw.md](./00-安装Skill-先拷贝到OpenClaw.md) |
| **B. 已手动 clone** | 仓库已在本地 | 从 [01](./01-手动克隆与配置OpenClaw.md) 起 |

拉仓后，仓库内会包含：

- 门面 MCP：`openmontage/mcp/bootstrap/`（`python -m openmontage.mcp.bootstrap`）  
- Skill：`openmontage-bootstrap-setup` / `openmontage-bootstrap-produce`  
- 安装 Skill 源文件：`openmontage-bootstrap-installer`（也可单独拷到 OpenClaw）

## 阅读顺序（已 clone 之后）

| 步 | 文件 | 做什么 |
|----|------|--------|
| 0 | [00-安装Skill-先拷贝到OpenClaw.md](./00-安装Skill-先拷贝到OpenClaw.md) | （可选）只装安装 Skill，用一句话拉仓并口述配置 |
| 1 | [01-手动克隆与配置OpenClaw.md](./01-手动克隆与配置OpenClaw.md) | clone + 口述/手配门面 MCP 与 2 个 Skill |
| 2 | [02-环境检测与安装.md](./02-环境检测与安装.md) | setup：计划 → 确认 → 安装 → verify |
| 3 | [03-零Key最小出片.md](./03-零Key最小出片.md) | produce → `final.mp4` |

## 详细归档

- 门面：[../docs/Mcp_Entity/Mcp_Bootstrap/00-INDEX.md](../docs/Mcp_Entity/Mcp_Bootstrap/00-INDEX.md)
- 新机三步：[../docs/新机导入三步/00-INDEX.md](../docs/新机导入三步/00-INDEX.md)
- 上游长 README：[./archive/](./archive/)

## 原则

- 根目录短 `README.md` / `README_zh-CN.md` 作首页  
- 长操作说明在本目录  
- **不**忽略整个 `docs/`  
- 安装 Skill **不自动改** OpenClaw 配置，只口述步骤  
