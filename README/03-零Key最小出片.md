# 03 — 出片（Skill02；默认先轻度）

使用 Skill：`openmontage-bootstrap-produce`  
前提：Skill01 `verify_ready` 已通过。

主题确认后 Agent 会请你选 **轻度 / 中度 / 重度**，完整说明见 [06-出片三档说明.md](./06-出片三档说明.md)。

## 轻度（零 Key，首推先跑通）

- Piper TTS（试听 → 批量）  
- 字幕、Remotion compose、probe  
- **不做**：Stock、付费 TTS/生图/生视频  

### 协议摘要

1. 主题确认 → **选轻度** → `produce_init_project`（`animated-explainer`）  
2. 人审关：`produce_approve_checkpoint` 必须带用户原话 `approval_text`  
3. TTS：`produce_tts_sample` → 试听 OK → `produce_tts_generate(..., confirm_sample_ok=true)`  
4. `produce_compose_start` → `produce_job_status`  
5. 成片：`<PROJECTS>/<project_id>/renders/final.mp4`  

### 试跑提示词示例

> 制作一个约 45 秒动画解说，解释天空为什么是蓝色的；选轻度（Piper）；每个关卡等我确认。

## 中度 / 重度（摘要）

| 档位 | 画面 | 语音 |
|------|------|------|
| 中度 | Stock（见 [05](./05-免费Stock素材接入.md)） | 默认 Piper；可手动付费 TTS |
| 重度 | 付费生图 + 生视频（见 [04](./04-收费Providers接入.md)） | 付费 TTS |

付费执行由 Skill03 + `openmontage-providers-*` 门禁完成；本 Skill **编排**但不静默调付费 API。

更细清单：[../docs/新机导入三步/03-第三步-最小视频出片验证.md](../docs/新机导入三步/03-第三步-最小视频出片验证.md)
