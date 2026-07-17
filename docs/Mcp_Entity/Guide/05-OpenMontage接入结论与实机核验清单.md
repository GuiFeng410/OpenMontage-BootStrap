# OpenMontage 接入结论与实机核验清单

> 日期：2026-07-17  
> 目的：把本目录调研结果落到 OpenMontage × eClaw 的可执行下一步

## 1. 现在可以确定的设计决策

1. **Skill 按 OpenClaw `SKILL.md` 目录格式交付。**  
   不要发明第二套 Skill JSON，除非实机证明 eClaw 不接受该格式。

2. **MCP 按 OpenClaw `mcp.servers` 注册。**  
   先做标准 stdio MCP，再用 `openclaw mcp doctor --probe` / eClaw 等价 UI 验证。

3. **权限按“可见性 ≠ 授权”设计。**  
   Skill Pack 只负责导演；真正执行边界靠 tool policy、sandbox、exec approvals、MCP toolFilter 与企业策略。

4. **不要做 `make_video()` 单工具。**  
   与既有 P0/P1/P2 结论一致；eClaw 的人审/协同叙事更要求多轮对话关卡，而不是一次 RPC 出片。

5. **为 eClaw 企业层预留适配。**  
   官网已明确存在远程删除 Skill/MCP、沙箱准入批量推送、审计与脱敏。本地配置不是最终权限真相源。

## 2. 推荐交付形态（对照本目录）

### Skill Packs

| Pack | 形式 | 关键 frontmatter |
|---|---|---|
| `openmontage-router` | `<dir>/SKILL.md` | `name`, `description`, `requires.bins/env` |
| `openmontage-gates-intro` | 同上 | 无危险 bins |
| `openmontage-animated-explainer` | 多 stage Skill 或按 stage 拆分目录 | 声明 Remotion/FFmpeg/Piper |
| `openmontage-l3-*` | 可选 | 按技术门控 |

### MCP Servers

| Server | 传输 | 过滤 |
|---|---|---|
| `openmontage-doctor` | stdio | 仅诊断/状态/校验 |
| `openmontage-media` | stdio + job poll | 零 Key 媒体白名单 |
| `openmontage-providers-*` | stdio/HTTP | dry_run + confirm |

### 权限基线

- P0：几乎只允许 doctor MCP；拒绝 runtime/browser。
- P1：放开 media MCP + 受控 read；exec 走 allowlist/on-miss。
- P2：provider MCP 单独授权，永不默认全局 full。

## 3. 对既有 chance_file 规划的修正

`docs/chance_file/03-...` 里“对 eClaw 的最低假设”基本成立，但应改成：

| 原假设 | 现状 |
|---|---|
| 支持安装多个 Markdown Skill | **高度可信**（OpenClaw 原生即如此；eClaw 官方强调 Skill 广场） |
| 连接 stdio 或本地 HTTP MCP | **高度可信**（OpenClaw 原生支持；eClaw 官方点名 MCP 管控） |
| 连续对话保留 project ID | 仍合理，但是产品行为假设，非官网技术证明 |
| 读取 MCP 返回的本地路径 | 仍合理，需实机确认沙箱/路径映射 |
| 关卡处停轮等待用户 | 与 Agent 对话模型一致，但 eClaw UI 是否强制停轮需验证 |

新增硬约束：

- 配置适配层应优先兼容 OpenClaw；
- 同时把“企业策略允许 Skill/MCP”作为上线 checklist；
- 在拿到 eClaw 实机前，不要把 `~/.openclaw/...` 写成唯一安装说明。

## 4. 实机核验清单（建议原样执行）

### A. Skill

- [ ] 能否导入本地目录形式的 Skill（含 `SKILL.md`）？
- [ ] frontmatter `name/description/metadata.openclaw` 是否被识别？
- [ ] `requires.bins` / `requires.env` 失败时，Skill 是隐藏、报错还是仍可见？
- [ ] 同名 Skill 的优先级是否符合 OpenClaw 文档？
- [ ] 企业控制台能否禁用/删除该 Skill，本地是否同步消失？

