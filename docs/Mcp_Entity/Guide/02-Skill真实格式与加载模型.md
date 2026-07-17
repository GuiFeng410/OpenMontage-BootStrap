# Skill 真实格式与加载模型

> 日期：2026-07-17  
> 证据等级：以 OpenClaw 官方文档（B）为主；eClaw 兼容性仍为推断（D）

## 1. 最小真实格式

Skill **不是**单个 JSON/RPC，而是一个目录：

```text
my-skill/
  SKILL.md                 # 必需（也接受 skill.md；遗留 skills.md）
  scripts/                 # 可选
  references/              # 可选
  assets/                  # 可选
  .clawhubignore           # 可选（发布忽略）
  .clawhub/origin.json     # 安装后由 CLI 写入
```

`SKILL.md` = YAML frontmatter + Markdown 正文。

最小可用示例：

```markdown
---
name: openmontage-router
description: Diagnose OpenMontage capabilities and give 3 starter prompts.
---

# OpenMontage Router

当用户说“我想做视频 / 现在能做什么”时：

1. 调用 MCP `doctor` 与 `provider_menu_summary`
2. 用白话说明当前能力
3. 只给出本机可执行的 3 条提示词
4. 明确生产请求时，切换到 animated-explainer Skill Pack
```

## 2. Frontmatter 字段

### 2.1 必需字段

| 字段 | 规则 |
|---|---|
| `name` | 唯一 slug：小写字母、数字、连字符；建议与目录名一致；1–64 |
| `description` | 一行摘要；建议 <160 字符；会出现在 Agent 提示词与 slash 发现 |

### 2.2 常用可选字段

| 字段 | 作用 |
|---|---|
| `user-invocable` | 默认 `true`；是否暴露为 `/skill` slash command |
| `disable-model-invocation` | `true` 时不注入常规系统提示，但仍可通过 slash 调用 |
| `command-dispatch` | 设为 `tool` 时，slash 命令绕过模型，直接调工具 |
| `command-tool` | 与 `command-dispatch: tool` 配套的工具名 |
| `command-arg-mode` | 默认 `raw`；把原始参数串转给工具 |
| `homepage` | Skills UI 中的网站链接 |
| `version` | ClawHub 发布常用 |

### 2.3 运行时门控：`metadata.openclaw`

```yaml
---
name: openmontage-media
description: Drive zero-key media tools for animated explainers.
metadata:
  openclaw:
    requires:
      bins:
        - ffmpeg
        - node
      env:
        - OPENMONTAGE_PROJECTS_DIR
      anyBins:
        - piper
        - piper-tts
      config:
        - tools.exec.host
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
        description: Project root for artifacts and renders
      - name: PIPER_MODEL_DIR
        required: false
        description: Optional Piper model directory
    os:
      - win32
      - darwin
      - linux
    emoji: "🎬"
    homepage: https://example.com/openmontage
    install:
      - kind: node
        package: some-helper
        bins: [some-helper]
---
```

| 字段 | 含义 |
|---|---|
| `requires.env` | 必须存在的环境变量 |
| `requires.bins` | PATH 上必须全部存在的二进制 |
| `requires.anyBins` | 至少一个二进制存在 |
| `requires.config` | `openclaw.json` 中必须为真的配置路径 |
| `primaryEnv` | 主凭据环境变量；可映射 `skills.entries.<name>.apiKey` |
| `envVars[]` | 带描述的环境变量声明；可选变量用 `required: false` |
| `always` | `true` 时跳过其它门控，始终纳入 |
| `os` | 平台限制，如 `["win32"]` |
| `install[]` | UI/安装器用的依赖安装规格：`brew` / `node` / `go` / `uv` |
| `skillKey` | 覆盖配置键；默认用 `name` |
| `emoji` / `homepage` | UI 展示 |

门控规则：

- 没有 `metadata.openclaw` 的 Skill，默认合格，除非被配置禁用。
- `requires.env` 表示“没有就不能跑”；可选变量不要放进 `requires.env`。
- `requires.bins` 在**宿主机**检查；若 Agent 进沙箱，容器内也必须有对应二进制。

## 3. 加载优先级

