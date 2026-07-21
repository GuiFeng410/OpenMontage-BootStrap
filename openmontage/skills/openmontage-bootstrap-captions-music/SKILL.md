---
name: openmontage-bootstrap-captions-music
description: >-
  BootStrap captions+BGM helper: copy→subs, import/register BGM, build compose
  input bundle, optional FFmpeg duck mix. Does not replace produce TTS or paid music.
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
    emoji: "📝"
---

# OpenMontage BootStrap Captions + Music（阶段 B+C）

## Scope

**做：** 文稿→字幕；BGM 导入/登记；打包 `edit_decisions` + `asset_manifest` 给 compose；可选 FFmpeg 旁白+BGM duck 混音。  

**不做：** 自定义字幕时间/位置；静默付费配乐；替代 Skill02 档位与旁白 TTS。

边界：`README/说明/03-字幕与配乐.md`

## Required MCP

`openmontage-bootstrap`

## 目录

```text
<project>/assets/copy|music|subs|audio/
<project>/artifacts/asset_manifest.json
```

## Hard protocol

### 文稿 → 字幕（B）

1. `produce_scan_copy_music`  
2. 无文稿 → 起草 → 人审 → `produce_write_copy(confirm=true)`  
3. 有文稿（沙箱内）→ `produce_import_copy(confirm=true)`  
4. `produce_segment_copy_to_subtitles(confirm_copy_ok=true)` → 展示 preview  

### BGM → compose 约定（C）

5. 无 BGM：可继续「仅字幕」；勿自动付费生成音乐。  
6. 有 BGM（沙箱内文件）→ `produce_import_music(..., confirm=true)`  
   或文件已在 `assets/music/` → `produce_register_music(confirm=true)`  
7. `produce_build_compose_inputs(project_id)` → 得到：  
   - `edit_decisions_json`（含 `audio.music` + `subtitles`）  
   - `asset_manifest_json`  
8. 交给 Skill02：`produce_compose_preflight` → `produce_compose_start`（合并进完整 timeline/edit 后调用）。  

### 可选混音（依赖 ffmpeg）

9. 已有旁白 `assets/audio/*` + 已登记 BGM 时，用户确认后：  
   `produce_mix_narration_and_music(confirm=true)` → `assets/audio/mixed.wav`（manifest id=`audio_mixed`）。  
10. 若 FFmpeg compose 需要单轨 `audio_path`，使用该 mixed 文件；Remotion 路径可继续用 manifest + edit_decisions。  
11. 无 ffmpeg / mix 失败：展示错误与依赖说明，仍可用「仅登记 BGM、不混音」路径。

### 工具失败（强制交接）

任一 `produce_*` / mix / compose 相关失败时：读 Skill `openmontage-bootstrap-error-handling`，  
`error_capture_context` → `error_plan_recovery`；E01/E04 常见。阶段 1 只给计划，不自动 apply。

## 工具一览

| 工具 | 阶段 |
|------|------|
| `produce_scan_copy_music` / `produce_ensure_captions_music_dirs` | B/C |
| `produce_write_copy` / `produce_import_copy` | B |
| `produce_segment_copy_to_subtitles` | B |
| `produce_import_music` / `produce_register_music` | C |
| `produce_build_compose_inputs` | C |
| `produce_mix_narration_and_music` | C 可选 |
| `produce_read_asset_manifest` | B/C |

## 成功标准（C）

- BGM 进入 `assets/music/` 且 manifest 有 `type=music`  
- `produce_build_compose_inputs` 产出可交给 compose 的 JSON  
- 文档写清：duck 混音依赖 ffmpeg；未混音时依赖 runtime 读 `edit_decisions.audio.music`  
- 无静默付费音乐调用  
