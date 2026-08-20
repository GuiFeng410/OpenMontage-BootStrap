# 商品宣传片提示词词库（P1）

独立词库，供 `04-produce` 与商品模板写**付费 AI 镜头**英文/中文提示词时查阅。  
不替代 `product-prompt-template.md` 的槽位流程；写单镜前先完成素材闸与表 3。

来源整理自通用视频提示词规范与商业展示常见写法（内化摘录，非整仓 vendoring）。

## 1. 与模板的关系

| 文件 | 职责 |
|------|------|
| `product-prompt-template.md` | 分类、缺图、切段、中文槽位→英文组装顺序 |
| **本文** | 景别 / 运镜 / 布光 / 质感用语短表 |
| `asset-preprocess-gate.md` | 上传图预检，不写 prompt |

交叉引用：模板 §5–§6 组装英文单镜时，**应查阅本文**选用运镜与布光，避免堆砌无效形容词。

## 2. 景别（shot size）

| 用语 | 用途 |
|------|------|
| extreme close-up | 材质、切面、logo 微距 |
| close-up | 产品局部 |
| medium shot | 半身佩戴 / 手持 |
| wide shot / hero wide | 开场全貌、陈列 |

商品片默认：开场 medium/hero wide → 中段 close-up → 收尾 hero wide。

## 3. 运镜（camera move）— 身份优先

| 用语 | 何时用 | 忌用 |
|------|--------|------|
| locked-off / static | 身份敏感主镜头 | — |
| slow push-in | 强调质感 | 连续猜背面 |
| gentle parallax | Remotion/确定性 | 代替真实 360 |
| orbit / turntable | **仅**已确认多角度图之间 | 单图猜旋转 |
| whip pan | 转场花活 | 商品身份镜 |

原则：**固定机位或极慢微推优先**；未展示侧面不要让模型连续旋转臆造。

## 4. 布光（lighting）

| 用语 | 氛围 |
|------|------|
| softbox key, soft fill | 电商干净 |
| rim light / edge light | 分离主体 |
| specular highlight sweep | 玉石/金属高光 |
| overcast / diffused daylight | 自然佩戴 |
| warm practicals | 生活方式场景 |

保持与身份基准图色温一致；禁止「霓虹乱闪」除非用户点名。

## 5. 质感与约束短语（正面描述）

- seamless closed form, stable proportions, consistent material  
- keep product identity matching the reference image  
- clean seamless backdrop / marble surface / soft linen  
- commercial product photography, sharp focus on product  

避免负面堆砌（「no deformation」等）；用正面约束替代。

## 6. 单镜 7 要素清单（付费段）

写 I2V / T2V 前自检：

1. 商业/广告风格一句  
2. 景别  
3. 运镜（从表 3）  
4. 产品状态/动作（静止展示为主）  
5. 环境背景  
6. 布光  
7. 画质（sharp, commercial grade）+ **参考图一致性**  

总时长按 beat 控制（常见 ≤5s 试镜，正式动态段按锁定计划）。

## 7. 修订

| 日期 | 说明 |
|------|------|
| 2026-08-10 | P1 初版：独立 lexicon，与商品模板交叉引用 |
