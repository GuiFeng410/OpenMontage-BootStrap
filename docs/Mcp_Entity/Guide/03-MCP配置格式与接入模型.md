# MCP 配置格式与接入模型

> 日期：2026-07-17  
> 证据等级：OpenClaw 官方文档（B）；eClaw 企业层为官方确认存在但 schema 未公开（A + D）

## 1. 两条 MCP 路径，不要混用

OpenClaw 官方把 MCP 分成两条完全不同的路径：

| 目标 | 用法 | 角色 |
|---|---|---|
| 让外部 MCP 客户端读写 OpenClaw 会话 | `openclaw mcp serve` | OpenClaw **作为 MCP Server** |
| 让 OpenClaw Agent 调用第三方 MCP | `openclaw mcp add/set/...` + `mcp.servers` | OpenClaw **作为 MCP Client 注册表** |

对 OpenMontage 来说，主路径是第二条：**把 OpenMontage 做成被 eClaw/OpenClaw 调用的 MCP Server，并写入其 `mcp.servers`。**

注意：

- `openclaw mcp *` **不读取** `config/mcporter.json`。
- 早期社区资料里常见的 mcporter 路径，已不是当前官方主注册表。
- 配置真相源是 OpenClaw 配置中的 `mcp.servers`。

## 2. 真实配置位置与结构

主配置文件（OpenClaw）：

```text
~/.openclaw/openclaw.json
```

核心结构：

```json
{
  "mcp": {
    "sessionIdleTtlMs": 600000,
    "apps": {
      "enabled": false
    },
    "servers": {
      "openmontage-doctor": {
        "command": "python",
        "args": ["-m", "openmontage_mcp.doctor"],
        "cwd": "C:/Users/example/OpenMontage",
        "env": {
          "OPENMONTAGE_PROJECTS_DIR": "C:/Users/example/OpenMontageProjects"
        },
        "toolFilter": {
          "include": [
            "doctor",
            "provider_menu_summary",
            "list_pipelines",
            "list_projects",
            "get_project_state",
            "get_next_stage",
            "validate_artifact",
            "validate_checkpoint",
            "estimate_cost",
            "init_project"
          ],
          "exclude": []
        }
      },
      "docs": {
        "url": "https://mcp.example.com/mcp",
        "transport": "streamable-http",
        "timeout": 20,
        "connectTimeout": 5,
        "auth": "oauth",
        "oauth": {
          "scope": "docs.read"
        },
        "sslVerify": true,
        "supportsParallelToolCalls": true,
        "toolFilter": {
          "include": ["search_*", "read_*"],
          "exclude": ["admin_*"]
        }
      }
    }
  }
}
```

## 3. 传输类型与字段

### 3.1 stdio（本地进程）

| 字段 | 含义 |
|---|---|
| `command` | 可执行文件（必需） |
| `args` | 参数数组 |
| `env` | 额外环境变量 |
| `cwd` / `workingDirectory` | 工作目录 |

适用：OpenMontage 本地 Python MCP、FFmpeg 探针、Piper 等本机工具。

### 3.2 SSE / HTTP

| 字段 | 含义 |
|---|---|
| `url` | 远程 MCP URL（必需） |
| `headers` | HTTP 头，如 Authorization |
| `auth: "oauth"` | 使用 `openclaw mcp login` 保存的 OAuth 凭据 |
| `timeout` / `requestTimeoutMs` | 请求超时 |
| `connectTimeout` / `connectionTimeoutMs` | 连接超时 |
| `sslVerify` | TLS 校验；仅可信私有端点可关 |
| `clientCert` / `clientKey` | mTLS |
| `supportsParallelToolCalls` | 是否提示可并行调用 |

### 3.3 Streamable HTTP

与 HTTP 类似，但显式设置：

```json
{
  "url": "https://mcp.example.com/stream",
  "transport": "streamable-http"
}
```

兼容说明：

- OpenClaw 规范拼写是 `transport: "streamable-http"`。
- `openclaw mcp set` 会把 CLI 风格的 `type: "http"` 归一化到同一配置形态。

## 4. 管理命令

| 命令 | 作用 |
|---|---|
| `openclaw mcp list` | 列出已保存服务器 |
| `openclaw mcp show [name]` | 查看定义 |
| `openclaw mcp status --verbose` | 不连服务器，打印解析后的传输/认证/过滤信息 |
| `openclaw mcp doctor [name] [--probe]` | 静态检查；`--probe` 再做实连 |
| `openclaw mcp probe [name]` | 实连接并列出 tools/resources/prompts |
| `openclaw mcp add <name> ...` | 用 flags 添加；默认先 probe 再保存 |
| `openclaw mcp set <name> '<json>'` | 整对象写入 |
| `openclaw mcp configure <name> ...` | 改 enable/filter/timeout/OAuth/TLS，不整表替换 |
| `openclaw mcp tools <name> --include/--exclude` | 单服务器工具过滤 |
| `openclaw mcp login/logout <name>` | OAuth 授权与清凭据 |
| `openclaw mcp reload` | 清理当前 CLI 进程缓存的 MCP runtime |
| `openclaw mcp unset <name>` | 删除定义 |

