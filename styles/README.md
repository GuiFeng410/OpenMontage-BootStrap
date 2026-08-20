# 风格 YAML 已迁到 `product/styles/`

`playbook_loader.py` 留在本目录，供 `from styles.playbook_loader` 使用。YAML 由 `ResourceLocator.styles()` 解析（优先 `product/styles`）。
