# Remotion 图表深色主题可读性优化

> 关联样片：轻度 Remotion showcase 第二段 charts  
> 修复提交：`c212489`（Phase A）  
> 参照固化：Phase B（见文末索引）

---

## 1. 背景与样片路径

轻度 Remotion 能力展示项目用 `flat-motion-graphics` 深色主题，演示柱状图 / 折线图 / 扇形图 / KPI 等 cut。

| 项 | 路径 |
|----|------|
| 项目目录 | `projects/remotion-light-showcase/` |
| 第二段 props | `projects/remotion-light-showcase/segment-02-charts.json` |
| 第二段成片 | `projects/remotion-light-showcase/renders/segment-02-charts.mp4` |
| 渲染说明 | `projects/remotion-light-showcase/RENDER.md` |
| Agent 参照 | `openmontage/skills/openmontage-bootstrap-03-usercheck/references/light-remotion-showcase.md` |

主题为深色底；comparison、terminal 等镜头本身正常，问题集中在图表类 cut。

---

## 2. 问题现象

在 `segment-02`（`bar_chart` → `line_chart` → `pie_chart` → `kpi_grid`）中：

- **图形本身正确**：柱、线、扇区、KPI 卡片都能画出来
- **标注看不清**：轴标签、刻度、图例、数值等文字没有、太小，或颜色太灰，在深色底上几乎不可见
- **对照正常**：同片中的 `comparison` 双栏对照、`terminal_scene` 终端镜头可读性正常

易误判为「没开 `showValues` / `showLegend`」。实际这两个开关是开的；根因是颜色与透明度，不是开关。

折线图没有「点上数值标签」属于组件能力边界（当前无 `showPointLabels`），不是本次 bug。

---

## 3. 根因分析

### 3.1 主题色算了，但没传给图表

`Explainer.tsx` 的 `SceneRenderer` 已计算：

```ts
const textColor = cut.color || theme.textColor;
```

`comparison`、`text_card`、`callout` 等会把 `textColor` 传进子组件。  
**但** `bar_chart` / `line_chart` / `pie_chart` / `kpi_grid` 原先**未传** `textColor`（也未传 `gridColor` / KPI 的 `cardBackgroundColor`）。

关键路径：`remotion-composer/src/Explainer.tsx`（`SceneRenderer` 中图表分支）。

### 3.2 图表组件默认浅色主题色

未传 props 时，图表默认：

| prop | 默认值 | 在深色底上的效果 |
|------|--------|------------------|
| `textColor` | `#1F2937`（深灰） | 几乎看不见 |
| `gridColor`（柱/折） | `#E5E7EB` 等浅灰 | 网格/刻度对比弱 |
| `cardBackgroundColor`（KPI） | `#F9FAFB` | 与深色主题表面色不一致 |

关键路径：

- `remotion-composer/src/components/charts/BarChart.tsx`
- `remotion-composer/src/components/charts/LineChart.tsx`
- `remotion-composer/src/components/charts/PieChart.tsx`
- `remotion-composer/src/components/charts/KPIGrid.tsx`

### 3.3 部分元素透明度偏低

修复前典型值：

| 元素 | 约 opacity | 说明 |
|------|------------|------|
| 柱图网格/刻度 | ~0.6 | 再叠深灰字更难读 |
| 折图网格 | ~0.5 | 同上 |
| 饼图图例百分比 | ~0.6 | 图例数值发灰 |

`showValues` / `showLegend` 默认多为 `true`；问题不在开关，而在 **默认字色 + 透明度** 与深色主题不匹配。

### 3.4 为何 comparison / terminal 正常

这两类 cut 一直把主题推导出的 `textColor`（或等价颜色）传入子组件，因此在 `flat-motion-graphics` 下可读。图表分支漏传，形成「同主题、不同 cut 表现分裂」。

---

## 4. 修复方法（Phase A，已做）

提交：`c212489` — Remotion 图表深色主题修复，并固化轻度 Remotion 参照与 demo props。

### 4.1 Checklist

