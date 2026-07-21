# 错误处理

| 文档 | 内容 |
|------|------|
| [01-错误集合.md](./01-错误集合.md) | 已收集的典型错误与教训 |
| Skill | `openmontage-bootstrap-error-handling`（阶段 1：分类 + 计划） |

## 阶段 1 用法（给 Agent）

工具失败时：

```text
error_capture_context → error_classify → error_plan_recovery
```

- 已知四类：E01 静音 BGM / E02 字幕盘符 / E03 PowerShell / E04 混音 AAC  
- 安全步骤可按计划手动执行；**付费 / 覆盖原素材须确认**  
- `error_apply_recovery` 尚未开放（见阶段 2）  
- 状态：`<project>/artifacts/error_recovery.json`  

Playbook 数据：`openmontage/mcp/common/error_playbooks.yaml`
