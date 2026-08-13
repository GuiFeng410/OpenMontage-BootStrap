# 商品片素材预处理闸（P0 · Beat 覆盖闭环）

**适用范围：** 商品宣传、电商展示、佩戴/使用演示；轻、中、重档均执行。它保留七阶段：表 2 后、表 3 前做覆盖预检；表 3 确认后在顶层 `assets_gate` 完成生成、审图与最终闭环。生成图确认是 **`assets_gate` 内部子闸，不是第八阶段**。

**硬原则：** 图片总数只是提示，`beat × 所需画面 × 候选图片` 覆盖矩阵才是门禁。**总张数够不等于逐段覆盖够，也不等于关键角度够。** 识图仅给建议，不能替代用户确认；禁止静默补图、静默复用、无商品主图硬烧或只写状态不落证据。

交叉引用：

- 分类标签与缺图话术：`product-prompt-template.md` §2.1–2.3
- 运镜/布光词库：`commercial-prompt-lexicon.md`
- 付费 AI 视频镜提示词：`openmontage/skills/openmontage-seedance-prompt/SKILL.md`
- Schema：`schemas/artifacts/asset_ledger.schema.json`、`decision_log.schema.json`

**冲突优先级：** `product-prompt-template.md` 中“默认图生图/按默认即 I2I”及“表 3 每段都必须已有 `ref_image`”的旧话术在本流程失效；缺口必须按本文件四选，I2I 永远不是默认项，且只有当前 image provider 可用时才可推荐。I2I 缺口按“先计划、后生成审图、最后回填真实引用”的顺序执行。

## 1. 两段式执行位置

```text
表 1/2 已锁（时长、档位、评审方式已知）
→ 扫描图片并形成 provisional unified matrix
→ 表 3 前先向用户输出「beat × 所需画面 × 候选图片」覆盖矩阵
→ 用户从四种缺口动作中逐项确认，表 3 写入对应素材计划
→ 用户确认表 3，brief_locked=completed
→ 进入七阶段第 2 阶段 assets_gate
→ 按计划补传/生成/复用/降级并审图
→ unified matrix 无开放状态且用户确认候选
→ assets_gate=completed
→ 才可交接 04
```

表 3 前只规划 I2I，不生成；生成和审图发生在 `assets_gate`。快速模式也不得合并或跨过这两个门。

## 2. 扫描与角色确认

1. 调 `produce_scan_user_images(project_id)` 扫描当前项目 `assets/images/` 的真实文件、尺寸、摘要和重复项。
2. 若已配置识图 Key，可调 `produce_describe_user_images(project_id)`；空 Key 时保留文件名启发式，不能把建议写成用户确认。
3. 将结果写入 `asset_precheck`；用户确认后，`user_class` 才可覆盖 `suggested_class`。
4. canonical Beat 只能来自已落盘的 `segment_cards` 与 `video_plan`；两者 Beat 集不一致时停止修正，不得猜。
5. `asset_ledger` 只用当前 schema 已允许的字段。每个 entry 只写 `beat` 或 `beats`，禁止两者同时出现。

辅助实现：`lib.asset_precheck.scan_user_images`、`build_asset_requirements`、`build_asset_ledger`、`validate_beat_assignment_matrix`。

## 3. 表 3 前必须输出 unified matrix

矩阵每行一个 canonical Beat，至少包含：

| Beat | 所需画面/关键角度 | 候选图片（精确项目相对路径） | 来源 | 当前状态 | 缺口动作/原因 |
|------|------------------|------------------------------|------|----------|---------------|
| B01 | 商品整体正面 | `assets/images/hero.png` | 用户上传 | `used` | 主图清晰，可专用于 B01 |
| B02 | 侧面结构 | `assets/images/hero.png` | 用户上传 | `reuse_pending` | 拟从 B01 跨 Beat 复用，尚未批准 |
| B03 | 扣合细节 | 无 | — | `missing` | 等待四选一 |

