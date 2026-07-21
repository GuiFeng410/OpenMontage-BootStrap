# 错误处理

| 文档 | 内容 |
|------|------|
| [01-错误集合.md](./01-错误集合.md) | 已收集的典型错误与教训 |
| Skill | `openmontage-bootstrap-error-handling`（**阶段 2**：classify + plan + apply） |

## 阶段 2 用法

```text
error_capture_context → error_plan_recovery → error_apply_recovery
→ 重试原工具
```

- 已知：E01 静音 BGM / E02 字幕盘符 / E03 PowerShell / E04 混音 AAC  
- 安全动作可自动 apply；**付费 / 覆盖原素材 / 覆盖 final.mp4 须 confirm=true**  
- 同一 incident 最多 apply **3** 次  
- 辅助：`probe_audio_loudness`  
- 状态：`<project>/artifacts/error_recovery.json`  

Playbook：`openmontage/mcp/common/error_playbooks.yaml`
