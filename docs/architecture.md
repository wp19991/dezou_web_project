# Architecture

## Runtime

- `PokerService` 负责 API 编排、幂等处理、当前手聚合与 replay 输出。
- `TableKernel` 负责和 `pokerkit` 状态对象交互，并把运行时状态转换成可持久化/可展示的数据。
- `RuntimeRegistry` 维护 `session_id -> HandRuntime` 和每个 session 的 `asyncio.Lock`。
- `Store` 负责 SQLite 读写。

## Persistence

SQLite 持久化这些对象：

- `sessions`
- `session_seats`
- `hands`
- `hand_seats`
- `events`
- `hand_replays`
- `idempotency_requests`

启动时会先执行 `poker_table_sqlite_schema.sql`，再执行兼容迁移。当前兼容迁移会自动补旧库缺失的：

- `sessions.rng_seed`
- `sessions.user_participates`

## Session Metadata

当前 session 除了传统牌局参数外，还额外保存一项前端模式元数据：

- `user_participates`

它的用途是让内置网页在重新载入已有 session 时，仍然知道应该恢复成：

- `用户参与` 视图
- `旁观模式` 视图

注意：

- 这是元数据，不会改变后端通用 API 的权限模型。
- 后端仍然没有鉴权层。
- `seat_count` 的 `5/6` 人限制和随机命名策略，属于内置网页逻辑；后端接口本身仍接受 `2..9` 人与任意唯一 `seat_names`。

## State Machine

对外可感知的主要阶段：

- `waiting_start`
- `waiting_actor_action`
- `hand_ended`

后端内部仍会短暂使用：

- `running`

其中：

- `waiting_start`：session 已创建但还没开始当前手
- `waiting_actor_action`：当前手进行中，等待某个玩家动作
- `hand_ended`：当前手结束，允许开始下一手

## Seed Strategy

- `POST /api/v1/sessions` 上的 `seed` 是 Session 级随机种子
- 每一手实际使用的 `hand seed` 由 `session_seed + hand_no - 1` 派生
- `state` 与 `replay` 都会回传当前手/该手的 seed，便于回放和排查

## Visibility Model

后端的可见性规则仍然是按 `viewer_name` 决定：

- 自己的 hole cards 可见
- 其他玩家未公开的 hole cards 不可见
- 公开 replay 只显示摊牌已亮出的牌

内置网页在此基础上再做一层展示策略：

- `用户参与` 模式：当前手时间线不显示，隐藏牌显示为 SVG 牌背
- `旁观模式`：动作/聊天区隐藏，当前手时间线可见

## Frontend Flow

首页是单页轮询界面，模板由 `index.html` 输出，主要逻辑在 `app/static/app.js`：

- 启动时从模板读取 `POKER_BOT_NAMES` 注入的 5 个候选名称
- 创建 session 时根据模式自动生成 `seat_names`
- 激活 session 后隐藏设置区，只保留“开始新一手”
- `用户参与` 模式轮询 `/state?viewer_name=...`
- `旁观模式` 优先轮询 `/events`，并在需要时刷新 `/state`

## Recovery

运行中的 hand 仍保存在进程内以支持实时操作，但如果服务重启：

- 已结束 hand 的历史与 replay 仍可直接查询
- 未结束 hand 会在下一次读取 `/state` 或继续提交动作时自动恢复运行时
