# Architecture

## Runtime

- `PokerService` 负责业务编排。
- `TableKernel` 负责与 `pokerkit` 状态对象交互。
- `RuntimeRegistry` 维护 `session_id -> HandRuntime` 与 `asyncio.Lock`。
- SQLite 保存 session、seat、hand、event、replay 与幂等记录。

## State Machine

- `waiting_start`
- `running`
- `waiting_actor_action`
- `hand_ended`

`running` 仅在后端内部短暂存在，前端主要感知 `waiting_start`、`waiting_actor_action`、`hand_ended`。

## Seat Rotation

- 启动一手牌时，将 `dealer_seat` 旋转到内部最后一个 `player_index`。
- 向 `pokerkit` 统一传入 `{0: small_blind, 1: big_blind}`。
- 该映射同时满足 `2` 人和 `3+` 人局的盲注位与行动顺序。