常见添加示例：

```bash
openclaw mcp add openmontage-doctor \
  --command python \
  --arg -m \
  --arg openmontage_mcp.doctor \
  --cwd "C:/Users/example/OpenMontage" \
  --env OPENMONTAGE_PROJECTS_DIR=C:/Users/example/OpenMontageProjects \
  --include "doctor,provider_menu_summary,list_pipelines,list_projects,get_project_state,get_next_stage,validate_artifact,validate_checkpoint,estimate_cost,init_project"

openclaw mcp doctor openmontage-doctor --probe
```

## 5. 工具过滤与运行时投影

关键行为：

1. `enabled: false` 保留定义，但排除出嵌入式 runtime 发现。
2. `toolFilter.include` / `exclude` 在 MCP tool 变成 OpenClaw tool **之前**过滤。
3. 若服务器声明 resources/prompts，会额外暴露 `resources_list`、`resources_read`、`prompts_list`、`prompts_get` 等工具名，同样受 include/exclude 约束。
4. 嵌入式 OpenClaw 在 `coding` / `messaging` profile 下暴露已配置 MCP 工具；`minimal` 会隐藏；`tools.deny: ["bundle-mcp"]` 可显式关掉。
5. 动态 tool-list 变更会使该 session 的缓存目录失效，下次发现/使用再刷新。
6. 某服务器连续请求/协议失败会被短暂暂停，避免拖垮整轮。
7. session 级 MCP runtime 默认空闲 10 分钟回收（`mcp.sessionIdleTtlMs`；`0` 关闭）。

**沙箱第二道门：**

若 Agent 处于 sandbox，仅配置 `mcp.servers` 不够。还要在 sandbox 工具策略中放行：

- `bundle-mcp`
- 或 `group:plugins`
- 或服务器前缀工具名/通配，如 `openmontage-doctor__doctor`、`openmontage-doctor__*`

否则会出现“MCP 已配置，但沙箱回合只剩内置工具”。

## 6. OpenClaw 作为 MCP Server（次要路径）

`openclaw mcp serve` 让外部客户端通过 stdio 访问 Gateway 会话：

```json
{
  "mcpServers": {
    "openclaw": {
      "command": "openclaw",
      "args": [
        "mcp",
        "serve",
        "--url",
        "wss://gateway-host:18789",
        "--token-file",
        "/path/to/gateway.token"
      ]
    }
  }
}
```

暴露工具包括：

- `conversations_list`
- `conversation_get`
- `messages_read`
- `attachments_fetch`
- `events_poll` / `events_wait`
- `messages_send`
- `permissions_list_open` / `permissions_respond`

这对 OpenMontage 不是主集成路径；只有当你想让 Cursor/其他 MCP 客户端直接操作 eClaw/OpenClaw 会话时才需要。

## 7. eClaw 企业层对 MCP 的公开增强

伊登官网明确提到：

- 可远程删除高危 **MCP**；
- 可批量推送沙箱准入规则；
- 可秒级隔离威胁沙箱；
- 有统一可观测与日志审计。

这意味着 eClaw 至少存在一层**高于单机 `mcp.servers` 的策略面**。可能形态包括：

1. 桌面 UI 包装 OpenClaw `mcp.servers`；
2. 企业控制台下发允许/拒绝的 MCP 白名单；
3. 运行时拦截未批准的 MCP tool call。

当前公开资料**没有**给出该策略面的 JSON schema。因此：

- OpenMontage 仍应按 OpenClaw `mcp.servers` 先做成可注册、可 probe 的标准 MCP；
- 同时准备“企业控制台登记/审批”步骤，而不是假设用户本地 JSON 一改就永久可用。

## 8. 给 OpenMontage 的推荐 MCP 切分

| Server | 建议暴露 | 不暴露 |
|---|---|---|
| `openmontage-doctor` | doctor / state / validate / estimate / init_project | 媒体生成、付费调用 |
| `openmontage-media` | Piper、compose job、probe、mix、stitch | 静默换模型、无确认付费 |
| `openmontage-providers-*` | dry_run + confirm 闸后的 provider 调用 | 密钥写入 Skill、自动烧钱 |

每个 server 都应：

1. 提供明确 JSON Schema；
2. 用 `toolFilter.include` 收紧；
3. 长任务用 `job_id` + poll，避免 stdio/HTTP 超时；
4. 所有写操作限制在 `OPENMONTAGE_PROJECTS_DIR`。
