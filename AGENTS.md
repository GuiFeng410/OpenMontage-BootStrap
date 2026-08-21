# OpenMontage BootStrap — Agent 入口

**产品版：`v0.6.0`** · **契约修订：`doc-r1`（2026-08-21）**

回滚文档：用 git 历史/标签；**不要**把 Skill 钉死在契约号上。

---

## 读序（强制）

1. **本文**（门口：是什么、缺步、通道一句、Skill 一行）
2. [`AGENT_GUIDE.md`](AGENT_GUIDE.md)（短版中文契约：流程 + 职责 + 双通道）
3. **当前步**对应 `skills/bootstrap/.../SKILL.md`
4. 需要时再深挖：`README/agent/`、交接、[`AGENT_GUIDE-upstream.md`](AGENT_GUIDE-upstream.md)

**默认不要读上游附录。** 仅用户点名 pipeline / atelier，或七 Skill 盖不住时再开。

### 冲突裁决

`AGENTS` + 短 `AGENT_GUIDE` 通道规则 → 当前通道 Skill 章节 → Skill 旧写法让步于通道 → 上游仅按需。  
03/04 正文与 B2 面板尚未对齐：**先听通道规则**；Skill 正文下一轮再改。

---

## 本仓是什么

**OpenMontage-BootStrap**：在上游 OpenMontage 上叠 **门面 MCP + BootStrap 七 Skill**，闭环「安装 → 环境 → 简报 → 出片」。日常「做个视频」走七 Skill，不要直接 improvise 调工具。

- 人读操作：[`README/00-INDEX.md`](README/00-INDEX.md)
- 本机草稿：`Agent-ReadMe/`（gitignore，非公开真源）
- 发布：日常 `gitee` + `bootstrap`（**永不** `origin`）

---

## Goal1：熟悉项目

读序：`AGENTS` → 短 `AGENT_GUIDE` → [`PRODUCT_MAP`](README/agent/PRODUCT_MAP.md) / [`PROJECT_CONTEXT`](README/agent/PROJECT_CONTEXT.md) → `Agent-Docs/Phase/A_01-session-handoff/` 最新交接。

---

## Goal2：出片（缺步路由）

```text
【装机】01 → 02（verify_ready）
【出片】03（扫 Key · 锁简报）→ 04 → renders/final.mp4
【补充】05 字幕配乐 · 06 Key · 07 排错
```

| 缺啥 | 走哪 |
|------|------|
| 未装齐 | **01** |
| 未 verify_ready | **02** |
| 简报未锁 | **03** |
| 已锁要出片 | **04** |
| 字幕/BGM | **05** |
| 收费 Key | **06** |
| 工具失败 | **07** |

硬规则：未就绪禁止出片；表 2/3 未确认禁止交接 04；先计划再改系统；不静默付费、不静默换渠道。

### 双通道（一句）

| 通道 | 何时 | Agent 做什么 |
|------|------|----------------|
| **网站（默认）** | 电商/模糊「做个视频」、未声明只要聊天 | 给看板 URL；用面板 intent + runner |
| **纯聊天** | 用户明确只要聊天 / 不要看板 | **不要求** URL；聊天 Grill / 检查点推进 |

---

## 七个 BootStrap Skill（一行）

仓内：`skills/bootstrap/`。宿主 extraDirs：`skills/bootstrap`、`skills/providers`、`skills/production`。

| # | Skill | 一行 |
|---|--------|------|
| 01 | installer | 新装/更新：5 MCP + Skill 齐 |
| 02 | setup | 环境 → 确认 → 安装 → `verify_ready` |
| 03 | usercheck | 扫 Key；默认电商；定通道 |
| 04 | produce | 按已锁简报出片（默认不重选档） |
| 05 | captions-music | 字幕 / 本地 BGM（可后置） |
| 06 | providers | 收费 / Stock Key（空 Key 禁调） |
| 07 | error-handling | capture → plan → apply（≤3） |

环境口径（02）：旁白 **Edge-TTS**；HyperFrames 建议装可跳过；Piper 仅离线可选。

---

## 本机工作区与状态

因 Windows 大小写不敏感，用 `Agent-Docs/` · `Agent-ReadMe/` · `Agent-Temp/`（**默认不提交**）。

| 文件/目录 | 用途 |
|-----------|------|
| `.openmontage/install-state.json` | 本机就绪快照；**开口先读**；无密钥 |
| `projects/` | 出片工作区（gitignore） |
| `Agent-Docs/` | 计划/阶段/交接（name-to-docs） |

`verify_ready` 为真 → 禁止再走安装话术，须给看板（默认通道）或按纯聊天续作。

---

## Git（一行）

双推 = `gitee` + `bootstrap`；**Never** `git push origin`。细节见短 `AGENT_GUIDE` §9。

---

## 版本身份

- 逻辑地图：[`README/agent/PRODUCT_MAP.md`](README/agent/PRODUCT_MAP.md)
- 包：`src/openmontage/`；内核：`src/openmontage/lib/`
- 清单：[`distribution/manifests/release-manifest.json`](distribution/manifests/release-manifest.json)
- 上游深读：[`AGENT_GUIDE-upstream.md`](AGENT_GUIDE-upstream.md)
