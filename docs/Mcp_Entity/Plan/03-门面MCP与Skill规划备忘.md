# 门面 MCP 与 Skill 规划备忘

> 状态：已对齐需求，**待开始编写**（本文件只记结论，不代替实现）  
> 日期：2026-07-20

## 产品目标

新机只装 OpenClaw，配置 **1 个门面 MCP + 2 个 Skill**，流水线完成：拉仓 → 装环境 → 零 Key 最小出片。

## 已确认架构

| 项 | 结论 |
|----|------|
| 入口 | 对外 **1 个 MCP**（门面）；内部复用现有 doctor/media 逻辑，不重写出片 |
| 权限 | 允许自动改 PATH、装依赖、下载仓库到指定路径 |
| Skill01 | 检测 / 安装环境（驱动门面 MCP） |
| Skill02 | 零 Key 出片；付费 TTS 仅可选教学 |
| Skill03 | 各类 Key / 扩展配置 — **以后再做** |
| 与旧 MCP | 保留 doctor/media/providers-tts；用户最小路径可不感知 |

## 仓库镜像（门面「拉仓」应支持双源）

| 优先级 | 平台 | URL |
|--------|------|-----|
| 1 主 | GitHub | https://github.com/GuiFeng410/OpenMontage-BootStrap |
| 2 备 | Gitee | https://gitee.com/rory_-3232/open-montage-boot-strap |

门面 MCP 实现拉仓时：先试 GitHub，失败再试 Gitee（或由用户指定 URL）。

## 本地 git remote 约定（开发机）

| remote | URL |
|--------|-----|
| `bootstrap` | GitHub BootStrap |
| `gitee` | Gitee BootStrap |
| `origin` | 上游 calesthio/OpenMontage（勿误推除非明确要求） |

## 下一步（开始编写时）

1. 定工具清单：`bootstrap_*` + `produce_*`（薄封装）  
2. 危险操作确认点（改 PATH / 装系统包）  
3. 写 Skill01 / Skill02 + OpenClaw 模板  
4. 自检：`can_produce` 类检查通过后再进 Skill02  
