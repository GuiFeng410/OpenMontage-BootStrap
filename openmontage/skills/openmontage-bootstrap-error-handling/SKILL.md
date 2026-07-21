---
name: openmontage-bootstrap-error-handling
description: >-
  BootStrap Error-Handling Skill: on tool failure, capture stderr, classify
  against known playbooks (E01–E04), return recovery plan. Phase 1 plan-only;
  auto-apply comes in phase 2. Max retries 3; paid/overwrite needs confirm.
metadata:
  openclaw:
    requires:
      bins:
        - python
      env:
        - OPENMONTAGE_PROJECTS_DIR
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
      - name: OPENMONTAGE_P1_ALLOW_WRITES
        required: true
    os:
      - win32
      - darwin
      - linux
    emoji: "🩹"
---

# OpenMontage BootStrap Error-Handling（阶段 1）

## Scope

**做：** 工具失败时捕获 stderr → 匹配已知 playbook → 给出修复计划与重试预算。  
**不做（阶段 1）：** `error_apply_recovery` 自动执行；付费 API 自动重试；静默覆盖素材。

来源：`README/错误处理/01-错误集合.md`  
Playbook 数据：`openmontage/mcp/common/error_playbooks.yaml`

## Required MCP

`openmontage-bootstrap`（`error_*` 工具）

## 何时调用（强制）

produce / captions-music / compose / mix / stock 等工具返回失败，或 stderr 含 FFmpeg/PowerShell 异常时：

1. **先读本 Skill**，再调用 `error_*`  
2. **不要**在未分类前盲目重跑付费 API  
3. **不要**编造与 playbook 无关的「万能修复」

## Hard protocol（阶段 1）

```text
工具失败（含 stderr / error 字段）
→ error_capture_context(project_id, tool_name, stage, stderr, stdout?, paths_json?)
→ error_classify(project_id, incident_id)          # 可选；capture 已初分
→ error_plan_recovery(project_id, incident_id)
→ 向用户展示：playbook_id、title_zh、actions、retries_left
→ 若 auto_allowed：按 planned_actions 中 auto=true 的步骤**手动**执行（阶段 1 无 apply 工具）
→ 若 needs_confirm / exhausted / E00_unknown：停下来等人审
→ 安全步骤做完后，重试原工具（同一 incident 逻辑重试 ≤ 3；阶段 2 会计数）
```

### 阶段 1 执行边界

| 情况 | Agent 行为 |
|------|------------|
| E02 / E03（低危、auto） | 可按计划改相对路径 / 改用 Python subprocess list，然后重试 |
| E01 / E04（中危） | 可先做检测、跳过 BGM、拆两步编码；**替换/覆盖文件须确认** |
| E00_unknown | 只展示 stderr，不自动修复 |
| 付费 / Stock 再下载 / 覆盖 `final.mp4` / 删除原 BGM | **必须弹窗确认** |
| `exhausted=true` | 停止自动修复，列出已尝试计划 |

### 已知 playbook

| ID | 含义 |
|----|------|
| E01_silent_bgm | BGM 无声 / AAC 极低码率 |
| E02_subtitle_drive_colon | Windows 字幕盘符冒号 |
| E03_powershell_arg_escaping | PowerShell 参数转义 |
| E04_amix_aac_bitrate_collapse | 混音一步 AAC 码率崩溃 |
| E00_unknown | 未匹配 |

## 工具一览

| 工具 | 作用 |
|------|------|
| `error_capture_context` | 写入 `artifacts/error_recovery.json`，返回 `incident_id` |
| `error_classify` | 匹配 playbook |
| `error_plan_recovery` | 返回计划（**不执行**） |
| `error_list_incidents` | 列出本项目 incidents |

状态文件：`<PROJECTS>/<project_id>/artifacts/error_recovery.json`

## 与其它 Skill

| Skill | 关系 |
|-------|------|
| produce | 失败时先交接本 Skill，再继续 compose |
| captions-music | mix / BGM 失败优先走 E01/E04 |
| providers-* | **不**自动修复；分类后交 Skill03 + 用户 |
| setup | ffmpeg 缺失等环境问题指向 setup，不计为本 Skill 自动重试 |

## 成功标准（阶段 1）

- 文档内四类 stderr 样例能命中正确 `playbook_id`  
- 计划含 `max_retries=3`、`auto_allowed`、`needs_confirm_for`  
- produce / captions Skill 写明失败时调用本 Skill  
- 无静默付费、无自动覆盖原素材  
