# Playbook 说明（阶段 3）

机器可读定义：`openmontage/mcp/common/error_playbooks.yaml`（`version: 3`）。

## 流程

```text
error_capture_context → error_classify / error_plan_recovery
→ error_apply_recovery（默认只跑 auto）
→ 高危：confirm=true + action_ids
→ 重试原工具
```

同一 `incident_id` 最多 apply **3** 次；超限报 `retries_exhausted`。

## Playbook 一览

| ID | 典型现象 | 自动动作 | 须 confirm |
|----|----------|----------|------------|
| E01_silent_bgm | `-91dB` / `input_i:-inf` / `2kbps` | loudness_check、mark invalid、skip BGM | `replace_bgm` / `synthesize_replacement_bgm`（零 Key 合成） |
| E02_subtitle_drive_colon | `original_size` + `subtitles=D:\` | 复制 SRT 到 `assets/subs/_work/` 相对路径 | — |
| E03_powershell_arg_escaping | `&&` / ParserError / force_style | 提示改用 `subprocess` list | — |
| E04_amix_aac_bitrate_collapse | amix + AAC 码率崩溃 | two_step_encode + verify_bitrate | — |
| E00_unknown | 未匹配 | 不自动修 | 任意 apply |

## E01 换 BGM（阶段 3）

用户确认后任选其一：

```text
error_apply_recovery(incident_id, confirm=true, action_ids="replace_bgm")
# 或
produce_synthesize_bgm(project_id, confirm=true)
```

- 写出 `assets/music/synth_ambient.wav`（多正弦 ambient，零 Key）
- 旧音乐移到 `assets/music/_invalid/`
- 登记 `music_bgm`，并尽量清除 skip-BGM hint
- 听过样片后再 compose / mix

## 辅助

- `probe_audio_loudness`：下载 Stock 后先验响度  
- 状态：`<project>/artifacts/error_recovery.json`  
- 详细教训原文：[01-错误集合.md](./01-错误集合.md)
