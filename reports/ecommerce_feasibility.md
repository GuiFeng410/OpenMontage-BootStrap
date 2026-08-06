# 电商商品一致性视频生成 — 可行性分析报告（修订版）

> 生成时间：2026-08-04（v2 修订）
> 修订依据：v5 实验验证结果 + 实际代码审查

---

## 一、配置状态（已验证）

### Agnes 双引擎均已可用 ✅

| 工具 | 文件 | 模型 | 成本 | 质量分 | 状态 |
|------|------|------|------|--------|------|
| **AgnesImage** | `tools/graphics/agnes_image.py` | `agnes-image-2.1-flash` | $0.003/张 | 0.85 | ✅ **AVAILABLE** |
| **AgnesVideo** | `tools/video/agnes_video.py` | `agnes-video-v2.0` | $0.005/秒 | 0.80 | ✅ **AVAILABLE** |

### .env 配置确认

```
AGNES_API_KEY=cpk-hLRejMZznnh5VtjpIVKkmy7D9m4wAAiQNhjnPIPIVOAfKJzt  ✅
AGNES_ACCOUNT_TIER=tokenplan  ✅
AGNES_BASE=https://apihub.agnes-ai.com  ✅
```

### 额外发现

| 发现 | 说明 |
|------|------|
| **dashscope_image 也可用** | 阿里通义图片生成，免费，可作为补充 |
| **image_selector 已内置 Agnes 优先逻辑** | `tools/graphics/image_selector.py:324-330` — 自动检测 AGNES_API_KEY 并优先选择 agnes |
| **`ProductReveal.tsx` 已存在** | remotion-composer 中的电商产品展示组件 |

---

## 二、现有电商基础设施

### 文档基础（已完善）

| 文档 | 内容 |
|------|------|
| `docs/商品一致性视频生成通用规则.md` | 完整的产品一致性规范 — 镜头分级、提示词模板、参考图要求、验收标准、质量门禁 |
| `docs/商品宣传片前置审计规范.md` | 素材分类、身份确认、三级评判、状态规则 |

### 代码基础

| 模块 | 能力 | 状态 |
|------|------|------|
| `tools/graphics/agnes_image.py` | I2I + T2I + Edit，多图参考支持 | ✅ 已实现且可用 |
| `tools/video/agnes_video.py` | T2V + I2V，默认 5 秒短段 | ✅ 已实现且可用 |
| `lib/parallel_generate.py` | 完整并行生成引擎 + 重试 + 并发控制 | ✅ 已实现 |
| `lib/shot_prompt_builder.py` | 批量提示词构建（`build_batch_prompts`） | ✅ 已实现 |
| `lib/variation_checker.py` | 场景一致性检测（连续3段相同标记） | ✅ 已实现 |
| `tools/graphics/image_selector.py` | 自动优先 Agnes 图片生成 | ✅ 已实现 |
| `remotion-composer/.../ProductReveal.tsx` | 电商产品展示组件 | ✅ 已实现 |
| `backlot/server.py` | FastAPI + SSE 实时看板 | ✅ 已实现 |

### 已有实验资产（tianshancui-bangle-60s 项目）

| 资产 | 状态 | 说明 |
|------|------|------|
| `assets/images/i2i_samples_20260804/*.png` | ✅ 已生成 | 6 张浅青玉多角度 I2I 参考图（已人工验收） |
| `assets/video/candidate_angle_pale_v3_4s.mp4` | ✅ 验收通过 | 角度镜头，浅青玉色，闭合圆环，稳定厚度 |
| `assets/video/candidate_diagonal_pale_v3_4s.mp4` | ✅ 验收通过 | 对角线镜头，浅青玉色，稳定几何 |
| `assets/video/candidate_angle_02_v2_4s.mp4` | ❌ 已拒绝 | 颜色漂移（浅青→深翠） |
| `assets/video/candidate_diagonal_06_v2_4s.mp4` | ❌ 已拒绝 | 纹理重构（黑色星状） |
| `assets/video/candidate_light_04_v2_4s.mp4` | ❌ 已拒绝 | 颜色漂移（浅青→绿色） |
| `renders/previews/bangle_60s_agnes_insert_v5.mp4` | ✅ 候选预览 | 15 beats × 4s，2 个 Agnes 插入 + 13 个确定性静帧 |

---

## 三、v5 实验结论（关键修正）

### Agnes 不能作为商品身份保证器

v5 实验验证了 Agnes I2V 的实际一致性表现：

| 问题类型 | 出现情况 | 说明 |
|---------|---------|------|
| **颜色漂移** | 3/5 候选被拒 | 浅青玉变成深翠绿色，颜色在视频中逐帧变化 |
| **纹理重构** | 1/5 候选被拒 | 玉镯纹理被重新构造成黑色星状纹理 |
| **环境漂移** | 1/5 候选被拒 | 背景和光线发生明显变化 |
| **几何稳定** | 2/5 候选通过 | 当参考图为浅青玉色、颜色描述准确时，可保持稳定 |

**核心结论：Agnes 可以作为"受控候选片段生成器"，不能作为商品身份保证器。**

