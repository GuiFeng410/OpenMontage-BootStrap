# Backlot frontend（工厂源码）

React + Vite 源码。开发机 `npm install` / `npm run build` 写出 `../ui-dist/`。

用户运行时由 FastAPI 托管 `ui-dist`，不启 Vite，不带 `node_modules`。默认库页仍是 `backlot/ui/`（`/`）。`/next/` 是并行库页；`/next/p/<id>` 是并行商业看板（外壳、intent、播放器、剪辑）。默认路由 `/` 与 `/p/<id>` 仍走旧 `ui/`。
