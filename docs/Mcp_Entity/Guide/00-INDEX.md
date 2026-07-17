# eClaw Skill / MCP / 权限模型资料索引

> 调研日期：2026-07-17  
> 调研对象：深圳市伊登软件有限公司 eClaw  
> 核心结论：**eClaw 官方确认基于 OpenClaw，但未公开桌面版技术手册。现阶段能确认的“真实格式”主要来自 OpenClaw 上游官方文档；eClaw 的企业增强层必须通过实机或厂商资料二次验证。**

## 文档导航

1. [01-eClaw公开事实与证据边界.md](./01-eClaw公开事实与证据边界.md)  
   eClaw 官方能确认什么、不能确认什么，以及本次调研的证据等级。

2. [02-Skill真实格式与加载模型.md](./02-Skill真实格式与加载模型.md)  
   `SKILL.md` 的目录结构、YAML frontmatter、发现优先级、门控、安装与可见性。

3. [03-MCP配置格式与接入模型.md](./03-MCP配置格式与接入模型.md)  
   `openclaw.json` 中的 `mcp.servers`、stdio / HTTP 配置、OAuth、工具过滤与诊断命令。

4. [04-权限模型与企业安全控制.md](./04-权限模型与企业安全控制.md)  
   Skill 可见性、工具策略、沙箱、宿主机执行审批、MCP 工具过滤及 eClaw 企业安全增强。

5. [05-OpenMontage接入结论与实机核验清单.md](./05-OpenMontage接入结论与实机核验清单.md)  
   对 OpenMontage P0/P1/P2 规划的修正、推荐配置和必须向伊登/实机确认的问题。

6. 工程计划（同级目录）：[../Plan/00-INDEX.md](../Plan/00-INDEX.md)  
   基于本 Guide 编写的 P0 实现计划等；**先读本 Guide，再读 Plan**。

7. P0 交付：[../Mcp_P0/00-INDEX.md](../Mcp_P0/00-INDEX.md)  
   doctor MCP + router/gates Skill 的安装模板与验收清单。

8. P1 交付：[../Mcp_P1/00-INDEX.md](../Mcp_P1/00-INDEX.md)  
   media MCP + animated-explainer / production-contract Skills 的安装模板与验收清单。

8. P1 交付：[../Mcp_P1/00-INDEX.md](../Mcp_P1/00-INDEX.md)  
   media MCP + animated-explainer / production-contract Skills 的安装模板与验收清单。

## 一页结论

- **Skill 是文件夹，不是单个 RPC。** 最小结构为 `<skill>/SKILL.md`，正文是 Markdown，顶部是 YAML frontmatter。
- **Skill 本身不是安全边界。** `agents.*.skills` 只控制可见性；真正的执行边界来自工具策略、沙箱、OS 用户、凭据与执行审批。
- **OpenClaw 当前有原生 MCP 注册表。** 配置位于 `~/.openclaw/openclaw.json` 的 `mcp.servers`，支持 stdio、SSE、Streamable HTTP、OAuth、TLS/mTLS 和单服务器工具过滤。
- **MCP 工具还要通过 OpenClaw 工具策略。** MCP 配置成功不等于 Agent 一定能看到工具；profile、allow/deny、Agent 策略、沙箱策略和插件状态都会继续过滤。
- **eClaw 企业版公开宣称新增集中管控。** 包括远程删除高危 Skill/MCP、批量推送沙箱准入策略、异常隔离、脱敏、内容审计、统一日志与告警。
- **目前不能证明 eClaw 完全沿用 OpenClaw 文件路径或字段。** 伊登可能用桌面 UI、企业控制台或私有策略层封装/覆盖上游配置。

## 来源等级

| 等级 | 含义 | 本目录中的用法 |
|---|---|---|
| A | 伊登软件官网直接陈述 | 用于确认 eClaw 产品定位与企业安全能力 |
| B | OpenClaw 官方文档/官方仓库 | 用于确认上游真实 Skill、MCP、权限格式 |
| C | 第三方报道或展会资料 | 只作旁证，不作为配置依据 |
| D | 基于 A+B 的工程推断 | 明确标记为“推断/待验证” |

## 关键官方入口

- eClaw 官方详情页：https://www.edensoft.com.cn/product/1-24
- 伊登 AI 产品页：https://www.edensoft.com.cn/aiService
- OpenClaw Skill 格式：https://docs.openclaw.ai/clawhub/skill-format
- OpenClaw Skills：https://docs.openclaw.ai/tools/skills
- OpenClaw MCP：https://docs.openclaw.ai/cli/mcp
- OpenClaw 权限层次：https://docs.openclaw.ai/gateway/sandbox-vs-tool-policy-vs-elevated
- OpenClaw Exec Approvals：https://docs.openclaw.ai/tools/exec-approvals