同时列出“上传图片归宿表”。**每张上传图必须且只能归入下列一类，并写中文原因：**

- `used`：`entries[].selected=true`，且只覆盖一个 Beat；用 `beats` 指向该 Beat，`note_zh` 写为何适配。
- `reuse_pending`：同一真实路径拟覆盖多个 Beat，但尚无精确复用批准；矩阵显示待确认，不得伪装为 `used`。账本可写 `beats` 和 `note_zh`，最终是否闭环由 scoped decision 判定。
- `unused`：`entries[].selected=false`，不写 `beat/beats`；`note_zh` 必须说明重复、角度不符、分辨率不足或与商品身份冲突等原因。

不在 canonical Beat 集中的分配是 `orphan`，必须修正；不能把它归成 `unused` 来掩盖错误。一个 Beat 同时有多个闭环路径也是冲突，必须确认唯一选用项。

## 4. 缺口处理严格四选

每个 `missing` Beat 只能选择一项：

1. **补传**：用户上传后重新扫描并更新矩阵。
2. **I2I**：仅在当前确有可用 `image_generation` provider/model 时可选。
3. **显式复用**：绑定精确路径和精确 Beat 集，等待用户原话批准。
4. **降级/不补**：明确降低镜头要求、改为概念表达或不使用该画面；记录风险和用户原话，并重写表 3 使该 Beat 不再声明缺失素材。

无当前可用 image provider 时，I2I 必须标为“不可执行”，**不得推荐**；只展示其余三项。`video provider` 不能替代 image provider，**禁止把 Pixverse 或任何仅 T2V/I2V 的 video provider 当生图工具**。

## 5. 显式复用硬协议

未获批准的跨 Beat 复用一律为 `reuse_pending`。批准必须通过 `produce_append_decision` 追加 schema-valid `asset_decision`，并同时满足：

- `decision_log.project_id` 等于当前 `project_id`；
- `stage="assets_gate"`；
- `subject` 与 `asset_path` 均为同一精确项目相对路径；
- `beat_ids` 与实际复用 Beat 集完全一致；
- 选中的 `options_considered[]` 项 `action="reuse"`；
- `user_approved=true` 且 `user_response_text` 是用户完整原话。

路径、Beat 集、项目或阶段任一变化，都要追加新 decision；不得修改旧记录或沿用旧项目授权。

## 6. I2I provider、候选与重试协议

### 6.1 生成前

1. 从 provider registry / 对应 image MCP 探测当前可用 `image_generation` 能力；明确 provider、model、费用与可用状态。
2. 用户确认 provider/model 后锁定到该 Beat 的 `planned_entries[]`。换 provider/model 必须暂停、重新确认并追加决定；重试不得静默换渠模。
3. `prompt_zh` 的输入**只能**是该 Beat 已确认的 `copy_plan_zh + shot_plan_zh + asset_plan_zh` 与 `source_paths` 中的 source image。不得用全片泛化 prompt，也不得脱离 source image 做 T2I 冒充 I2I。
4. 在真实调用前写 schema-valid planned entry；provider/model 缺失时不得进入 `generating`。

### 6.2 表 3 与 `ref_image` 写入顺序

缺图 Beat 在表 3 先写 `gap_fill="i2i"`、`assignment_status="i2i_planned"`、`planned_output_path`、`provider`、`model`。此时 `ref_image` 可省略；禁止把 source image、计划路径或尚未批准的候选路径冒充最终引用。

只有在真实候选落入当前项目 `assets/images/`、用户完成审图且 planned entry 已为 `status="approved"`、`review_status="approved"` 后，才把唯一批准的 `output_path` 同步写入该 Beat 的 `ref_image` 和 actual ledger。回填后将 `assignment_status` 改为闭环状态，并重算 unified matrix。

### 6.3 生命周期与证据

状态机固定为：`planned→generating→ready/review_pending→approved|rejected|failed`。

