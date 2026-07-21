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
模板：`README/templates/providers-stock.mcp.json`

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

1. 搜索确认后 `stock_download(..., confirm=true)`，产物落在 `OPENMONTAGE_PROJECTS_DIR` 沙箱内。  
2. 把每个镜头的本地路径回传 produce，写入 compose 用的 `asset_manifest_json`，建议条目至少含：

```json
{
  "id": "shot_01",
  "kind": "image|video",
  "path": "<absolute path under projects sandbox>",
  "source": "pexels|pixabay",
  "query": "<used query>"
}
```

3. 本 Skill **不**调用 `produce_compose_*`；合成仍由 produce / 门面完成。  
4. 轻度/重度默认不走本 Skill（重度用付费生图生视频）。

## 与 BootStrap 关系

| 组件 | 关系 |
|------|------|
| 安装 Skill | **可选后补**，不默认注册 |
| Skill03 | 管付费 Key；stock 用本 Skill |
| produce | **中度**画面依赖本 MCP；轻度不依赖 |
