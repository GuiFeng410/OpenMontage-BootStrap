# OpenClaw P2 安装 — 高级 TTS

> 前置：完成 [../换机部署/01-已有eClaw-OpenClaw换机导入清单.md](../换机部署/01-已有eClaw-OpenClaw换机导入清单.md)（P1 底盘）

## 1. 环境变量（按你启用的商）

```powershell
$env:OPENMONTAGE_PROJECTS_DIR = "C:\Users\<you>\OpenMontageProjects"
$env:OPENMONTAGE_P1_ALLOW_WRITES = "true"   # Production Agent
$env:OPENMONTAGE_MAX_COST_USD = "2.00"
$env:OPENMONTAGE_ALLOWED_PROVIDERS = "openai,elevenlabs"  # 可选白名单

# 只配你要用的：
$env:OPENAI_API_KEY = "..."
# $env:ELEVENLABS_API_KEY = "..."
# $env:DASHSCOPE_API_KEY = "..."
# $env:DOUBAO_SPEECH_API_KEY = "..."
```

Key **不要**写进 Skill 文件。

## 2. 注册 MCP

合并 [templates/p2-providers-tts.mcp.json](./templates/p2-providers-tts.mcp.json) 到 Production Agent 的 `mcp.servers`。

```bash
openclaw mcp add openmontage-providers-tts \
  --command python \
  --arg -m \
  --arg openmontage.mcp.providers_tts \
  --cwd "<OPENMONTAGE_REPO_ROOT>" \
  --env OPENMONTAGE_PROJECTS_DIR=<PROJECTS_DIR> \
  --env PYTHONUTF8=1 \
  --env OPENMONTAGE_MAX_COST_USD=2.00
# 再按需附加各家 API Key 环境变量
```

## 3. 加载 Skill

`extraDirs` 已指向 `openmontage/skills` 时，启用：

```json5
entries: {
  "openmontage-providers-tts": { enabled: true }
}
```

Production Agent `skills` 增加 `openmontage-providers-tts`。

## 4. 权限

合并 [templates/p2-providers-tts.policy.json5](./templates/p2-providers-tts.policy.json5)：

- allow 增加：`openmontage-providers-tts__*`

## 5. 对话验收

> 旁白改用 OpenAI TTS，先估价和试听，通过后再生成全稿。

期望：`list_tts_providers` → `tts_dry_run` → 停轮 → `tts_sample` → 停轮 → `tts_generate`。
