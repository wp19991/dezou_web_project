# Poker Table

基于 `FastAPI + pokerkit + SQLite` 的网页德州扑克对局系统。

## 启动

```powershell
python -m uvicorn app.main:app --reload
```

默认会在项目根目录创建/使用 `poker_table.db`，并以 UTF-8 读取 `poker_table_sqlite_schema.sql` 初始化数据库。

当前随机种子按 Session 作用域生效：创建 Session 时可传 `seed`，每一手实际使用的 `hand seed` 由后端自动派生，并在 state / replay 中展示。

## 测试

```powershell
pytest
```

## 目录

- `app/`: 后端应用、规则内核、前端模板与静态资源
- `docs/`: 实施与验收文档
- `tests/`: 自动化测试
- `poker_table_openapi.yaml`: 接口契约
- `poker_table_sqlite_schema.sql`: SQLite 表结构