### B. MCP

- [ ] 是否存在等价于 `mcp.servers` 的配置面？
- [ ] 能否注册 stdio server：`python -m openmontage_mcp.doctor`？
- [ ] 是否支持 `toolFilter.include/exclude`？
- [ ] 沙箱开启后，是否还需放行 `bundle-mcp` / `server__*`？
- [ ] OAuth / headers / env 明文是否被 UI 告警或禁止？
- [ ] 企业策略能否远程移除某个 MCP？

### C. 权限

- [ ] 默认 sandbox mode / workspaceAccess 是什么？
- [ ] 默认 exec mode 是 deny、allowlist、ask 还是 full？
- [ ] 是否存在 `exec-approvals.json` 或 Windows native approvals？
- [ ] Skill allowlist 是否被误宣传成安全边界？
- [ ] 脱敏、审计、告警是否对 MCP tool call 生效？

### D. 路径与部署

- [ ] 实际配置根目录是 `~/.openclaw`、自定义 state dir，还是 eClaw 专属目录？
- [ ] 项目落盘是否允许自定义 `OPENMONTAGE_PROJECTS_DIR`？
- [ ] 沙箱内能否看到宿主机项目目录；只读还是读写？
- [ ] 本地 / 云端 / 混合部署下，MCP 是本机进程还是远端网关？

## 5. 向伊登索取资料时的最小问题单

1. eClaw 是否 100% 兼容 OpenClaw 的 `SKILL.md` 与 `mcp.servers`？
2. 企业策略的导出格式是什么？能否提供 schema？
3. 推荐第三方 Skill/MCP 的安装方式是 CLI、桌面导入，还是控制台分发？
4. Windows 上的执行审批与沙箱默认策略是什么？
5. 是否有开发者文档、示例 Skill、示例 MCP、权限模板？
6. “远程删除高危 Skill/MCP”的判定规则与恢复流程是什么？

联系入口（官网公开）：

- 热线：400 830 0095
- 站点：https://www.edensoft.com.cn/contact
- 产品页：https://www.edensoft.com.cn/product/1-24

## 6. 建议的下一步工程顺序

```text
1. 用本目录结论更新 P0 技术设计假设
2. 先实现 openmontage-doctor MCP + router Skill（OpenClaw 格式）
3. 在纯 OpenClaw 环境跑通 probe / doctor / 3 条提示词
4. 再拿 eClaw 实机做差异表（路径、UI、企业策略）
5. 差异稳定后，再写 eClaw 专用安装说明与适配层
```

**已落地：** 第 1 步对应实现计划见 [../Plan/01-P0实现计划.md](../Plan/01-P0实现计划.md)。编码需待该计划中的「批准清单」确认后再开始。

在第 4 步完成前，任何“eClaw 专用配置文件格式已确认”的说法都不可成立。

## 7. 资料来源摘要

### A. 伊登 / eClaw

- https://www.edensoft.com.cn/
- https://www.edensoft.com.cn/aiService
- https://www.edensoft.com.cn/about
- https://www.edensoft.com.cn/product/1-24

### B. OpenClaw 官方

- https://docs.openclaw.ai/clawhub/skill-format
- https://docs.openclaw.ai/tools/skills
- https://docs.openclaw.ai/tools/creating-skills
- https://docs.openclaw.ai/tools/skills-config
- https://docs.openclaw.ai/cli/mcp
- https://docs.openclaw.ai/tools
- https://docs.openclaw.ai/gateway/sandbox-vs-tool-policy-vs-elevated
- https://docs.openclaw.ai/tools/exec-approvals
- https://docs.openclaw.ai/tools/multi-agent-sandbox-tools
- https://docs.openclaw.ai/gateway/security

### C. 旁证

- 展会/媒体对伊登 AI 产品矩阵与 eClaw 参展的报道（只证明产品存在与市场叙事，不证明配置格式）
