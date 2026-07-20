# 操作说明集合（README/）

> BootStrap 用户请按顺序阅读。公开操作说明以本目录为准。

## 两种用法

| 用法 | 适合谁 | 从哪开始 |
|------|--------|----------|
| **A. 安装 Skill（推荐新机）** | OpenClaw 已装好，还没有本仓库 | [00-安装Skill-先拷贝到OpenClaw.md](./00-安装Skill-先拷贝到OpenClaw.md) |
| **B. 已手动 clone** | 仓库已在本地 | 从 [01](./01-手动克隆与配置OpenClaw.md) 起 |

拉仓后，仓库内会包含：

- 门面 MCP + 三个 providers MCP（安装时一并注册；付费 Key 可后填）  
- Skill：setup / produce / providers（Skill03） / installer  
- MCP 模板：[templates/](./templates/)

## 阅读顺序（已 clone 之后）

| 步 | 文件 | 做什么 |
|----|------|--------|
| 0 | [00-安装Skill-先拷贝到OpenClaw.md](./00-安装Skill-先拷贝到OpenClaw.md) | （可选）只装安装 Skill，用一句话拉仓并口述配置 |
| — | [流程简版-OpenClaw安装到出片.txt](./流程简版-OpenClaw安装到出片.txt) | 一页流程（有 OpenClaw 时怎么选） |
| 1 | [01-手动克隆与配置OpenClaw.md](./01-手动克隆与配置OpenClaw.md) | clone + 口述/手配 4 MCP 与 3 Skill |
| 2 | [02-环境检测与安装.md](./02-环境检测与安装.md) | setup：计划 → 确认 → 安装 → verify |
| 3 | [03-零Key最小出片.md](./03-零Key最小出片.md) | produce → `final.mp4` |
| 4 | [04-收费Providers接入.md](./04-收费Providers接入.md) | （可选）往已注册 MCP 填付费 Key |

## 其它

- 新机三步：[../docs/新机导入三步/00-INDEX.md](../docs/新机导入三步/00-INDEX.md)
- 上游长 README：[./archive/](./archive/)

## 原则

- 根目录短 `README.md` / `README_zh-CN.md` 作首页  
- 长操作说明在本目录  
- 安装 Skill **不自动改** OpenClaw 配置，只口述步骤  
