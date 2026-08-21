# 电商商品一致性流程：第 1-2 阶段执行记录

> 更新时间：2026-08-04
> 项目：`tianshancui-bangle-v6`

## 本轮完成

### 第 1 阶段：商品身份 Manifest 接入

- 新增 `lib/product_identity.py`。
- 支持加载、保存和校验 `identity_anchor.json`。
- 只允许 `approved` / `satisfied` 素材进入后续流程。
- 会检查商品 ID、商品名称、主色、几何约束、禁止变化项和素材文件存在性。
- 真实 v6 Manifest 已加载通过：2 张批准 I2I 图片、2 段批准 I2V 视频。

### 第 2 阶段：商品提示词自动注入

- `lib/shot_prompt_builder.py` 新增 `build_product_prompt()`。
- 自动注入商品名称、浅青玉主色、几何约束、指定角度和“单一商品”要求。
- 新增 `build_product_negative_prompt()`，把颜色漂移、纹理重构、断环、厚度变化等禁止项传给生成器。
- `build_batch_prompts()` 增加可选 Manifest 参数；不传 Manifest 时保持旧流程。
- `lib/parallel_generate.py` 的 `build_scene_plan()` 支持 `product_id` 和 Manifest 路径元数据。
- `make_agnes_generate_fn()` 支持 Manifest 或 `product_id`，生成 Agnes 载荷时自动注入正/负向商品约束。
- 现有天山翠脚本已传入 `product_id`，后续生成不会绕过身份约束。

## 验证结果

- Python 编译检查：通过。
- 真实 Manifest 加载：通过。
- 关键路径标准库断言：通过。
- 定向 pytest：未执行，当前 Python 环境未安装 `pytest`；不是代码断言失败。
- 本轮没有调用 Agnes，没有产生新的云端费用。

## 下一阶段：第 3-4 阶段

1. 新增候选验收状态机：`pending -> rejected / approved / satisfied`，拒绝或待审候选必须回退 Remotion 确定性画面。
2. 选择一个尚未使用的新镜头，例如“正面特写”或“局部高光扫过”。
3. 在调用前明确记录：工具 `agnes_video`、provider `agnes`、模型 `agnes-video-v2.0`、I2V、4 秒、2-3 个候选、预计费用约 `$0.02-$0.06`（以实际返回为准）。
4. 用已批准 I2I 图片作为参考，逐个生成 2-3 个候选；不做批量 60 秒生成。
5. 逐个检查颜色、闭合圆环、厚度、纹理、商品数量、背景漂移和运动是否可接受，写入三档结论：不合格 / 合格可用 / 满意。
6. 只有“满意”的视频候选才允许进入正式时间线；其余使用 Remotion 回退，并保留人工验收记录。

## 当前决策

- Remotion 继续作为最终时间线和商品身份主控。
- Agnes 只作为短片段候选生成器。
- 暂不引入其它云端模型、ComfyUI 或批量 Agnes 生成。

## 第 3-4 阶段当前结果

- 新增 `lib/candidate_review.py` 和对应测试。
- 状态机支持 `pending / rejected / approved / satisfied`，拒绝或待审候选可切换到 Remotion 确定性回退。
- 已用 `agnes_video` / `agnes` / `agnes-video-v2.0` 生成 2 个 `beat_09` 的 4 秒 I2V 候选。
- 候选文件：
  - `projects/tianshancui-bangle-v6/assets/video/phase4_beat09_candidate_01.mp4`
  - `projects/tianshancui-bangle-v6/assets/video/phase4_beat09_candidate_02.mp4`
- 联系图：`projects/tianshancui-bangle-v6/renders/previews/phase4_beat09_contact.jpg`
- 两个候选生成后先登记为 `pending`；人工验收后分别更新为 `satisfied` 和 `rejected`，均尚未写入正式 60 秒时间线。

## 人工验收结果（2026-08-04）

- `phase4_beat09_candidate_01.mp4`：`satisfied`。
  - 用户判断：第一段较为满意，整体商品一致性可接受。
- `phase4_beat09_candidate_02.mp4`：`rejected`。
  - 用户判断：后半段出现明显断裂；补充帧最后 3 张可见手镯断裂痕迹。
- 候选 2 禁止进入正式时间线；候选 1 暂存为满意候选，等待阶段总结确认后再映射到 `beat_09`。

## 当前门槛

本轮在人工验收门槛等待用户确认期间，没有继续生成或批量调用 Agnes；用户确认后已执行 `beat_09` 接入、候选 2 回退和 v6 重渲染，详见下方结果。

## 已批准执行结果（2026-08-04）

- 候选 1 已接入 `beat_09`（00:32-00:36）。
- 候选 2 未复制到 Remotion 公共素材目录，保持拒绝状态并使用确定性回退。
- 已更新 `artifacts/scene_plan_v6.json`：12 个确定性 beat + 3 个 Agnes 插入。
- 新预览：`projects/tianshancui-bangle-v6/renders/previews/bangle_v6_preview_beat09_satisfied.mp4`
- 技术检查：H.264、1920x1080、30fps、1800 帧、60.053 秒、MP4 封装正常。
- `beat_09` 抽帧检查：候选 1 已生效，未出现候选 2 的断裂片段。
