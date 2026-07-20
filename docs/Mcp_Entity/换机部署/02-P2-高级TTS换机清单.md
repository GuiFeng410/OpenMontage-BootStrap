# P2 换机清单 — 仅高级 TTS（在 P1 底盘之上）

> 前提：已完成 [01-已有eClaw-OpenClaw换机导入清单.md](./01-已有eClaw-OpenClaw换机导入清单.md)  
> 本切片：**只加付费/云端 TTS**；不做图/视频/其它流水线

---

## 1. 代码（随仓更新即可）

在已有 `<OPENMONTAGE_REPO_ROOT>` 上确保包含：

- [ ] `openmontage/mcp/providers_tts/`
- [ ] `openmontage/skills/openmontage-providers-tts/`
- [ ] `tests/mcp_p2/`（可选自检）
- [ ] 现有 `tools/audio/*_tts.py`（openai/elevenlabs/…）

无需单独再拷一份「TTS 小包」——跟仓走。

---

## 2. 本机额外配置

- [ ] 至少一个云 TTS 的 API Key（见下表）
- [ ] （建议）`OPENMONTAGE_MAX_COST_USD=2.00`
- [ ] （建议）`OPENMONTAGE_ALLOWED_PROVIDERS=openai` 或你的白名单

| 要用的商 | 环境变量 |
|----------|----------|
| OpenAI | `OPENAI_API_KEY` |
| ElevenLabs | `ELEVENLABS_API_KEY` |
| 阿里云百炼 | `DASHSCOPE_API_KEY` |
| 豆包语音 | `DOUBAO_SPEECH_API_KEY` |
| Google | `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` |
| Kling | `KLING_API_KEY` |

---

## 3. OpenClaw / eClaw 导入

- [ ] 注册 MCP：`python -m openmontage.mcp.providers_tts`  
  模板：[../Mcp_P2/templates/p2-providers-tts.mcp.json](../Mcp_P2/templates/p2-providers-tts.mcp.json)
- [ ] 启用 Skill：`openmontage-providers-tts`
- [ ] 工具策略放行：`openmontage-providers-tts__*`  
  模板：[../Mcp_P2/templates/p2-providers-tts.policy.json5](../Mcp_P2/templates/p2-providers-tts.policy.json5)
- [ ] Key 配在 MCP `env` 或系统环境，**不要**写进 Skill

安装说明：[../Mcp_P2/02-OpenClaw安装.md](../Mcp_P2/02-OpenClaw安装.md)

---

## 4. 部署步骤（最短路径）

1. 更新/同步 OpenMontage 仓到含 P2 TTS 的提交  
2. `pip install -r requirements.txt`（若依赖有变）  
3. 设置 `OPENMONTAGE_PROJECTS_DIR` + 所选 `*_API_KEY`  
4. OpenClaw 增加 `openmontage-providers-tts` server + Skill  
5. 自检：

```powershell
python -c "from openmontage.mcp.providers_tts.tools import list_tts_providers; import json; print(json.dumps(list_tts_providers(), ensure_ascii=False, indent=2)[:1500])"
```

6. 对 Production Agent：`旁白用 OpenAI，先估价再试听`

---

## 5. 一页勾选表

| # | 项 | ☐ |
|---|----|---|
| 1 | P1 换机清单已全部勾完 | |
| 2 | 仓内有 `providers_tts` + Skill | |
| 3 | 至少一个 TTS Key 已配置 | |
| 4 | OpenClaw 已注册 providers-tts MCP | |
| 5 | Skill 已启用 | |
| 6 | `list_tts_providers` 看到目标商 available | |
| 7 | 对话走出 dry_run → sample → generate | |

---

## 6. 明确不部署（本阶段）

- AI 生图 / 生视频 MCP  
- 分析 / 发布 MCP  
- 其它 pipeline Skill Pack  
