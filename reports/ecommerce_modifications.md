# 电商商品一致性 — 可修改范围说明书（修订版）

> 生成时间：2026-08-04（v2 修订）
> 目的：基于 v5 验证结果，重新评估可修改范围和实施优先级

---

## 重要修正声明

**原报告中的关键错误：**

1. ~~"Agnes I2I 天然保持一致性"~~ → 实际 v5 验证：3/5 候选因颜色/纹理漂移被拒
2. ~~"image_selector 路径为 tools/video/image_selector.py"~~ → 实际路径为 `tools/graphics/image_selector.py`
3. ~~"可立即批量生成"~~ → 实际需要先完成 manifest 和验收机制
4. ~~"旧 scene_plan.json 可直接使用"~~ → 实际 6×10s 策略已过时，需废弃

---

## 一、已有能力（可直接使用，不需要改）

| 能力 | 位置 | 说明 |
|------|------|------|
| Agnes 图片生成 | `tools/graphics/agnes_image.py` | I2I + T2I + Edit，已可用 |
| Agnes 视频生成 | `tools/video/agnes_video.py` | T2V + I2V，默认 4-5 秒短段 |
| 并行生成引擎 | `lib/parallel_generate.py` | 完整并发 + 重试 + 进度 |
| 提示词框架 | `lib/shot_prompt_builder.py` | 5 层 Cinematic 提示词框架 |
| 工具路由 | `tools/graphics/image_selector.py` | 自动优先 Agnes 图片生成 |
| 视频路由 | `tools/video/video_selector.py` | 自动路由到 Agnes 视频 |
| Web 看板 | `backlot/server.py` + `backlot/state.py` | SSE + 实时推送 |
| 视频拼接 | `lib/parallel_generate.py:assemble_ffmpeg()` | FFmpeg 拼接 |
| 一致性检测 | `lib/variation_checker.py` | 连续 3 段相同镜头标记 |
| 商品一致性规则 | `docs/商品一致性视频生成通用规则.md` | 完整提示词模板和验收标准 |
| 并发控制 | `lib/parallel_generate.py:resolve_agnes_concurrency()` | 根据 tier 设置并发 |
| Remotion 电商组件 | `remotion-composer/src/components/ProductReveal.tsx` | 产品展示组件 |
| v5 已验收候选 | `assets/video/candidate_*_pale_v3_4s.mp4` | 2 个已通过验收的 Agnes 片段 |
| v5 已验收参考图 | `assets/images/i2i_samples_20260804/*.png` | 6 张浅青玉参考图 |

---

## 二、需要新增的能力（按优先级）

### 模块1：商品身份 Manifest（P0 — 必须）

**目的**：记录商品身份锚点和参考图验收状态

**新增文件**：`lib/product_identity.py`

```python
# 核心结构
ProductManifest = {
    "product_id": str,              # 商品唯一 ID（如 "tianshancui-bangle"）
    "product_name": str,            # 商品名称（用于 prompt 注入）
    "identity_anchor": {            # 商品身份锚点
        "primary_color": str,       # 主色（如 "pale icy-green"）
        "forbidden_changes": list,  # 禁止变化项
        "geometry_constraints": list # 几何约束
    },
    "reference_images": [           # 用户上传的原始参考图
        {"path": str, "angle": str, "status": "approved|rejected"}
    ],
    "i2i_candidates": [             # I2I 生成的候选图
        {"path": str, "angle": str, "status": "pending|approved|rejected|satisfied"}
    ],
    "i2v_candidates": [             # I2V 生成的候选视频
        {"path": str, "scene_id": str, "status": "pending|approved|rejected|satisfied"}
    ],
    "scene_plan_refs": {            # 场景 → 已验收参考图映射
        "scene01": "i2i_candidates/02.png",
        "scene02": "i2i_candidates/angle_controlled_three_quarter.png"
    }
}
```

**工作量**：~80 行，纯新增

---

### 模块2：商品提示词自动注入（P0 — 必须）

**修改文件**：`lib/shot_prompt_builder.py`

```python
# 需新增函数
def build_product_prompt(
    scene: dict,
    product_manifest: dict,
    angle: str,
) -> dict[str, str]:
    """基于商品 manifest 构建场景提示词"""
    # 1. 从 manifest.identity_anchor 提取颜色/几何约束
    # 2. 从 docs/商品一致性视频生成通用规则.md 的模板获取几何锚点
    # 3. 组合 prompt（参考图角度 + 商品特征 + 镜头描述）
    # 4. 注入 forbidden_changes 到负向提示词
```

