# 03 — 零 Key 最小出片（Skill02）

使用 Skill：`openmontage-bootstrap-produce`  
前提：Skill01 `verify_ready` 已通过。

## 范围（首版）

- Piper TTS（试听 → 批量）  
- 字幕、Remotion compose、probe  
- **不做**：diagram、stitch、付费 TTS 调用  

## 协议摘要

1. `produce_init_project`（pipeline 用 `animated-explainer`）  
2. 人审关：`produce_approve_checkpoint` 必须带上用户原话 `approval_text`  
3. TTS：`produce_tts_sample` → 用户听过 OK → `produce_tts_generate(..., confirm_sample_ok=true)`  
4. `produce_compose_start` → `produce_job_status`  
5. 成片：`<PROJECTS>/<project_id>/renders/final.mp4`  

## 试跑提示词示例

> 制作一个约 45 秒动画解说，解释天空为什么是蓝色的；零 Key（Piper）；每个关卡等我确认。

## 付费语音（可选说明，不执行）

若需要云端 TTS，需另行配置 `openmontage-providers-tts`，并遵守估价 → 试听 → 批量门禁。本 Skill 不代为调用付费 API。

更细清单：[../docs/新机导入三步/03-第三步-最小视频出片验证.md](../docs/新机导入三步/03-第三步-最小视频出片验证.md)
