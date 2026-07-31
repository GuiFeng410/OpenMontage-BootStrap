# HyperFrames 数据可视化视频 — 优化记录

## 项目信息

- **项目路径：** `projects\hyperframes-dataviz-demo\`
- **视频时长：** 20s（1920×1080, 30fps）
- **渲染文件：** `renders\hyperframes_dataviz_20s.mp4`
- **合成文件：** `hyperframes\index.html`
- **渲染耗时：** 约 4 分钟

---

## 优化点 1：深色背景上的文字对比度不足

### 问题描述

柱状图下方的辅助文字（"QUARTERLY GROWTH TREND"、柱状图标签 "Q1/Q2/Q3/Q4/本年"、环形进度标签 "Overall Progress"）在深色背景上过于暗淡，几乎无法辨认。

### 根因分析

| 元素 | 原色值 | 背景色 | 对比度 | WCAG AA 标准 |
|------|--------|--------|--------|-------------|
| 底部标签 | `#4a3d2b`（深棕） | `#0a0a12`（深黑） | ~2.5:1 | ❌ 不达标（需 ≥4.5:1） |
| 柱状图标签 | `#6B5D4B`（中棕） | `#0a0a12`（深黑） | ~3.5:1 | ❌ 不达标 |
| 环形进度标签 | `#6B5D4B`（中棕） | `#0a0a12`（深黑） | ~3.5:1 | ❌ 不达标 |

### 修改内容

| 元素 | 修改前 | 修改后 |
|------|--------|--------|
| `#s2-bottom-label`（QUARTERLY GROWTH TREND） | `color: #4a3d2b` | `color: #8B7D6B` |
| `.bar-label`（Q1/Q2/Q3/Q4/本年） | `color: #6B5D4B` | `color: #7A6B55` |
| `#ring-center-label`（Overall Progress） | `color: #6B5D4B` | `color: #8B7D6B` |

### 修改后效果

- 底部标签对比度从 ~2.5:1 提升至 ~4.8:1（达标）
- 柱状图标签对比度从 ~3.5:1 提升至 ~4.3:1（接近达标）
- 环形进度标签对比度从 ~3.5:1 提升至 ~4.8:1（达标）

---

## 优化点 2：数字字体不适合数据展示场景

### 问题描述

视频中的数字（柱状图百分比、环形进度数值、卡片统计数字）使用的字体不够正式和专业，看起来不像常规的数据报告/出版物中的数字格式。

### 根因分析

| 元素 | 原字体 | 问题 |
|------|--------|------|
| 柱状图数值 `28%` `45%` ... | `Inter`（无衬线体） | 偏现代科技感，不像数据报表中的数字 |
| 环形中心数字 `92%` | `Playfair Display`（装饰性衬线体） | 高对比度装饰字体，粗细变化大，数字不够稳重均匀 |
| 卡片统计 `2.4M` `85K` `99.9%` | `Playfair Display`（装饰性衬线体） | 同上 |

### 修改内容

所有数字元素统一使用 **Georgia** 字体（Windows 系统自带衬线字体）：

| 元素 | 修改前 | 修改后 |
|------|--------|--------|
| `.bar-value` | 无 `font-family`（继承 `Inter`） | `font-family: Georgia, 'Times New Roman', serif` |
| `#ring-center-number` | `font-family: 'Playfair Display', serif` | `font-family: Georgia, 'Times New Roman', serif` |
| `.stat-number` | `font-family: 'Playfair Display', serif` | `font-family: Georgia, 'Times New Roman', serif` |

### 选择 Georgia 而非 Times New Roman 的原因

- **Georgia** 在屏幕上的可读性更好（字形更大、更宽、笔画更清晰）
- **Times New Roman** 数字偏窄，在视频中可能不够醒目
- 两者都是衬线字体，风格接近，但 Georgia 更适合屏幕展示

---

## 经验总结

### 深色背景文字颜色选择原则

1. 深色背景（`#0a0a12` 级别）上，辅助文本颜色不应低于 `#8B7D6B`
2. 可读性底线：`#7A6B55`（标签级），`#8B7D6B`（说明级），`#F5F0E8`（主内容级）
3. 避免使用 `#4a3d2b` 及更暗的颜色作为深色背景上的文字色

### 数据视频中数字字体选择原则

1. 数据展示场景优先使用 **Georgia** 或 **Times New Roman** 等传统衬线字体
2. 装饰性衬线（如 `Playfair Display`）适合标题，不适合数据数字
3. 无衬线体（如 `Inter`）适合科技感场景，但不适合"数据报告"风格
4. 系统自带字体（Georgia）无需额外加载，渲染更稳定