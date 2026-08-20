# 已迁移（阶段 1 shim）

Python 内核在 `src/openmontage/lib/`。本目录只留加载器：把 `__path__` 指到真树，避免仓根同名目录挡住 `from lib.…`。