- [x] `Explainer.tsx`：图表传入 `textColor`、`gridColor={theme.mutedTextColor}`；KPI 加 `cardBackgroundColor={theme.surfaceColor}`
- [x] `TalkingHead.tsx`：overlay 图表同样传入 `textColor` / `gridColor` / KPI `cardBackgroundColor`
- [x] `BarChart`：网格透明度上限 `0.6` → `0.75`
- [x] `LineChart`：网格透明度上限 `0.5` → `0.65`
- [x] `PieChart`：图例百分比 opacity `0.6` → `0.75`
- [x] 重渲 `segment-02-charts.mp4` 验证可读性

### 4.2 代码改动要点

**Explainer（图表分支）** — 在已有 `backgroundColor={bgColor}` 旁补传主题色，例如：

```ts
// bar_chart / line_chart
textColor={textColor} gridColor={theme.mutedTextColor}

// pie_chart
textColor={textColor}

// kpi_grid
textColor={textColor} cardBackgroundColor={theme.surfaceColor}
```

其中 `textColor = cut.color || theme.textColor`，可用 cut 级 `color` 覆盖。

**TalkingHead** — overlay 侧对齐：默认浅色字 `#F8FAFC`、网格 `#94A3B8`，KPI 卡片表面色随深色底推导。

**图表组件** — 仅微调透明度；默认 `textColor = #1F2937` 仍保留（浅色主题兼容），深色场景依赖调用方显式传入。

---

## 5. 验证方式

不改 props 结构，只验证「传色 + 透明度」后第二段是否可读。

在 `remotion-composer/` 下（命令见 `RENDER.md`）：

```powershell
cd f:\small_work\vedio_github_project\OpenMontage\remotion-composer

npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-02-charts.mp4" `
  --props="..\projects\remotion-light-showcase\segment-02-charts.json"
```

目视检查：

1. 柱状图：轴标签、柱顶数值清晰  
2. 折线图：轴/图例可读（点上数值仍可能没有，见 §6）  
3. 扇形图：图例与百分比可读  
4. KPI：数值与卡片对比足够  

成片路径：`projects/remotion-light-showcase/renders/segment-02-charts.mp4`。

---

## 6. 仍可继续优化的点

| 项 | 说明 | 建议阶段 |
|----|------|----------|
| 轴/图例字号 | 当前约 18–22，可提到 24–28，大屏更易读 | 可选 UI 微调 |
| 折线点数值 | 增加 `showPointLabels`（或等价 prop），在 marker 旁标数值 | 组件能力扩展 |
| 简单/复杂表格 | 需新 `data_table` cut，非现有 chart 能覆盖 | 阶段 C |
| 默认色策略 | 长期可考虑：未传 `textColor` 时按 `backgroundColor` 亮度自动选浅/深字色，减少漏传 | 防御性增强 |

能力边界（非 bug）：`line_chart` 无点上数值标签；`comparison` 仅双栏。已写入 `light-remotion-showcase.md`。

---

## 7. 相关文件索引

| 角色 | 路径 |
|------|------|
| 场景编排（传色修复） | `remotion-composer/src/Explainer.tsx` |
| TalkingHead 覆盖层 | `remotion-composer/src/TalkingHead.tsx` |
| 柱 / 折 / 饼 / KPI | `remotion-composer/src/components/charts/{Bar,Line,Pie}Chart.tsx`、`KPIGrid.tsx` |
| 样片 props / 成片 | `projects/remotion-light-showcase/segment-02-charts.json`、`renders/segment-02-charts.mp4` |
| 渲染命令 | `projects/remotion-light-showcase/RENDER.md` |
| Phase B Agent 参照 | `openmontage/skills/openmontage-bootstrap-03-usercheck/references/light-remotion-showcase.md` |
| 表 2.1 Remotion 脚注 | `openmontage/skills/openmontage-bootstrap-03-usercheck/SKILL.md` |
| demo props 同步 | `remotion-composer/public/demo-props/light-showcase-*.json` |

### Phase B 固化（已做，供对照）

- 参照文档：`light-remotion-showcase.md`（60s 结构、11 种 cut、图表能力边界）
- 03 SKILL 表 2.1 脚注：选 Remotion 时指向上述参照与仓内样板 `projects/remotion-light-showcase/`
