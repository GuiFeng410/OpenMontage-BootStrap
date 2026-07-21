# 05 — 免费 Stock 素材接入（可选后补）

> **不在**默认安装的 4 个 MCP 里。零 Key 出片跑通后再按需加。

MCP：`openmontage-providers-stock`（`python -m openmontage.mcp.providers_stock`）  
Skill：`openmontage-providers-stock`  
模板：[templates/providers-stock.mcp.json](./templates/providers-stock.mcp.json)

## 步骤

1. 注册 MCP（command/cwd 与门面相同；env 含 `OPENMONTAGE_PROJECTS_DIR`）  
2. 填免费 Key（可只填一个）：
   - `PEXELS_API_KEY` → https://www.pexels.com/api/
   - `PIXABAY_API_KEY` → https://pixabay.com/api/docs/
3. 启用 Skill：`openmontage-providers-stock`  
4. 重启 MCP

## 用法协议

```text
list_stock_sources
→ stock_search(source, media_kind, query)   # 不落盘
→ 用户确认候选
→ stock_download(..., confirm=true)         # 写入沙箱
```

`source`：`pexels` | `pixabay`  
`media_kind`：`image` | `video`  
费用：$0（注意 API 限速）

## 与付费生成的区别

| | Stock | 付费 image/video |
|--|-------|------------------|
| 内容 | 现成素材搜索下载 | AI 生成 |
| 安装 | 可选后补 | 安装时已注册 server |
| Key | 免费申请 | 付费云厂商 |