一致性保持的关键因素：
1. 参考图的颜色/材质必须准确描述
2. prompt 中需要明确禁止颜色漂移
3. 使用 I2I 生成的统一风格参考图比原始图更稳定
4. 短片段（3-4 秒）比长片段（10 秒）更容易保持几何稳定

---

## 四、技术路线修正

### 原计划（过于乐观）

```
商品参考图 → Agnes I2I → Agnes I2V（天然保持一致）→ 合并成片
```

### 修正后计划（基于 v5 验证）

```
用户上传商品图
       ↓
Agnes I2I 生成多角度候选图（人工验收：不合格/合格/满意）
       ↓
合格图 → Agnes I2V 生成短片段候选（人工验收：不合格/合格/满意）
       ↓
满意片段 → 插入 Remotion 确定性时间线（AI_INSERTS_ENABLED 开关控制）
       ↓
Remotion 主控转场、品牌文案、Logo、CTA
```

### 关键设计原则

1. **I2I 只生成候选图** — 每张候选图必须经过人工判断
2. **I2V 只使用短片段** — 建议 3-4 秒，不一次生成 10 秒长段
3. **Remotion 作为身份控制层** — 商品身份由确定性静帧保证，Agnes 只负责片段内部运动
4. **AI_INSERTS_ENABLED 开关** — 可随时回退到纯确定性版本

---

## 五、方案可行性评估

### 可行性判断

| 维度 | 评估 | 说明 |
|------|------|------|
| 技术路径 | ✅ 高 | I2I → I2V → Remotion 经 v5 验证可行 |
| Agnes 一致性 | ⚠️ 中等 | 需要人工验收环节，不能全自动保证 |
| 基础设施 | ✅ 高 | 核心工具均已实现且可用 |
| 批量可行性 | ⚠️ 中等 | 需新增商品身份 manifest + 验收状态机 |
| 成本可控 | ✅ 高 | 单片段候选约 $0.008（I2I $0.003 + I2V $0.005） |

---

## 六、建议实施路径（基于 v5 验证）

### 第一阶段：商品身份 manifest（预计 1 天）

1. 新建 `lib/product_identity.py` — 定义 manifest 结构
2. 定义商品身份锚点（颜色范围、几何约束、禁止变化项）
3. 建立参考图验收流程（不合格/合格/满意三级状态）

### 第二阶段：商品提示词自动注入（预计 1 天）

1. 在 `shot_prompt_builder.py` 中新增 `build_product_prompt()`
2. 从 manifest 提取商品特征注入 prompt
3. 集成到 `parallel_generate` 的生成流程

### 第三阶段：验收状态机（预计 1-2 天）

1. 新增候选状态追踪（`pending`/`rejected`/`approved`/`satisfied`）
2. 在 Backlot 中展示候选验收 UI
3. 确定性回退机制（AI 候选不通过时自动使用 Remotion 静帧）

### 第四阶段：单镜头验证（预计 0.5 天）

1. 选择 1 个新镜头做 2-3 个小样本验证
2. 验证新的 manifest 机制和提示词注入效果
3. 根据结果优化 prompt 模板

### 第五阶段：自动一致性评分（预计 2-3 天）

1. 实现候选自动筛选（CLIP embedding + 颜色直方图比对）
2. 辅助人工验收，减少重复劳动
3. **注意**：自动评分不能替代人工验收，仅作为辅助

### 第六阶段：批量流程封装（预计 1-2 天）

1. 整合为完整 ecommerce pipeline
2. Backlot 实时进度展示
3. 批量生成 + 自动验收 + 确定性回退

---

## 七、成本估算

### 单镜头候选成本

| 步骤 | 数量 | 单价 | 成本 |
|------|------|------|------|
| I2I 候选图（3 角度） | 3 张 | $0.003 | $0.009 |
| I2V 候选视频（1-2 段） | 2 段×4秒 | $0.005/秒 | $0.04 |
| 人工验收 | — | — | $0 |
| **单镜头候选总计** | | | **~$0.05** |

### 完整 60 秒视频成本（保守估计）

假设 60 秒需要 15 个 beat，其中 3 个 Agnes 插入，每个插入 3 次候选：

| 步骤 | 数量 | 成本 |
|------|------|------|
| I2I 参考图（15 张多角度） | 15 张 | $0.045 |
| I2V 候选（15 beat × 3 次 × 4 秒） | 180 秒 | $0.90 |
| Remotion 确定性部分 | — | $0 |
| **总计** | | **~$0.95** |

---

## 八、结论

| 维度 | 结论 |
|------|------|
| Agnes 图片/视频模型 | ✅ 已配置且可用 |
| 技术路线 | ✅ 可行（I2I → I2V → Remotion 经 v5 验证） |
| Agnes 一致性 | ⚠️ 不能保证，需要人工验收环节 |
| 旧 scene_plan.json | ❌ 需废弃（6×10s 策略已过时） |
| 新策略 | ✅ 少量 Agnes 插入 + Remotion 主控 |
| 建议下一步 | 第一阶段：实现商品身份 manifest |
| 预计补齐工作量 | 5-8 天（分 5 阶段） |
