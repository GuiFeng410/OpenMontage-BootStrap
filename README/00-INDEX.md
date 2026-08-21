# 操作说明集合（README/）

> 前提：**本机已有 OpenClaw**（本文不写 OpenClaw 下载安装）。  
> 公开操作以本目录为准；具体执行以仓内 Skill 为准。  
> **交付：** 主路径为 git 克隆 + Agent；见仓根 [`README_zh-CN.md`](../README_zh-CN.md) / [`AGENTS.md`](../AGENTS.md)。

## 当前目录（二分前）

| 目录 | 用途 | 拟归（Plan/34） |
|------|------|-----------------|
| [说明/](./说明/) | 怎么选、装什么、免费/收费、字幕配乐 | `human/` |
| [配置/](./配置/) | MCP 模板 + 字段清单（无操作步骤） | `human/` |
| [错误处理/](./错误处理/) | 典型错误集合 + Error-Handling 说明 | `human/` |
| [archive/](./archive/) | 旧版全量 README | `human/archive/` 或仓根 `archive/`（待批） |

目标树：`README/human/` + `README/agent/`。**不属于二者**的进本机 `Agent-ReadMe/`（gitignore）。搬家执行前见本机 `Agent-Docs/Plan/34-README人机文档二分-v1.0.md`。

## 阅读顺序

| 步 | 文档 | 做什么 |
|----|------|--------|
| 1 | [说明/01-安装配置与环境.md](./说明/01-安装配置与环境.md) | 5 MCP + 6 Skill；模糊需求先 openmontage-bootstrap-03-usercheck |
| 2 | [说明/02-免费与收费能力.md](./说明/02-免费与收费能力.md) | 轻度/中度/重度；免费 vs 收费对照 |
| 3 | [说明/03-字幕与配乐.md](./说明/03-字幕与配乐.md) | 可选：文稿字幕 + BGM |
| 4 | [说明/04-剪辑标签与Agent驱动剪辑.md](./说明/04-剪辑标签与Agent驱动剪辑.md) | 剪辑标签：轻量标记 → Agent 确认 → 重合成 |
| — | [配置/00-字段清单.md](./配置/00-字段清单.md) | 抄模板与 env 名时查阅 |
| — | [错误处理/](./错误处理/) | 失败时：capture → plan → apply（≤3） |

## 原则

- 根目录短 `README.md` / `README_zh-CN.md` + `AGENTS.md` 作人/机首页  
- 安装 Skill **不自动改** OpenClaw 配置，只口述  
- 字段与 JSON 只在 **配置/**；步骤细节在 Skill  
- `CLAUDE.md` / `CURSOR.md` 等宿主文件**留仓根**，不迁入 README  
