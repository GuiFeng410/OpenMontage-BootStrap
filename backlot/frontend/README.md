# Backlot frontend（工厂源码）

React + Vite 源码。开发机 `npm install` / `npm run build` 写出 `../ui-dist/`。

用户运行时由 FastAPI 托管 `ui-dist`，不启 Vite，不带 `node_modules`。默认 `/` 与 `/p/<id>` 走这份产物。`/next/` 与 `/next/p/<id>` 是同一份 SPA 的书签别名。`ui-dist` 缺失时 `/` `/p/` 回退旧 `ui/`。`/ui/*.css` 仍给 SPA 用。
