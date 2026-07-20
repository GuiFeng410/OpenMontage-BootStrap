# P2 实现计划：高级 TTS（providers-tts）— 其它插件暂缓

> 日期：2026-07-20  
> 状态：**已实现（TTS 切片）** → 交付见 [../Mcp_P2/00-INDEX.md](../Mcp_P2/00-INDEX.md)  
> 范围锁定：仅 **高级/付费 TTS**；不做 image/video/analysis/publish/其它流水线 Pack  
> 终态依据：[../../chance_file/03-P0-P1-P2阶段最终实现形态.md](../../chance_file/03-P0-P1-P2阶段最终实现形态.md) §P2（MCP-C providers-tts 子集）

---

## 0. 一句话目标

在 P0/P1 之上增加可选插件 **`openmontage-providers-tts`**：用户可在 explainer 资产阶段选择更自然的云端 TTS；必须 **先估价 → 再试听 → 再批量**，失败不静默换商。

---

## 1. 范围

### 做

| 项 | 说明 |
|----|------|
| MCP | `python -m openmontage.mcp.providers_tts` |
| 工具 | `list_tts_providers` · `tts_dry_run` · `tts_sample` · `tts_generate` |
| Provider | openai / elevenlabs / dashscope / doubao / google / kling（复用现有 BaseTool） |
| Skill | `openmontage-providers-tts` |
| 门禁 | `confirm_estimate` / `confirm` + `confirm_sample_ok`；`OPENMONTAGE_MAX_COST_USD`；`OPENMONTAGE_ALLOWED_PROVIDERS` |
| 文档 | Mcp_P2 归档 + 换机清单 §P2 TTS |

### 不做（本切片明确排除）

- providers-image / video / audio-music / stock  
- analysis / publish MCP  
- 新 pipeline Skill Pack  
- 静默 fallback 到其它付费商（失败只报错；可**明示**改用 Piper）

---

## 2. 协议（绑定）

```text
list_tts_providers
  → 只展示 available +（建议）key_configured
tts_dry_run(provider, text)
  → 向用户出示 estimated_cost_usd / model
用户批准估价
tts_sample(..., confirm_estimate=true)
用户试听通过
tts_generate(..., confirm=true, confirm_sample_ok=true)
decision_log: voice_selection
```

Key 仅来自环境变量，禁止写入 Skill。

---

## 3. 与 P1 关系

- Piper 仍走 `openmontage-media`（默认零 Key）  
- 付费 TTS 为**可选**；未装 MCP / 无 Key 时 router 不得宣称可用  
- explainer Skill 已注明可选路径  

---

## 4. 验收

- [ ] 无 Key 时 `list_tts_providers` 标明不可用，不伪造  
- [ ] 缺 `confirm_*` 时拒绝调用  
- [ ] 失败不自动换 provider  
- [ ] 沙箱路径仍在 `OPENMONTAGE_PROJECTS_DIR`  
- [ ] 单元测试不发起真实付费请求  
- [ ] 有 Key 的环境可人工跑通 sample（可选）

---

## 5. 后续 P2 插件（未排期）

image / video / analysis / 其它 pipeline — 另开计划，不在本切片。