- `planned`：记录 `provider`、`model`、`source_paths`、`prompt_zh`、`planned_output_path`、`candidate_paths`、`retry_count`、`max_retries`；可记录计划 decision_id，但它不是审图批准证据，也不在未审状态强制解析为 approval decision。
- `generating`：保留前述字段，调用前递增或确认 `retry_count`；同一 Beat 的历史候选不得删除。
- `ready/review_pending`：候选必须真实落在当前项目 `assets/images/`；把全部候选写入 `candidate_paths`，把当前待审候选写入 `candidate_output_path`。文件不存在不得写 `ready`。
- `approved`：写 `review_status="approved"`、审图 `decision_id` 和唯一 `output_path`；`candidate_paths` 非空，批准输出必须属于 `candidate_paths`，所有候选路径均在当前项目内，且批准输出文件真实存在。审图 decision 同时固化工具计算的 `asset_sha256`，批准后同路径内容被替换必须重新审图。
- `rejected`：写 `review_status="rejected"` 并保留被拒候选路径与审图决定。若重生成，继续累计 `candidate_paths` / `retry_count`。
- `failed`：写 `error_zh`，保留 provider/model、重试次数和已有候选；不得只写一个 `failed` 状态。

候选、`retry_count`、`decision_id`、最终 `output_path` 与审图 decision 的 `asset_sha256` 是闭环证据；禁止只写状态。`planned_output_path` 只是计划，文件生成前禁止伪造 `output_path`。

## 7. 所有档位、评审方式都必须审图

生成图审查属于 assets_gate 内部子闸（不是第八阶段），适用于全部 `production_tier`、全部 `review_mode`：

- **普通模式**：可在一次卡片中批量展示全部候选，用户一次确认每个 Beat 的选中项/拒绝项；仍须保存用户原话和逐 Beat 结果。
- **专业模式**：逐张确认；用户可对单张拒绝并要求按同一已锁 provider/model 重生成，逐次累计候选与 `retry_count`。
- **快速模式**：不得绕过审图；最多沿用普通模式的一次批量确认形式。

**未经 approved 的生成图不能成为 `ref_image`、不能成为实际素材、不能进入 sample 或任何 video generation。** 用户只批准方案、档位、表 3、费用或“直接出片”，均不等于批准生成图。

## 8. `assets_gate=completed` 硬门禁

完成前必须重新运行/等价执行 unified matrix 校验，并同时满足：

