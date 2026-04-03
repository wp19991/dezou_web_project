# Implementation Plan

## Summary

- 使用 `FastAPI + SQLAlchemy 2.x + SQLite + pokerkit + 模板前端` 实现单桌德州扑克系统。
- 正式接口仅提供 `/api/v1/*`。
- 活跃手牌状态保存在进程内，历史、事件、回放持久化到 SQLite。
- 过程中产生的说明文档统一落地到仓库文件。

## Key Changes

1. 建立后端骨架、数据库初始化、统一错误处理和文档。
2. 实现 `TableKernel`、session 串行锁、会话/手牌/动作/聊天/事件/回放服务。
3. 提供模板页、轮询同步、时间线、聊天、历史与回放查看。
4. 补充自动化测试与验收文档。

## Test Plan

- 单元测试覆盖庄位旋转、heads-up 顺序、动作合法性、手牌结束与回放生成。
- API 测试覆盖创建 session、开始 hand、提交动作、聊天、事件流、历史与 replay。

## Assumptions

- 仅支持 `No-Limit Texas Hold'em`。
- 不做运行中牌局的重启恢复。
- 所有读取与写入统一按 UTF-8 处理。

