# 商品片素材预处理闸（P0 · 混合模式）

**适用范围：** 仅**商品宣传 / 电商商品展示 / 佩戴演示**片。普通讲解、轻度 Demo、非商品片不强制本闸。

**原则：** 程序清点硬事实 + Agent 建议分类 + **用户确认定稿**。P0 **不调用视觉 API** 做自动标类。禁止静默补图、禁止无主图硬烧。

交叉引用：

- 分类标签与缺图话术：`product-prompt-template.md` §2.1–2.3  
- 运镜 / 布光词库（写 prompt 用）：`commercial-prompt-lexicon.md`  
- 付费 AI 镜提示词（04 强制）：`openmontage/skills/openmontage-seedance-prompt/SKILL.md`

## 1. 何时触发

```text
用途 = 商品宣传或电商商品视频
且已完成表 1 / 表 2 关键锁定（时长已知）
→ 表 3 之前必须走本闸
```

## 2. 程序步骤（只读）

1. 调用 MCP `produce_scan_user_images(project_id)`  
2. 源目录：`projects/<id>/assets/images/`  
3. 得到 `asset_precheck`：路径、宽高、字节、sha256、重复、过小分辨率、`suggested_class`（仅文件名启发式）  
4. **不写盘**；由 Agent 把 `asset_precheck` 写入 checkpoint / artifacts  

Python 辅助（同仓库）：

- `lib.asset_precheck.scan_user_images`  
- `lib.asset_precheck.build_asset_requirements`  
- `lib.asset_precheck.build_asset_ledger`  

## 3. 用户确认卡

出示简表（各类张数、建议类、风险）：

| 文件 | 建议类 | 确认类 | 风险 |
|------|--------|--------|------|
| … | product_hero | （待填） | 过小/重复/未分类 |

缺则固定三选一（与模板 §2.3 一致）：

1. 我再上传素材  
2. 图生图补图（默认）  
3. 不补图 / 降级  

用户改标或确认后：

- `user_class` 覆盖 `suggested_class`  
- 写入 `asset_ledger` + `asset_requirements`  
- `decision_log` category：`asset_decision`  
- 才允许填表 3 / `video_plan` 的 `ref_image` / `gap_fill`

## 4. 状态（中文）

| 状态 | 含义 |
|------|------|
| 就绪 | 有主图且达最低数量与建议类型 |
| 降级继续 | 有主图但低于建议；须用户确认风险 |
| 等待用户选择 | 无主图或核心缺口未关闭 |

## 5. 与顶层 `assets_gate`

本闸 = 方案确认内的**预检**（表2后表3前）。  
顶层 `assets_gate` 只核验**已确认计划**所需实际文件与最终 `asset_ledger`，不重复分类。

## 6. Backlot

落盘 `artifacts/asset_precheck.json` / `asset_ledger.json`（或 checkpoint 内联）。  
若董事会话已读这些 artifact，顺带展示摘要；无则聊天给路径与简表即可。
