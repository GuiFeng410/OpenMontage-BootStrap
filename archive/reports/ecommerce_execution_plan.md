# 电商商品一致性视频生成 — 执行计划

> 生成时间：2026-08-04
> 基于：v5 实验验证结论 + 代码审查结果

---

## 总览

| 项目 | 内容 |
|------|------|
| **商品** | 天山翠玉镯（浅青玉色，闭合圆环） |
| **目标** | 60 秒电商宣传片，保持商品身份一致性 |
| **策略** | 少量 Agnes 插入（2-3 个镜头）+ Remotion 确定性主控 |
| **总工期** | 5 阶段，预计 5-8 天 |
| **当前阶段** | 第 0 阶段：手动验证（本周可完成） |

---

## 第 0 阶段：手动验证（本周，0 代码修改）

**目标**：用现有工具验证 v5 策略的完整流程

### 步骤

1. **创建商品身份锚点文件**
   ```bash
   # 新建项目目录
   mkdir -p projects/tianshancui-bangle-v6/products/tianshancui-bangle
   ```
   创建 `products/tianshancui-bangle/identity_anchor.json`：
   ```json
   {
     "product_id": "tianshancui-bangle",
     "product_name": "天山翠玉镯",
     "primary_color": "pale icy-green with subtle yellow undertones",
     "forbidden_changes": [
       "color cannot become deep emerald green",
       "texture cannot become black star-shaped",
       "roundness must remain closed and complete",
       "thickness must remain consistent throughout"
     ],
     "geometry_constraints": [
       "closed ring (no gaps)",
       "consistent inner/outer diameter ratio",
       "smooth surface texture",
       "translucent jade material"
     ]
   }
   ```

2. **基于 v5 已验收候选创建新 scene_plan**
   - 使用 `assets/video/candidate_angle_pale_v3_4s.mp4` 和 `candidate_diagonal_pale_v3_4s.mp4` 作为 AI 插入
   - 其余 beat 使用 Remotion 确定性静帧
   - 创建 `artifacts/scene_plan_v6.json`

3. **手动组装 Remotion 时间线**
   - 用现有 `scripts/run_rematon.py` 跑通
   - 验证 2 个 Agnes 插入 + 13 个确定性静帧的效果

4. **人工验收**
   - 检查颜色是否一致（浅青玉色，非深翠绿色）
   - 检查几何是否稳定（闭合圆环，无形变）
   - 检查纹理是否漂移（无黑色星状纹理）

**交付物**：
- `projects/tianshancui-bangle-v6/products/tianshancui-bangle/identity_anchor.json`
- `projects/tianshancui-bangle-v6/artifacts/scene_plan_v6.json`
- `renders/previews/bangle_v6_preview.mp4`

**不做的事**：不写任何代码，纯配置文件 + 手动跑现有工具

---

## 第 1 阶段：商品身份 Manifest（预计 1 天）

### 任务

1. **新建 `lib/product_identity.py`**
   - 定义 `ProductManifest` 数据结构
   - 实现 `load_manifest()`, `save_manifest()`, `validate_anchor()`
   - 实现 `get_approved_i2i_images()`, `get_approved_i2v_candidates()`

2. **修改 `lib/parallel_generate.py`**
   - `build_scene_plan()` 增加 `product_id` 参数
   - `generate_one_scene_with_retries()` 支持从 manifest 读取参考图

3. **编写测试**
   - `tests/lib/test_product_identity.py`

### 验证标准

- [ ] manifest 能正确加载和保存
- [ ] `identity_anchor` 约束能被正确验证
- [ ] `get_approved_i2i_images()` 只返回状态为 approved/satisfied 的图

---

## 第 2 阶段：商品提示词自动注入（预计 1 天）

### 任务

1. **修改 `lib/shot_prompt_builder.py`**
   - 新增 `build_product_prompt(scene, product_manifest, angle)` 函数
   - 从 manifest 提取颜色/几何约束注入 prompt
   - 将 `forbidden_changes` 注入负向提示词

2. **集成到并行生成**
   - 修改 `lib/parallel_generate.py:make_agnes_generate_fn()`
   - 当 `product_id` 存在时，自动调用 `build_product_prompt()`

