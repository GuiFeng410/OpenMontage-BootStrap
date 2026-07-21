# 07 — 字幕与配乐 Skill 边界大纲

> 状态：阶段 **B+C 已实现**；D（付费音乐）/ E（字幕时间位置）未做。  
> Skill：`openmontage-bootstrap-captions-music`

---

## 锁定决策

| # | 决策 |
|---|------|
| 1 | 无文稿：短脚本 → 人审 → 切分字幕 |
| 2 | 配乐默认零 Key；付费仅显式选择 |
| 3 | 两轨：字幕 + BGM；旁白走 produce TTS |
| 4 | 统一目录 `assets/copy|music|subs|audio` |
| 5 | 自定义字幕时间/位置：后置 |

---

## 已落地工具

| 工具 | 阶段 |
|------|------|
| `produce_scan_copy_music` / `ensure_*_dirs` / `write_copy` / `import_copy` / `segment_copy_to_subtitles` | B |
| `produce_import_music` / `produce_register_music` | C |
| `produce_build_compose_inputs` | C |
| `produce_mix_narration_and_music` | C 可选（需 ffmpeg） |

---

## Compose 输入约定（C）

1. 登记字幕 +（可选）BGM 到 `asset_manifest`。  
2. `produce_build_compose_inputs(project_id)` 返回：  
   - `edit_decisions_json`：`audio.music.asset_id` + `subtitles.source`  
   - `asset_manifest_json`  
3. Skill02 将其合并进完整 edit/timeline 后调用 `produce_compose_*`。  

### 混音依赖（写清）

| 路径 | 条件 | 说明 |
|------|------|------|
| 登记即可 | Remotion 等读 `edit_decisions.audio.music` | 不强制先 mix |
| `produce_mix_narration_and_music` | **ffmpeg 在 PATH** | duck 旁白+BGM → `assets/audio/mixed.wav` |
| 失败回退 | mix 报错 | 仍可 compose 仅字幕，或仅登记 BGM 不混音 |

门面不再把 `mix_audio` 列在 `not_in_v1`；通过 `produce_mix_narration_and_music` 包装 `audio_mixer` duck。

---

## 分期

| 阶段 | 状态 |
|------|------|
| A 大纲 | 完成 |
| B 文稿→字幕 | 完成 |
| C BGM + compose 约定 | **完成** |
| D 付费音乐 Skill03 | 待做 |
| E 字幕时间/位置 | 后置 |

索引：[00-INDEX.md](./00-INDEX.md)
