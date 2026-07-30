# Remotion Light 能力展示 — 60 秒视频方案

**主题**：向量搜索 vs 关键词搜索（零密钥、纯 Remotion 组件）  
**主题风格**：`flat-motion-graphics`（深色科技风）  
**总时长**：60 秒 · 1920×1080 · 30fps

---

## 结构总览

| 时间段 | 镜头 ID | 类型 | 内容要点 |
|--------|---------|------|----------|
| 0:00–0:04 | hook | `hero_title` | 主标题「向量搜索 vs 关键词搜索」 |
| 0:04–0:08 | intro | `text_card` | 一句话引入：语义理解 vs 字面匹配 |
| 0:08–0:14 | compare | `comparison` | 双栏对比：匹配方式、召回特点 |
| 0:14–0:18 | recall-stat | `stat_card` | 大数字：语义召回 +47% |
| 0:18–0:24 | recall-bars | `bar_chart` | 柱状图：Top-10 召回率对比 |
| 0:24–0:30 | latency-line | `line_chart` | 折线图：语料规模 vs 延迟 |
| 0:30–0:35 | query-pie | `pie_chart` | 环形图：查询类型分布 |
| 0:35–0:41 | metrics-kpi | `kpi_grid` | 三列 KPI：QPS、成本、满意度 |
| 0:41–0:47 | demo-terminal | `terminal_scene` | 终端演示：embedding 查询命令 |
| 0:47–0:52 | hybrid-tip | `callout` | 提示卡：混合检索最佳实践 |
| 0:52–0:56 | adoption | `progress_bar` | 进度条：企业采用率 68% |
| 0:56–0:58 | takeaway | `text_card` | 收束语 |
| 0:58–1:00 | end | `hero_title` | 片尾「OpenMontage · Light Tier」 |

## 叠加层（overlays）

| 时间段 | 类型 | 内容 |
|--------|------|------|
| 0:08–0:11 | `section_title` | 章节「核心差异」 |
| 0:18–0:21 | `section_title` | 章节「数据表现」 |
| 0:14–0:17 | `stat_reveal` | 角标 +47% |
| 0:30–0:33 | `stat_reveal` | 角标 62% 语义查询 |
| 0:35–0:38 | `section_title` | 章节「生产指标」 |
| 0:41–0:47 | `provider_chip` | 轮播 Remotion / Zero-Key |

## 分段渲染计划

为加快预览，另提供 3 段独立 JSON（时间轴归零）：

1. **segment-01-intro-comparison.json**（~17s）— hero_title、text_card、comparison、stat_card
2. **segment-02-charts.json**（~23s）— bar_chart、line_chart、pie_chart、kpi_grid
3. **segment-03-terminal-close.json**（~20s）— terminal_scene、callout、progress_bar、text_card、hero_title

完整 60s 使用 `explainer-props-60s.json`。

**Agent 参考文档**：`openmontage/skills/openmontage-bootstrap-03-usercheck/references/light-remotion-showcase.md`（cut 清单、深色自检、能力边界、渲染命令）。Phase A 图表 `textColor` 修复见 `RENDER.md`。

## 渲染命令

```powershell
cd remotion-composer

# 完整 60s
npx remotion render src/index.tsx Explainer `
  "../projects/remotion-light-showcase/renders/showcase-60s.mp4" `
  --props="../projects/remotion-light-showcase/explainer-props-60s.json"

# 分段（示例）
npx remotion render src/index.tsx Explainer `
  "../projects/remotion-light-showcase/renders/segment-01-intro-comparison.mp4" `
  --props="../projects/remotion-light-showcase/segment-01-intro-comparison.json"
```
