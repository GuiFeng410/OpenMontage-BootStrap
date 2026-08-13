# 04-剪辑标签与 Agent 驱动剪辑

> 适用：`bootstrap-commercial` 七阶段 Backlot 看板。剪辑标签是初稿与交付前的修订入口，不是独立编辑器，也不新增第八阶段。

## 功能边界

用户在「✂ 剪辑」标签对 canonical 成片做轻量标记，Agent 读取要求、在聊天展示计划并取得确认，再修改 cuts 和重合成。既有七阶段、聊天审批、费用门禁与 provider/runtime 锁定均保持不变。

Backlot 仍以 checkpoint 和 `artifacts/*.json` 为真相层，只读展示这些证据。网页唯一写例外是把用户标记写入 `projects/<id>/intents/`；网页不能修改 checkpoint、canonical artifact 或生产决定。

## 素材门禁前置

剪辑修订不能补救未闭环的素材分配。商品片进入试片和后续视频阶段前，`assets_gate` 必须已经完成以下检查：

1. Beat 卡片只以 `segment_cards` / `video_plan` 的 canonical 分段为准；素材账本中的多 Beat 复用不会创建额外段卡。
2. 每个 Beat 都有明确的已批准素材或经确认的降级方案；缺图、孤立 Beat、未批准复用和多素材冲突都会阻止封板。
3. 生成图片必须记录 provider、model、候选、真实项目内输出与审图决定。所有档位都须用户确认；普通模式可批量确认，专业模式可逐张确认和重生成。
4. 未审生成图只作为候选预览，不能写成正式 `ref_image`，也不能进入试片或视频生成；快速模式同样不能绕过。
5. 每张上传图片都应归入已使用、复用待确认或未使用清单，并说明原因。

通过素材门禁后，剪辑闭环只处理已生成视频片段的 cuts 与重合成，不再静默更换图片、复用范围、provider 或模型。

## 开放条件

剪辑只在当前活动阶段为 `draft_review` 或 `delivery_signoff` 的修订环开放；`final_compose` 合成中锁定。以下条件必须全部满足：

1. `full_draft_pro` 存在、结构有效，且其媒体真实可读；
2. canonical latest render 有效：`draft_review` 读取 `full_draft_pro.path`，`delivery_signoff` 读取 `final_review.output_path`；
3. `edit_decisions.cuts` 非空；
4. 所有 `cuts[].source` 都指向当前项目 `assets/video/` 下真实、非空的视频；
5. 若 cuts 已应用并标记 `requires_compose=true`，当前 render artifact 已记录 matching `cuts_revision`。

缺任一条件时，播放器编辑、拖拽、删除、备注提交等操作整体锁定，`POST /intents` 也会返回 editing gate `409`。源文件缺失不是“不阻塞”；应先修复 canonical cuts 与媒体证据。

## 用户操作

| 操作 | 作用 |
|------|------|
| 点击片段 | 预览该 `cuts[].source` 片段 |
| 拖片段左右边缘 | 修改入点/出点（trim） |
| 拖片段左侧 ⠿ 手柄 | 调整顺序（reorder） |
| 点片段右上角 ✕ | 删除片段（delete） |
| 备注框 | 填写文字要求；无 cuts 动作时也可只提交备注 |
| ↩ 撤销 / ⟲ 重置 | 提交前逐步回退，或恢复服务端 cuts |
| 提交剪辑要求 | 只创建 intent，等待 Agent 在聊天复述和确认 |

## 固定闭环

```text
用户提交 → POST /intents（status=pending）
→ produce_list_intents
→ Agent 在聊天展示 plan
→ 用户明确确认
→ produce_apply_intent
   只改 edit_decisions.cuts
   写 requires_compose=true 与新 cuts_revision
→ produce_compose_preflight
→ produce_compose_start
→ produce_job_status（轮询 compose status）
→ 新媒体真实落盘
→ 在同一阶段更新 canonical artifact 的新路径、版本与 matching cuts_revision
   draft_review → full_draft_pro
   delivery_signoff → final_review
→ 重新读取 editing gate；enabled 后修订环才重新开放
```

`produce_apply_intent` 不生成媒体，也不自动得到新版本。apply 后只能说明“cuts 已应用，等待 Agent 重合成”；只有 compose 完成、媒体落盘且 canonical artifact 同步更新后，才能说“新版本已生成”。

## Intent 与漂移保护

每个新 intent 的 `base` 必须同时包含：

- `artifact="edit_decisions"`
- `source_render`：提交时的 canonical latest render
- `cuts_revision`：提交时 cuts 的内容摘要

apply 在项目锁内重新校验活动阶段、editing gate、canonical render、`source_render` 和 cuts digest。cuts 已漂移时 intent 进入 `superseded`，要求刷新后重标；阶段、render 或 gate 不匹配时拒绝应用。任何失败都不得部分修改 cuts。

校验通过后，更新后的 cuts、`requires_compose`、`cuts_revision` 与 intent 的 `applied` 状态作为跨文件事务提交；任一文件失败会回滚。

旧 intent 若缺 `source_render`，仍可在列表中查看审计内容，但不可应用，必须在当前 canonical 版本重新标记。

## 409 的两种含义

- editing gate `409`：响应包含 `kind="editing_gate"`、`reason_codes` 和中文原因，表示当前阶段或 canonical 证据不满足剪辑条件。
- 重复/冲突 `409`：同一 `intent_id` 已存在但内容不同，表示重复提交冲突。

两者不能都解释为“之前已经提交过”。前端应优先显示 editing gate 的具体原因。

## 阶段媒体证据

- 新写入的 `sample_reel` 必须带非空 `beat_ids`，只证明该试片覆盖的 Beat。
- `review_overview.overview[].output_path` 是对应 Beat 的分段 canonical 视频。
- `sample_reel.path`、Beat 分段路径、`full_draft_pro.path`、`final_review.output_path` 分别证明试片、分段、初稿、终稿，互不借用。
- 每次生成必须原子完成“媒体落盘 + 当前 canonical artifact 路径/版本更新”。孤立媒体文件不算阶段证据，不得据此宣称完成。

## 路径与状态

- `edit_decisions.cuts.source` 使用项目内相对路径 `assets/video/<file>`。
- `cuts_revision` 使用与前端一致的 cuts 内容摘要，用于版本漂移检测。
- Intent 状态主链为 `pending → planned → confirmed → applied`，异常终态为 `rejected` / `superseded`。
