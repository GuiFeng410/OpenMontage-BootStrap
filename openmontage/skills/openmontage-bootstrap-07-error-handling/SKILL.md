---
name: openmontage-bootstrap-07-error-handling
description: >-
  BootStrap Error-Handling Skill: on tool failure, capture stderr, classify
  against E01–E04, plan and apply safe recoveries (max 3). High-risk
  overwrite/paid/synth-BGM actions require confirm=true. Phase 3 adds
  zero-key ambient BGM via replace_bgm / produce_synthesize_bgm.
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

# OpenMontage BootStrap Error-Handling（阶段 3）

## Scope

**做：** 捕获 stderr → 分类 playbook → 计划 → **自动执行安全修复**（≤3 次）→ 用户确认后零 Key 合成 BGM → 提示重试原工具。  
**不做：** 静默付费 API；静默覆盖 `final.mp4`；未知错误乱修。

来源：`README/错误处理/01-错误集合.md`  
说明：`README/错误处理/02-playbook说明.md`  
Playbook：`openmontage/mcp/common/error_playbooks.yaml`

## Required MCP

`openmontage-bootstrap`（`error_*` + `probe_audio_loudness` + `produce_synthesize_bgm`）

## Hard protocol

```text
工具失败
→ error_capture_context(...)
→ error_plan_recovery(...)
→ 若 auto_allowed 且 retries_left>0：
     error_apply_recovery(incident_id)          # 默认只跑 auto 动作
→ E01 换 BGM（用户确认后）：
     error_apply_recovery(..., confirm=true, action_ids="replace_bgm")
     # 或 produce_synthesize_bgm(project_id, confirm=true)
→ 用 results 中的 relative_path / hints 重试原 compose/mix
→ exhausted → 停，展示 attempts
```

| 情况 | 行为 |
|------|------|
| E02 / E03 | apply 可自动（相对路径字幕 / subprocess list） |
| E01 | loudness_check + mark invalid + skip BGM；**合成替换须 confirm** |
| E04 | two_step_encode + verify_bitrate（需 ffmpeg） |
| E00 / 付费 / 覆盖成片 | 须确认；默认不 apply |
| 第 4 次 apply | `retries_exhausted` 拒绝 |

## 工具

| 工具 | 作用 |
|------|------|
| `error_capture_context` | 记 incident |
| `error_classify` / `error_plan_recovery` | 分类与计划 |
| `error_apply_recovery` | 执行动作并 +1 retry |
| `error_list_incidents` | 列表 |
| `probe_audio_loudness` | volumedetect |
| `produce_synthesize_bgm` | 零 Key ambient WAV + 登记（confirm） |

状态：`<project>/artifacts/error_recovery.json`

## 与其它 Skill

produce / captions-music 失败时**先**本 Skill；providers-* 不自动修。