- canonical Beat 集一致；每个仍要求素材的 Beat 恰有一个闭环素材；
- 无 `missing`、`orphan`、`reuse_pending`、`review_pending`、provider/model 缺失、候选未唯一选定或文件缺失；
- 所有上传图均为 `used` / 已批准复用 / `unused`，且有原因；
- 新写入用户素材为 `entries[].status="confirmed"` 且 `selected=true`；兼容旧账本显式 `origin/asset_source="user_upload"` 的 `ready` / `approved`，但只要同时出现 provider/model/candidate/output/review/decision/retry 等生成链字段，仍按生成图审查并拒绝来源伪装；
- 跨 Beat 复用存在本项目 scoped decision；
- 生成来源别名 `generated` / `t2i` / `text_to_image` / `i2i` / `image_to_image` / `ai_generated` 一律按生成图处理；**actual 生成链信号**包括 provider / model / candidate_paths / candidate_output_path / output_path / planned_output_path / review_status / decision_id / 任一 retry 字段及生成状态。actual image 只要出现任一信号就必须声明唯一生成来源并接受完整生成图审查；伪 `decision_id` 加省略来源不能降级成用户上传。无这些信号的普通用户上传继续兼容；
- planned 生成图还必须 `status="approved"`；`status="ready"` 只表示候选已落盘待审，不能代替批准；
- **planned image 来源声明：** 每个 `planned_entries[]` 的 image 都必须用 `origin` / `asset_source` / `gap_fill` 声明唯一且不冲突的来源。只要出现 planned_output / output / candidates / provider / model，或状态为 generating / ready / review_pending / approved / rejected / failed，就按完整生成链审查；不得靠省略来源把 approved planned 伪装成普通 ready 素材；
- 审图 `decision_id` 必须命中当前 `decision_log` 中唯一真实项：decision log 的 `project_id` 等于当前项目，且 decision 的 `stage="assets_gate"`、`category="asset_decision"`、`selected="approved"`、`user_approved=true`、`user_response_text` 非空；`asset_path` / `subject` 必须精确等于批准输出，`beat_ids` 必须与 entry 的 beats 精确一致，`asset_sha256` 必须等于当前文件内容。后续同一 asset_path + Beat 范围的撤回即使误改 subject 也按最新决定生效；伪 ID、重复冲突 ID、旧项目、旧 Beat 范围、路径漂移或同路径换图一律拒绝；
- planned 未 approved 时可保留计划 decision_id；只有 planned 标为 approved 才触发上述审图 decision 真实性校验；
- 同一条记录的 `origin` / `asset_source` / `gap_fill` 若声明为互不相容的来源，必须拒绝；生成来源别名之间先归一化后比较；
- `video_plan`、`segment_cards` 与 ledger 的 Beat、来源和最终路径无漂移；closed user/reuse/generated 状态下，已有 ref / ref_image 必须与 unified matrix 的同一 Beat + path 唯一批准路径一致，旧引用配新 ledger 必须拒绝。I2I 尚未审图时可省略引用；闭环后 Backlot/写入者只可用矩阵返回的唯一批准路径回填；
- 完成态必须复用 `lib.asset_precheck.scan_user_images` 的权威内容识别口径，递归扫描当前项目 `assets/images/`，并与 ledger 的 actual / planned / source / candidate / output 路径全集双向对账：任何未登记真实图片、以及账本引用但内容无法识别为有效图片的文件都拒绝，包含该扫描器支持的 BMP / TIFF / SVG。SVG 不能只凭扩展名认定：必须安全解析 XML、确认命名空间兼容的 **SVG 根元素**，尺寸优先取 width / height / viewBox，缺失时用安全占位但仍计入库存；普通伪 SVG 不计为图片。含 DOCTYPE、ENTITY 或**外部实体**声明的 SVG 禁止进入 XML 解析器和实体扩展，但不能从扫描消失：必须作为项目文件返回并标记 `unsafe_svg_declaration`。超过 `_MAX_SVG_BYTES` 的 `.svg` 必须先依据文件元数据判断，**不读取全文件**、不计算内容哈希，保留项目路径并标记 `svg_too_large`。这两类文件在 `assets_gate=completed` **无论是否入账**都硬拒绝。生成 source / candidate / output 路径计入账本，项目外路径和非图片文件不纳入追踪；
- Backlot 中**任何 planned image** 只有 unified matrix 真正批准同一 Beat + path 时才可显示 `preview_kind="approved"`；来源缺失、来源冲突或任一 matrix source issue 时只能显示候选/缺图，不能仅凭 `status` / `review_status` 标成批准；
- Backlot actual image 必须复用 validator 导出的 `has_generation_chain_signal` 生成链判定；只要命中信号但来源缺失或冲突，就不得显示 `user_asset`，只能显示候选、缺图或来源声明错误；
- `entries[].selected=false` 的实际素材必须用 `reason` 或非空 `note_zh` 解释为何 unused；`status="rejected"` 只表示状态，不能替代理由；
- 只要 canonical/inline decision log 存在，跨项目 decision_log 一律拒绝，其 `project_id` 必须等于 `project.json` 和项目目录身份；无复用、无生成图也不例外。确实不需要任何决定且 decision_log 文件不存在时保持兼容，不强制创建空文件。

只有全部满足，才写 `assets_gate=completed`。否则保持 `in_progress` / `awaiting_human` 并停在 03；不得交接 04。

## 9. Schema-valid 最小示例

以下示例以当前 schema 为准，不增添 schema 禁止字段。

#### Schema-valid 最小 planned entry

