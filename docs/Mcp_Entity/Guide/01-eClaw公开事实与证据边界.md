# eClaw 公开事实与证据边界

> 日期：2026-07-17  
> 证据等级：A/B/C/D（定义见 [00-INDEX.md](./00-INDEX.md)）

## 1. 产品身份

| 项 | 证据 | 等级 |
|---|---|---|
| 产品名 | eClaw | A |
| 厂商 | 深圳市伊登软件有限公司 | A |
| 官网 | https://www.edensoft.com.cn | A |
| 产品详情页 | https://www.edensoft.com.cn/product/1-24 | A |
| 上游框架 | 官方明确写“基于 OpenClaw 开源框架” | A |
| 推出时间 | 公司历程写明 2026 年推出 eClaw | A |
| 产品形态 | “一站式企业桌面应用” | A |
| 安装路径卖点 | “零门槛一键安装”“打开 > 配置 > 启动” | A |
| 部署方式 | 本地、云端、混合部署 | A |
| 接入方式 | web 端、移动端、IM 集成、API 调用 | A |

## 2. 官方公开能力（无配置细节）

伊登官方详情页公开宣称：

1. **内置 Skill 与 Agent 广场**：上千款安装即用。
2. **100+ 主流大模型智能路由**：按需调度模型。
3. **企业级管理权限精细管控**：面向团队协作。
4. **三重安全防线**：
   - 双向数据防护：上行识别/实时脱敏，下行回流检测/内容审计
   - 统一可观测：Dashboard、告警中心、日志审计
   - 远程管控：远程删除高危 Skill/MCP、批量推送沙箱准入规则、秒级隔离威胁沙箱
5. **多 Agent 生态**：核价、订单、商机、对账、HR、营销、编码、行业定制等场景 Agent。
6. **多智能体协同**：角色定义、任务拆解、协同执行。

这些内容足以证明：

- eClaw 把 **Skill** 和 **MCP** 视为一等能力对象；
- eClaw 有企业级 **权限 / 沙箱 / 远程管控** 层；
- eClaw 的产品叙事与 OpenClaw “Skill + Tool/MCP + Gateway/Sandbox” 架构一致。

但这些公开页**没有**给出：

- `SKILL.md` 样例；
- `openclaw.json` / `mcp.servers` 样例；
- 桌面端配置文件路径；
- 企业策略 schema；
- 权限字段、审批文件、沙箱 Docker 配置；
- 下载包、SDK、开发者文档。

## 3. 本次调研发现的关键缺口

| 期望资料 | 当前状态 |
|---|---|
| 官方开发者文档 / API 手册 | 未发现 |
| 官方 Skill 模板仓库 | 未发现 |
| 官方 MCP 配置样例 | 未发现 |
| 官方权限策略 schema | 未发现 |
| 官网搜索可索引的技术页 | 几乎没有；详情页靠前端路由 `/product/1-24` 暴露 |
| 公开下载安装包 | 未发现 |
| GitHub 官方 eClaw 源码仓 | 未发现伊登官方仓库 |

因此，对“真实 Skill 格式 / MCP 配置 / 权限模型”的技术答案，只能按以下规则成立：

> **上游 OpenClaw 文档 = 当前最可靠的技术基线；eClaw 企业层 = 官方确认存在，但 schema 未公开。**

## 4. 与 OpenClaw 的关系（确认 vs 推断）

### 已确认

- eClaw **基于 OpenClaw**（伊登官网原文）。
- eClaw 面向企业桌面，强调 Skill/Agent 广场、MCP 管控、沙箱与远程策略。

### 合理推断（D）

- eClaw 很可能兼容或包装 OpenClaw 的：
  - `SKILL.md` 目录格式
  - `mcp.servers` 注册表
  - tool policy / sandbox / exec approvals 分层
- eClaw 很可能在 OpenClaw 之上增加：
  - 企业控制台
  - 集中策略推送
  - 高危 Skill/MCP 远程删除
  - 数据脱敏与审计
  - 沙箱准入规则的批量管理

### 不能直接假定

- 配置文件一定叫 `~/.openclaw/openclaw.json`
- 企业策略一定直接编辑同一份 JSON
- 桌面 UI 一定暴露全部 OpenClaw CLI（`openclaw mcp add` 等）
- Skill allowlist 一定等同于安全边界
- eClaw 没有改过上游默认路径、默认权限或 MCP 投影规则

## 5. 对 OpenMontage 规划的直接含义

`docs/chance_file/03-P0-P1-P2阶段最终实现形态.md` 已正确指出：

> 若 eClaw 的 Skill 格式、MCP 传输方式或权限模型不同，只需增加适配层，不改变职责边界。

本次调研进一步收紧这句话：

1. **先按 OpenClaw 上游格式设计适配层。**
2. **把 eClaw 桌面/企业控制台当作可能存在的第二配置面。**
3. **所有写路径、权限默认值、MCP 是否原生注册，都必须用实机验证，不能只靠官网文案。**

## 6. 推荐验证方式

优先级从高到低：

1. 拿到 eClaw 安装包或试用环境，检查本机配置目录与导出配置。
2. 向伊登索取开发者/集成文档，重点问 Skill 导入、MCP 注册、策略 schema。
3. 用一个最小 `SKILL.md` + 一个本地 stdio MCP 做兼容性探针。
4. 对照 OpenClaw 官方文档字段，记录哪些字段被桌面层隐藏、重命名或增强。

详细清单见 [05-OpenMontage接入结论与实机核验清单.md](./05-OpenMontage接入结论与实机核验清单.md)。
