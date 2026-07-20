# 门面 MCP 与 Skill 规划备忘

> 状态：**首版已实现** → 见 [../Mcp_Bootstrap/00-INDEX.md](../Mcp_Bootstrap/00-INDEX.md)  
> 日期：2026-07-20（更新）

## 产品目标

新机只装 OpenClaw，配置 **1 个门面 MCP + 2 个 Skill**，流水线完成：拉仓 → 装环境 → 零 Key 最小出片。

## 已确认架构

| 项 | 结论 |
|----|------|
| 入口 | 对外 **1 个 MCP**（门面）；内部复用现有 doctor/media 逻辑，不重写出片 |
| 权限 | 允许自动改 PATH、装依赖；**高危默认 dry_run，确认后执行** |
| 启动 | 首版 **手动 clone**（不做 seed pip）；种子包后续迭代 |
| Skill01 | 检测 / 安装环境（驱动门面 MCP） |
| Skill02 | 零 Key **最简**出片；不接 diagram/stitch 全家桶；付费 TTS 仅可选教学 |
| Skill03 | 各类 Key / 扩展配置 — **以后再做** |
| 文档 | `docs/Mcp_Entity/Mcp_Bootstrap/` |
| 与旧 MCP | 保留 doctor/media/providers-tts；用户最小路径可不感知 |

## 仓库镜像（门面「拉仓」应支持双源）

| 优先级 | 平台 | URL |
|--------|------|-----|
| 1 主 | GitHub | https://github.com/GuiFeng410/OpenMontage-BootStrap |
| 2 备 | Gitee | https://gitee.com/rory_-3232/open-montage-boot-strap |

## 下一步

首版代码已落地。验证：`pytest tests/mcp_bootstrap`；OpenClaw 按 [../Mcp_Bootstrap/02-OpenClaw安装.md](../Mcp_Bootstrap/02-OpenClaw安装.md) 配置后实机试跑。  
后续迭代：seed pip 包、双源自动同步校验、produce 工具面扩展。