```json
{
  "version": "1.0",
  "project_id": "ring-launch-30s",
  "entries": [],
  "planned_entries": [
    {
      "beats": ["B03"],
      "kind": "image",
      "status": "planned",
      "review_status": "pending",
      "decision_id": "d-i2i-plan-001",
      "origin": "i2i",
      "gap_fill": "i2i",
      "source_paths": ["assets/images/hero.png"],
      "prompt_zh": "文案：展示扣合可靠；镜头：微距正侧光；素材：基于已确认主图补扣合细节角度。",
      "candidate_paths": [],
      "retry_count": 0,
      "max_retries": 2,
      "planned_output_path": "assets/images/i2i-B03-candidate-01.png",
      "provider": "configured-image-provider",
      "model": "locked-i2i-model",
      "label_zh": "B03 扣合细节候选",
      "note_zh": "仅为生成计划；真实文件落盘并审图前不可使用。"
    }
  ],
  "summary": {
    "available_image_count": 0,
    "counts_by_class": {},
    "missing_asset_classes": ["product_detail"],
    "status_zh": "等待用户选择",
    "quality_warning": "B03 尚无已批准细节图。"
  }
}
```

真实候选落盘后才增加 `candidate_output_path`；用户批准唯一候选后再写 `status="approved"`、`review_status="approved"` 与 `output_path`。

#### Schema-valid 复用 decision

```json
{
  "version": "1.0",
  "project_id": "ring-launch-30s",
  "decisions": [
    {
      "decision_id": "d-reuse-001",
      "stage": "assets_gate",
      "category": "asset_decision",
      "subject": "assets/images/hero.png",
      "options_considered": [
        {
          "option_id": "reuse",
          "label": "将主图复用于 B01 与 B04",
          "score": 1.0,
          "reason": "同一商品主图可承担开场与收束。",
          "action": "reuse"
        },
        {
          "option_id": "do_not_reuse",
          "label": "不复用并补传",
          "score": 0.5,
          "reason": "画面变化更丰富，但需要新增素材。",
          "rejected_because": "用户明确批准精确复用。",
          "action": "do_not_reuse"
        }
      ],
      "selected": "reuse",
      "reason": "用户确认精确路径和 Beat 范围。",
      "asset_path": "assets/images/hero.png",
      "beat_ids": ["B01", "B04"],
      "user_visible": true,
      "user_approved": true,
      "user_response_text": "同意 hero.png 只在 B01 和 B04 复用。",
      "decided_at": "2026-08-12T12:00:00+00:00"
    }
  ]
}
```

#### Schema-valid 审图 decision

```json
{
  "version": "1.0",
  "project_id": "ring-launch-30s",
  "decisions": [
    {
      "decision_id": "d-i2i-review-001",
      "stage": "assets_gate",
      "category": "asset_decision",
      "subject": "assets/images/i2i-B03-candidate-01.png",
      "options_considered": [
        {
          "option_id": "approved",
          "label": "批准候选 01",
          "score": 1.0,
          "reason": "商品身份、扣合结构和角度符合 B03。"
        },
        {
          "option_id": "rejected",
          "label": "拒绝并重生成",
          "score": 0.3,
          "reason": "可在结构不一致时重新生成。",
          "rejected_because": "用户确认候选 01 可用。"
        }
      ],
      "selected": "approved",
      "reason": "用户批准该真实候选用于 B03。",
      "asset_path": "assets/images/i2i-B03-candidate-01.png",
      "asset_source": "i2i",
      "asset_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "beat_ids": ["B03"],
      "user_visible": true,
      "user_approved": true,
      "user_response_text": "批准 B03 候选 01。",
      "decided_at": "2026-08-12T12:05:00+00:00"
    }
  ]
}
```

## 10. Backlot

落盘 `artifacts/asset_precheck.json`、`asset_ledger.json`、`video_plan.json`、`segment_cards.json`、`decision_log.json`（或 checkpoint 内联）；有识图时可另存 `asset_vision.json`。Backlot 只读展示矩阵与候选，用户仍在聊天批准。
