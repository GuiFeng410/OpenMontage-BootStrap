---
name: openmontage-seedance-prompt
description: >-
  BootStrap 付费 AI 动态段提示词写法（仓内）。商品/电商片在 04-produce
  写 I2V/T2V（含 Seedance/即梦/Agnes 等渠道路由到的模型）英文或中文镜描述前
  必须先读本 Skill。不替代 03 表确认、预算卡、素材闸门。
metadata:
  openclaw:
    requires:
      bins:
        - python
    os:
      - win32
      - darwin
      - linux
    emoji: "✍️"
---

# OpenMontage Seedance Prompt（仓内）

## 何时必须读

在 `openmontage-bootstrap-04-produce` 中，凡对**付费 AI 动态段**起草、改写或重试**生成提示词**（I2V / T2V / 多模态参考），**先读本 Skill**，再读：

1. `openmontage-bootstrap-03-usercheck/references/commercial-prompt-lexicon.md`（景别/运镜/布光短表）
2. `openmontage-bootstrap-03-usercheck/references/product-prompt-template.md`（槽位顺序）
3. 本目录 `references/seedance-prompt-skill.md`（上游完整写法：结构、镜头语言、多模态引用、案例）

**可不读本 Skill：** Remotion / HyperFrames **纯本地运镜**、静帧、字幕叠层、无云端生成的段落。

## 契约覆盖（高于上游原文）

上游文档面向即梦/Seedance 单产品；在 BootStrap 中以下条款**优先**：

| 规则 | 说明 |
|------|------|
| 渠模锁定 | provider / model / 时长 / 分辨率以 `03-usercheck` 已锁定 `video_plan` / 简报为准，**禁止**因本 Skill 擅自改渠或改模 |
| 素材闸 | 商品片须已过 `asset-preprocess-gate`；提示词中的参考图须对应 `asset_ledger` / `ref_image`，禁止臆造未上传素材 |
| 预算与试片 | 遵守 `04-produce` 试片关与 `OPENMONTAGE_MAX_COST_USD`；本 Skill 只管「怎么写」，不管「何时烧」 |
| 用户确认 | 专业路径改提示词后仍走审查卡；勿把上游「可直接提交生成」理解为可跳过确认 |
| 语言 | 面向用户的说明用中文；提交给模型的镜描述按锁定模板（多为英文槽位或渠要求的中文），与 `product-prompt-template` 一致 |
| 非 Seedance 渠 | Agnes / Kling / 其它 I2V 仍用本 Skill 的**镜头结构与具体化写法**；平台特有 `@图片1`、即梦入口限制等仅在锁定渠为 Seedance/即梦时强制 |

## 最小产出结构（与上游对齐）

写镜时至少覆盖：

1. 主体与动作（可指 `@图片N` / 仓内资产 ID，若渠支持）
2. 场景与空间关系
3. 运镜与景别（对照 lexicon）
4. 光影与材质（商品纹理、金属/玉石反光等）
5. 节奏与时长（匹配该段秒数，勿超锁定 clip）
6. 风格锚点（简报已锁定的 visual_style）

禁止空泛词堆砌（「高级」「大气」「大片感」而无可见动作）；禁止与已锁定 `motion_mix` / beat 职责冲突的整段改写，除非用户在审查中明确要求。

## Related

- `openmontage-bootstrap-04-produce`
- `openmontage-bootstrap-03-usercheck/references/asset-preprocess-gate.md`
- `openmontage-providers-video`（实际调用；本 Skill 不发请求）
- 上游：https://github.com/songguoxs/seedance-prompt-skill（MIT）
