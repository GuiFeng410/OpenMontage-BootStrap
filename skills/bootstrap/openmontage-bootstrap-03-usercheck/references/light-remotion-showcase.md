# 轻度 Remotion 能力展示 · Agent 参考

| 项 | 内容 |
|----|------|
| 版本 | **v0.1** |
| 状态 | 与 `projects/remotion-light-showcase/` 同步 |
| 受众 | 出片 Agent（表 3 规划、produce 写 props、渲染前自检） |
| 关联 | BootStrap `03-usercheck` 表 2.1 选 Remotion；`04-produce` 执行 |
| 不做 | 商品片提示词（见 `product-prompt-template.md`）；重度付费视频 |

---

## 1. 何时使用

满足**全部**条件时，以本参考为轻度 Remotion 片的规划与 props 模板：

| 字段 | 值 |
|------|-----|
| `production_tier` | `light` |
| `light_presentation` | `remotion` |

**特点**：零外部 API Key、纯 `Explainer` 组件编排、适合技术讲解 / 数据叙事 / 产品概念片。  
**仓内样板项目**：`projects/remotion-light-showcase/`（主题：向量搜索 vs 关键词搜索，60s，深色 `flat-motion-graphics`）。

---

## 2. 60 秒结构（三幕 + 完整时间轴）

样板总时长 **60s** · 1920×1080 · 30fps · `theme: flat-motion-graphics`。

### 2.1 三幕分段（可独立渲染预览）

| 段 | 时长 | Props 文件 | 镜头类型 |
|----|------|------------|----------|
| **intro / 对比** | ~17–18s | `segment-01-intro-comparison.json` | `hero_title` → `text_card` → `comparison` → `stat_card` |
| **charts / 图表** | ~23–24s | `segment-02-charts.json` | `bar_chart` → `line_chart` → `pie_chart` → `kpi_grid` |
| **terminal-close / 收束** | ~20–21s | `segment-03-terminal-close.json` | `terminal_scene` → `callout` → `progress_bar` → `text_card` → `hero_title` |

分段 JSON 时间轴从 `0` 起算，便于单段迭代；完整片使用 `explainer-props-60s.json`（全局 `in_seconds` / `out_seconds`）。

### 2.2 完整 60s 时间轴（节选）

| 时间段 | 镜头 ID | `cut.type` | 要点 |
|--------|---------|------------|------|
| 0:00–0:04 | hook | `hero_title` | 主标题 |
| 0:04–0:08 | intro | `text_card` | 一句话引入 |
| 0:08–0:14 | compare | `comparison` | 双栏对比 |
| 0:14–0:18 | recall-stat | `stat_card` | 大数字 |
| 0:18–0:24 | recall-bars | `bar_chart` | 柱状图 |
| 0:24–0:30 | latency-line | `line_chart` | 折线图 |
| 0:30–0:35 | query-pie | `pie_chart` | 环形图 |
| 0:35–0:41 | metrics-kpi | `kpi_grid` | KPI 三列 |
| 0:41–0:47 | demo-terminal | `terminal_scene` | 终端演示 |
| 0:47–0:52 | hybrid-tip | `callout` | 提示卡 |
| 0:52–0:56 | adoption | `progress_bar` | 进度条 |
| 0:56–0:58 | takeaway | `text_card` | 收束语 |
| 0:58–1:00 | end | `hero_title` | 片尾 |

人读方案全文见项目内 `video_plan.md`。

---

## 3. Cut 类型清单（样板使用的 11 种）

`Explainer` 还支持 `anime_scene`、`screenshot_scene`、裸 `source` 视频/图片等；**本样板刻意覆盖以下 11 种 cut**，供轻度片选型：

| # | `cut.type` | 典型用途 | 样板中出现 |
|---|------------|----------|------------|
| 1 | `hero_title` | 开场 / 片尾大标题 | ✓ |
| 2 | `text_card` | 陈述句、过渡文案 | ✓ |
| 3 | `stat_card` | 单一大数字 | ✓ |
| 4 | `callout` | 提示 / 引用 / 警告框 | ✓ |
| 5 | `comparison` | 左右双栏对比（**仅 2 列**） | ✓ |
| 6 | `bar_chart` | 分类对比、排名 | ✓ |
| 7 | `line_chart` | 趋势、时序（**无数据点文字标签**） | ✓ |
| 8 | `pie_chart` | 占比、分布（支持 donut） | ✓ |
| 9 | `kpi_grid` | 2–4 列 KPI 仪表盘 | ✓ |
| 10 | `progress_bar` | 完成度、采用率 | ✓ |
| 11 | `terminal_scene` | 合成终端动画（无需真录屏） | ✓ |

**权威字段表**：`remotion-composer/SCENE_TYPES.md`（新增 type 须同步该文件）。

### 3.1 Overlays（叠加层）

| `overlay.type` | 用途 | 样板 |
|----------------|------|------|
| `section_title` | 章节小标题（角标位） | 核心差异 / 数据表现 / 生产指标 |
| `stat_reveal` | 角标大数字 | +47%、62% |
| `provider_chip` | 轮播技术栈徽章 | Remotion / Zero-Key / Explainer |