**工作量**：~50 行，修改现有文件

---

### 模块3：候选验收状态机（P1 — 建议）

**新增文件**：`lib/candidate_review.py`

```python
# 需实现的核心函数
def review_candidate(
    candidate_path: str,
    reference_images: list[str],
    reviewer_decision: str  # "rejected" | "approved" | "satisfied"
) -> dict:
    """记录候选验收结果"""
    ...

def get_pending_candidates(product_manifest: dict) -> list[str]:
    """获取待验收候选列表"""
    ...

def apply_fallback(plan: dict, product_manifest: dict) -> dict:
    """当 AI 候选被拒时，应用确定性回退"""
    ...
```

**工作量**：~60 行，纯新增

---

### 模块4：电商 Pipeline 定义（P1 — 建议）

**新增文件**：`skills/ecommerce-product-video.md`

定义完整的电商视频生产流程：
- 输入：商品图 + 文案
- 阶段1：商品身份 manifest 创建
- 阶段2：I2I 候选生成 + 人工验收
- 阶段3：I2V 候选生成 + 人工验收
- 阶段4：Remotion 时间线组装（AI 插入 + 确定性回退）
- 阶段5：最终成片输出

**工作量**：~30 行，纯新增文档

---

### 模块5：Backlot 候选验收 UI（P2 — 可选）

**修改文件**：`backlot/state.py` + `backlot/ui/board.js`

在现有看板中增加：
- 候选图/视频预览
- 验收按钮（通过/拒绝/满意）
- 确定性回退状态显示

**工作量**：~40 行

---

## 三、修改优先级汇总

| 优先级 | 模块 | 文件 | 工作量 | 必要性 |
|--------|------|------|--------|--------|
| **P0** | 商品身份 Manifest | `lib/product_identity.py`（新增） | ~80 行 | 必须 |
| **P0** | 商品提示词注入 | `lib/shot_prompt_builder.py`（修改） | ~50 行 | 必须 |
| **P1** | 候选验收状态机 | `lib/candidate_review.py`（新增） | ~60 行 | 建议 |
| **P1** | 电商 Pipeline 定义 | `skills/ecommerce-product-video.md`（新增） | ~30 行 | 建议 |
| **P2** | Backlot 候选验收 UI | `backlot/state.py` + `board.js`（修改） | ~40 行 | 可选 |

---

## 四、不可跳过的关键决策

### 决策1：旧 scene_plan.json 必须废弃

当前 `projects/tianshancui-bangle-60s/artifacts/scene_plan.json` 是 6×10s 策略，基于错误的假设（Agnes 能长时间保持一致）。

**新策略**：
- 15 个 beat，每 beat 4 秒，共 60 秒
- 仅 2-3 个 beat 使用 Agnes 短插入（已验收的 candidate_*_pale_v3_4s.mp4）
- 其余 12-13 个 beat 使用 Remotion 确定性静帧
- 通过 `AI_INSERTS_ENABLED` 开关控制是否使用 AI 片段

### 决策2：不能批量生成

在 manifest 和验收机制完成前，不应批量生成。

**正确的顺序**：
1. 先完成 manifest 机制（模块1）
2. 再手动跑 1-2 个镜头验证（模块4 的 v5 策略）
3. 验证通过后，再考虑批量流程（模块5）

### 决策3：人工验收不可替代

自动一致性评分（CLIP embedding 等）只能作为辅助，不能替代人工验收。

**原因**：电商商品对颜色、几何、材质的敏感度极高，"整体相似"不代表商品身份没有变化。

---

## 五、MVP 路径（最快验证）

如果想**本周内**验证新策略效果，可以只做最小改动：

1. 手动创建 `products/tianshancui-bangle/identity_anchor.json`
2. 基于 v5 已验收的 2 个 candidate 视频，手动编辑 scene_plan_v6.json
3. 用现有 Remotion 框架跑通 60 秒时间线
4. 验证 Agnes 插入 + 确定性回退的效果

**不需要修改任何代码**，只需手动创建配置文件。

---

## 六、与 v5 实验的关系

v5 已经验证了新策略的可行性：
- ✅ 2/5 候选通过验收（浅青玉色保持稳定）
- ✅ 3/5 候选被拒（颜色/纹理漂移）
- ✅ Remotion 确定性时间线可行（15 beats × 4s）
- ✅ AI_INSERTS_ENABLED 开关可行

**下一步不是重新验证，而是把 v5 的手动流程自动化。**
