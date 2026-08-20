# Backlot frontend（工厂源码）

React + Vite 源码。开发机 `npm install` / `npm run build` 写出 `../ui-dist/`。

用户运行时由 FastAPI 托管 `ui-dist`，不启 Vite，不带 `node_modules`。默认库页仍是 `backlot/ui/`（`/`）。`/next/p/<id>` 是商业看板外壳（只读），确认/剪辑/播放仍走默认站 `/p/<id>`。