OpenClaw 按以下顺序加载，同名 Skill 时**高优先级覆盖低优先级**：

| 优先级 | 来源 | 默认路径 |
|---|---|---|
| 1 最高 | Workspace skills | `<workspace>/skills` |
| 2 | Project agent skills | `<workspace>/.agents/skills` |
| 3 | Personal agent skills | `~/.agents/skills` |
| 4 | Managed / local skills | `~/.openclaw/skills` |
| 5 | Bundled skills | 安装包自带 |
| 6 最低 | Extra dirs / plugin skills | `skills.load.extraDirs` + plugin |

补充规则：

- 可在根目录下最多 6 层深度搜索 `SKILL.md`。
- 子目录只用于组织；Skill 名称与 slash 命令来自 frontmatter `name`。
- Node-hosted skills 可从已连接节点发布；与本地同名时，本地/Gateway 保留原名，节点 Skill 使用带前缀的名字。

## 4. 配置面：`skills.*` 与 Agent 可见性

主配置文件（OpenClaw）：`~/.openclaw/openclaw.json`

```json5
{
  skills: {
    allowBundled: ["gemini", "peekaboo"],
    load: {
      extraDirs: ["~/Projects/agent-scripts/skills"],
      allowSymlinkTargets: ["~/Projects/manager/skills"],
      watch: true,
      watchDebounceMs: 250
    },
    entries: {
      "openmontage-router": {
        enabled: true,
        env: {
          OPENMONTAGE_PROJECTS_DIR: "C:/Users/example/OpenMontageProjects"
        }
      },
      sag: { enabled: false }
    }
  },
  agents: {
    defaults: {
      skills: ["openmontage-router", "openmontage-gates"]
    },
    list: [
      { id: "writer" }, // 继承 defaults
      { id: "docs", skills: ["docs-search"] }, // 完全替换，不合并
      { id: "locked-down", skills: [] } // 无 Skill
    ]
  }
}
```

关键语义：

- `skills.entries.<key>.enabled: false` 可禁用已安装 Skill。
- `agents.list[].skills` **替换** defaults，不合并。
- `skills.entries.*.env` / `apiKey` 只注入**宿主机进程**当前 Agent 回合，**不自动进入沙箱**。
- Skill 快照在 session 启动时固定；`SKILL.md` 变更或 watcher 触发后，下一轮/新 session 生效。

## 5. 安装与发布通道

| 动作 | 命令/方式 |
|---|---|
| 安装 ClawHub Skill 到 workspace | `openclaw skills install @owner/<slug>` |
| 安装到本机共享目录 | 加 `--global` → `~/.openclaw/skills` |
| 从 Git 安装 | `openclaw skills install git:owner/repo@ref` |
| 从本地目录安装 | `openclaw skills install ./path/to/skill --as my-tool` |
| 校验信任信封 | `openclaw skills verify @owner/<slug>` |
| 发布到 ClawHub | `clawhub skill publish ./path/to/skill` |

发布限制（ClawHub）：

- 仅接受文本类文件；
- 总包体上限约 50MB；
- 许可证固定 `MIT-0`；
- 不支持付费 Skill / 定价元数据。

## 6. 对 eClaw 的含义

伊登官网确认 eClaw：

- 有 **Skill 广场**；
- 可 **安装即用**；
- 可被企业策略 **远程删除高危 Skill**。

因此对 OpenMontage 的建议是：

1. **交付物按 OpenClaw `SKILL.md` 目录格式准备。**
2. **不要把整仓 AGENT_GUIDE 塞进一个 Skill；拆成多个小 Pack。**
3. **每个 Pack 写清 `requires.bins/env`，让 eClaw/OpenClaw 在缺依赖时自动隐藏或提示。**
4. **不要假设 Skill 能授权执行危险操作。** Skill 只教 Agent 怎么做；能不能做由权限模型决定。

实机仍需确认：

- eClaw 是否直接读取 `~/.openclaw/skills`；
- 桌面“Skill 广场”是否等于 ClawHub，或另有企业私有目录；
- 是否支持 `openclaw skills install ./local-dir`；
- 企业策略是否会覆盖 `agents.*.skills`。