3. **编写测试**
   - `tests/lib/test_product_prompt_builder.py`

### 验证标准

- [ ] 生成的 prompt 包含商品颜色描述（"pale icy-green"）
- [ ] 生成的 prompt 包含禁止变化项（负向提示词）
- [ ] 无 product_id 时不影响现有流程

---

## 第 3 阶段：候选验收状态机（预计 1-2 天）

### 任务

1. **新建 `lib/candidate_review.py`**
   - `review_candidate(candidate_path, reference_images, decision)`
   - `get_pending_candidates(product_manifest)`
   - `apply_fallback(plan, product_manifest)`

2. **修改 `backlot/state.py`**
   - 在 scene 状态中增加 `review_status` 字段
   - 显示候选验收状态

3. **创建验收 UI（可选，P2）**
   - `backlot/ui/review.js` — 候选预览 + 验收按钮

### 验证标准

- [ ] 候选验收结果能正确写入 manifest
- [ ] 被拒候选自动触发确定性回退
- [ ] Backlot 显示正确的验收状态

---

## 第 4 阶段：单镜头小样本验证（预计 0.5 天）

### 任务

1. 选择 1 个新镜头（如"正面特写"）
2. 用新 manifest 机制生成 2-3 个 I2V 候选
3. 人工验收并记录结果
4. 对比新旧策略的效果差异

### 验证标准

- [ ] 新 prompt 注入机制有效（颜色描述准确）
- [ ] 候选验收流程可重复执行
- [ ] 确定性回退在候选被拒时正确触发

---

## 第 5 阶段：批量流程封装（预计 1-2 天）

### 任务

1. **新建 `skills/ecommerce-product-video.md`**
   - 定义完整电商视频 pipeline
   - 集成前 4 阶段的所有模块

2. **修改 `scripts/run_parallel_video.py`**
   - 增加 `--product-id` 参数
   - 自动加载 manifest 和参考图

3. **最终集成测试**
   - 端到端跑通：商品图 → 提示词注入 → 候选生成 → 验收 → 成片

### 验证标准

- [ ] 完整 pipeline 可端到端执行
- [ ] 所有场景的 prompt 都包含商品身份约束
- [ ] 验收通过率 > 50%（基于 v5 的 40% 提升）

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Agnes I2V 颜色漂移仍发生 | 中 | 高 | 强制人工验收 + 确定性回退 |
| 提示词注入不够精准 | 中 | 中 | 基于 docs 模板逐步优化 |
| 验收流程过于繁琐 | 高 | 低 | 第 0 阶段手动验证后确认流程复杂度 |
| 批量生成成本超预期 | 低 | 中 | 单镜头验证通过后估算成本 |

---

## 关键决策记录

| 决策 | 内容 | 日期 |
|------|------|------|
| D1 | 废弃 6×10s 策略，采用 15×4s + 少量 Agnes 插入 | 2026-08-04 |
| D2 | Agnes 定位为"受控候选生成器"，非身份保证器 | 2026-08-04 |
| D3 | 人工验收不可替代，自动评分仅辅助 | 2026-08-04 |
| D4 | 第 0 阶段不写代码，纯配置文件验证 | 2026-08-04 |
| D5 | 先单镜头验证，再批量 | 2026-08-04 |

---

## 文件清单

### 新建文件

- `projects/tianshancui-bangle-v6/products/tianshancui-bangle/identity_anchor.json`
- `projects/tianshancui-bangle-v6/artifacts/scene_plan_v6.json`
- `lib/product_identity.py`
- `lib/candidate_review.py`
- `skills/ecommerce-product-video.md`
- `tests/lib/test_product_identity.py`
- `tests/lib/test_product_prompt_builder.py`

### 修改文件

- `lib/shot_prompt_builder.py` — 新增 `build_product_prompt()`
- `lib/parallel_generate.py` — 集成 manifest 和提示词注入
- `backlot/state.py` — 增加验收状态显示

### 废弃文件

- `projects/tianshancui-bangle-60s/artifacts/scene_plan.json` — 被 scene_plan_v6.json 替代
