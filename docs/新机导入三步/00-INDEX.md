# 新机导入三步（截止 P2 高级 TTS）

> 日期：2026-07-20  
> 适用：全新机器要把 OpenMontage 跑到「能导出最小成片」  
> 覆盖范围：P0（doctor）+ P1（零 Key 出片）+ P2（可选付费 TTS）  
> 不包含：AI 生图 / 生视频 / 其它 P2 插件

按顺序做完三步即可验收：

| 步 | 文件 | 做什么 |
|----|------|--------|
| 1 | [01-第一步-下载必要文件与运行时.md](./01-第一步-下载必要文件与运行时.md) | 拉仓、装 Python/Node/FFmpeg/Piper、建沙箱目录 |
| 2 | [02-第二步-配置MCP与Skill.md](./02-第二步-配置MCP与Skill.md) | 在 OpenClaw / eClaw 注册 MCP 与 Skill |
| 3 | [03-第三步-最小视频出片验证.md](./03-第三步-最小视频出片验证.md) | 跑通最小解说片，拿到 `renders/final.mp4` |

**仓库镜像（拉仓优先 GitHub，失败用 Gitee）：**

| 源 | URL |
|----|-----|
| GitHub（主） | https://github.com/GuiFeng410/OpenMontage-BootStrap |
| Gitee（备用） | https://gitee.com/rory_-3232/open-montage-boot-strap |

**前提假设：** 目标机已能安装软件；若使用 eClaw / OpenClaw，宿主本身需事先装好（本目录不写宿主安装细节）。

**更细的专项清单（可选深入）：**

- [../Mcp_Entity/换机部署/01-已有eClaw-OpenClaw换机导入清单.md](../Mcp_Entity/换机部署/01-已有eClaw-OpenClaw换机导入清单.md)
- [../Mcp_Entity/换机部署/02-P2-高级TTS换机清单.md](../Mcp_Entity/换机部署/02-P2-高级TTS换机清单.md)
- 门面 MCP 规划备忘：[../Mcp_Entity/Plan/03-门面MCP与Skill规划备忘.md](../Mcp_Entity/Plan/03-门面MCP与Skill规划备忘.md)

**一句话结论：** 只拷 MCP/Skill 不够；必须整仓（或最小目录子集）+ 本机运行时 + OpenClaw 注册，才能出片。