Overlays 与 cuts 共用全局时间轴；`in_seconds` / `out_seconds` 可落在 cut 中段。

---

## 4. Props JSON 路径

| 用途 | 路径（相对仓根） |
|------|------------------|
| 完整 60s | `projects/remotion-light-showcase/explainer-props-60s.json` |
| 分段 1 | `projects/remotion-light-showcase/segment-01-intro-comparison.json` |
| 分段 2 | `projects/remotion-light-showcase/segment-02-charts.json` |
| 分段 3 | `projects/remotion-light-showcase/segment-03-terminal-close.json` |
| Composer 演示副本 | `remotion-composer/public/demo-props/light-showcase-60s.json` |
| Composer 图表段副本 | `remotion-composer/public/demo-props/light-showcase-segment-02-charts.json` |

**约定**：场景属性写在 cut **顶层**（如 `cut.text`、`cut.chartData`），不要嵌套在 `props` 键下。  
新项目 props 建议落盘 `<project_id>/composition.json` 或 `public/demo-props/<name>.json`。

---

## 5. 渲染命令

工作目录：`remotion-composer/`。Composition 名：**`Explainer`**（非 `ExplainerVideo`）。

```powershell
cd f:\small_work\vedio_github_project\OpenMontage\remotion-composer

# 完整 60s
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\showcase-60s.mp4" `
  --props="..\projects\remotion-light-showcase\explainer-props-60s.json"

# 分段 2 — 图表（迭代最快）
npx remotion render src/index.tsx Explainer `
  "..\projects\remotion-light-showcase\renders\segment-02-charts.mp4" `
  --props="..\projects\remotion-light-showcase\segment-02-charts.json"
```

其余分段与输出路径见 `projects/remotion-light-showcase/RENDER.md`。  
渲染前建议跑 `composition_validator`（见 `skills/core/remotion.md`）。

---

## 6. 深色主题自检清单

样板使用 `theme: "flat-motion-graphics"`（`Root.tsx` 内 `textColor: #F8FAFC`，背景 `#0F172A`）。

| 检查项 | 说明 |
|--------|------|
| 图表轴/标题/数值可读 | **Phase A 已修**：`Explainer` 将 `theme.textColor`（或 `cut.color`）传入 `BarChart` / `LineChart` / `PieChart` / `KPIGrid` |
| 文案类 cut 对比度 | `text_card`、`comparison`、`callout` 等可显式设 `color: "#F8FAFC"` + `backgroundColor: "#0F172A"` |
| 图表 cut 的 `color` 覆盖 | 可选；未设时继承 `theme.textColor`。浅色主题视频勿忘设 `backgroundColor` |
| `chartColors` 与背景 | 深色底用高饱和色（如 `#22D3EE`、`#34D399`）；各 chart cut 可单独 `chartColors` 数组 |
| KPI `value` 格式 | 大数用 `value` + `suffix`（如 `8.1` + `" Billion"`），勿把原始巨大整数塞进 `value` |
| KPI `change` | 必须为**数字**（如 `34`），不要字符串 `"+34%"` |

---

## 7. 能力边界（规划时勿超范围）

| 能力 | 状态 | Agent 建议 |
|------|------|------------|
| `comparison` | ✅ 双栏 / 多栏（≤4） | 双栏或 `columns`；超过 4 栏改 `bar_chart` / `kpi_grid` |
| `data_table` | ✅ MVP | ≤5 列 × ≤5 行数据（+表头）；无合并；复杂表仍用 `screenshot_scene` |
| `line_chart` 数据点标签 | ✅ MVP | `showPointLabels`（默认关；仅第一条 series） |
| `terminal_scene` | ✅ | 适合 CLI/API 演示；步骤用 `steps[]`（`cmd` / `out` / `pill` / `pause`） |
| `screenshot_scene` | ✅ 组件已有 | 本样板未用；产品 UI _walkthrough 优先此 type |
| `anime_scene` | ✅ | 需图片资产；零密钥叙事优先本样板 11 类型组合 |
| 旁白 / BGM | 可选 | 样板 `audio: {}`；表 3 可先画面后配音（`05-captions-music`） |

---

## 8. 表 3 规划提示（轻度 Remotion）

1. **先定幕**：钩子（`hero_title`）→ 论证（图表/对比）→ 演示或收束（`terminal_scene` / `callout` / `hero_title`）。  
2. **每镜 4–6s**，全片 45–60s；图表动画至少留 4s。  
3. **每段 3–5 个 cut**，用 `section_title` 分组。  
4. 复制样板 JSON 改文案/数据，比从零拼字段更稳。  
5. 确认规划后写入 `video_plan` + 项目 `composition.json`，再交接 `04-produce`。

---

## 9. 相关链接

| 资源 | 路径 |
|------|------|
| 场景类型权威表 | `remotion-composer/SCENE_TYPES.md` |
| OpenMontage Remotion 技能 | `skills/core/remotion.md` |
| 样板渲染记录 | `projects/remotion-light-showcase/RENDER.md` |
| 样板视频方案 | `projects/remotion-light-showcase/video_plan.md` |
| 商品片（重度） | `references/product-prompt-template.md` |
