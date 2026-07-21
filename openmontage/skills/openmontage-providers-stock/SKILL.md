---
name: openmontage-providers-stock
description: >-
  Drive free Pexels/Pixabay stock search and download via openmontage-providers-stock
  MCP (list → search → download with confirm). Optional BootStrap add-on.
metadata:
  openclaw:
    requires:
      bins:
        - python
      env:
        - OPENMONTAGE_PROJECTS_DIR
    primaryEnv: OPENMONTAGE_PROJECTS_DIR
    envVars:
      - name: OPENMONTAGE_PROJECTS_DIR
        required: true
      - name: PEXELS_API_KEY
        required: false
        description: Free key from https://www.pexels.com/api/
      - name: PIXABAY_API_KEY
        required: false
        description: Free key from https://pixabay.com/api/docs/
      - name: OPENMONTAGE_ALLOWED_STOCK_SOURCES
        required: false
        description: Comma list e.g. pexels,pixabay
    os:
      - win32
      - darwin
      - linux
    emoji: "📷"
---

# OpenMontage Providers Stock（可选后补）

## Scope

**免费素材站**（非付费生成）：Pexels · Pixabay；图 + 视频。

**不在默认安装必配的 4 个 MCP 里。** 零 Key 出片跑通后，需要 B-roll/静帧时再注册。

## Required MCP

`openmontage-providers-stock` — `python -m openmontage.mcp.providers_stock`  
模板：`README/配置/templates/providers-stock.mcp.json`

## Hard protocol

1. `list_stock_sources` — 只推荐 key 已配置且 available 的源。  
2. `stock_search(source, media_kind, query)` — **只搜不落盘**，把候选展示给用户。  
3. 用户确认后 → `stock_download(..., confirm=true)`。  
4. 失败不静默换源；让用户改 query 或换 pexels/pixabay。  
5. Key 只来自环境变量。

`media_kind`：`image` 或 `video`。  
`source`：`pexels` 或 `pixabay`。

## Keys（免费注册）

| Key | 申请 |
|-----|------|
| `PEXELS_API_KEY` | https://www.pexels.com/api/ |
| `PIXABAY_API_KEY` | https://pixabay.com/api/docs/ |

费用恒为 $0（仍有 API 限速）。

## 与 produce 交接（中度档）

由 Skill02 `openmontage-bootstrap-produce` 在 **中度** 画面分支调用本 Skill。

1. `stock_search` → 用户确认候选。  
2. `stock_download(..., confirm=true, project_id=<项目ID>, scene_id=..., asset_id=...)`  
   - 文件落入项目沙箱  
   - **自动**写入/更新 `<project>/artifacts/asset_manifest.json`（schema 合法条目：`id/type/path/source_tool/scene_id` + stock 元数据）  
3. produce 侧：`produce_read_asset_manifest(project_id)` → 将 `asset_manifest_json` 传入 `produce_compose_*`。  
4. 本 Skill **不**调用 `produce_compose_*`。  
5. 轻度/重度默认不走本 Skill（重度用付费生图生视频；付费产物可用 `produce_append_asset_manifest_entry` 登记）。

## 与 BootStrap 关系

| 组件 | 关系 |
|------|------|
| 安装 Skill | **可选后补**，不默认注册 |
| Skill03 | 管付费 Key；stock 用本 Skill |
| produce | **中度**画面依赖本 MCP；轻度不依赖 |
