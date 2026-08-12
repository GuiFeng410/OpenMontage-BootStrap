# 04-剪辑标签与 Agent 驱动剪辑

> 适用：Backlot 看板 · 剪辑 POC（2026-08-12 完成并真实闭环验证）。  
> 配套代码：`backlot/ui/board-edit.js` · `lib/edit_intents.py` · `lib/edit_apply.py` · `POST /intents`。

## 这是什么

Backlot 项目页新增「✂ 剪辑」标签：用户对成片做**轻量标记**，Agent 读取标记、聊天确认后执行并重合成新版本。**Agent 主导剪辑，用户轻量参与**——不是剪映式手工编辑器。

## 用户怎么用（操作速查）

| 手势 | 作用 |
|------|------|
| 点击片段 | 播放器预览该片段（源文件缺失给提示，不阻塞） |
| 拖片段左右边缘 | 改该段时长（trim） |
| 拖片段左侧 ⠿ 手柄 | 调整顺序（reorder） |
| 点片段右上角 ✕ | 删除该段（delete） |
| 备注框 | 可填文字；**无改动时也可仅提交备注** |
| ↩ 撤销上一步 / ⟲ 重置为服务端版本 | 提交前补救：逐级回退 / 一键放弃所有未提交改动 |
| 提交剪辑要求 | 落盘 intent，等待 Agent 处理（提交后显示「已提交：…」回执） |

## Agent 闭环流程

```text
用户标记 → POST /intents → projects/<id>/intents/<intent_id>.json（status=pending）
→ Agent 读取（produce_list_intents）→ 聊天展示计划（plan_text）
→ 用户确认 → 应用（produce_apply_intent）：
   漂移检测（cuts 摘要不一致 → superseded + 提示重标）
   → 仅更新 edit_decisions.cuts（保留其他字段）
   → 缺失片段动作跳过 → status=applied
→ 按新 cuts 重合成新版本 → 回显
```

## 约定与边界

- **意图层与真相层分离**：`intents/` 是意图层（网页唯一写例外）；checkpoint / artifacts 是真相层，网页禁止写。
- **片段视频路径**：统一落 `projects/<id>/assets/video/`（命名如 `seg_<beat>.mp4`）；`edit_decisions.cuts.source` 用项目内相对路径。
- **cuts_revision**：cuts 内容摘要（djb2，与前端一致），用于版本漂移检测。
- **状态机**：`pending → planned → confirmed → applied`；异常分支 `rejected` / `superseded`。

## MCP 工具

`produce_list_intents(project_id)` 列 pending 请求；`produce_apply_intent(project_id, intent_id)` 应用（漂移检查 + 仅动 cuts）。

## 演示项目

`projects/edit-demo-jade`（翡翠手镯，真实 ffmpeg 片段）可体验完整闭环。
