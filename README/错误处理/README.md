# 错误处理

| 文档 | 内容 |
|------|------|
| [01-错误集合.md](./01-错误集合.md) | 已收集的典型错误与教训 |
| [02-playbook说明.md](./02-playbook说明.md) | E01–E04 / E00 动作与 confirm 规则 |
| Skill | `openmontage-bootstrap-error-handling`（**阶段 3**：apply + 零 Key 合成 BGM） |

## 阶段 3 用法

```text
error_capture_context → error_plan_recovery → error_apply_recovery
→ 重试原工具
```

- 已知：E01 静音 BGM / E02 字幕盘符 / E03 PowerShell / E04 混音 AAC  
- 安全动作可自动 apply；**付费 / 覆盖原素材 / 覆盖 final.mp4 / 合成替换 BGM 须 confirm=true**  
- E01 换源：`action_ids="replace_bgm"` 或 `produce_synthesize_bgm(confirm=true)`  
- 同一 incident 最多 apply **3** 次  
- 辅助：`probe_audio_loudness`  
- 状态：`<project>/artifacts/error_recovery.json`  

Playbook：`openmontage/mcp/common/error_playbooks.yaml`
