# API Notes

## Response Shape

成功响应：

```json
{"ok": true, "data": {}}
```

失败响应：

```json
{
  "ok": false,
  "error": {
    "code": "ACTION_NOT_ALLOWED",
    "message": "当前动作不合法",
    "details": {}
  }
}
```

## Idempotency

- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{session_id}/hands`
- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/chat`

当请求带 `request_id` 时，会优先返回已存储结果，避免重复入账与重复事件。

## Runtime Limitation

运行中的 hand 状态保存在进程内。服务重启后，已结束 hand 的历史与回放仍可查询，但未结束 hand 不支持恢复。

## Random Seed

- `seed` 在 `POST /api/v1/sessions` 上配置，作用域是整个 Session。
- `POST /api/v1/sessions/{session_id}/hands` 不再要求 hand 级 seed。
- 每一手实际使用的 `hand seed` 由 `session_seed + hand_no - 1` 派生，并在 state / replay 中返回，便于回放与排查。

## Player View

- `GET /api/v1/sessions/{session_id}/state` 支持 `viewer_name` 查询参数。
- `GET /api/v1/sessions/{session_id}/state` 会直接返回当前这手的 `turn_order / action_history / chat_messages / timeline`。
- `GET /api/v1/replays/{hand_id}` 支持 `viewer_name` 查询参数。
- 当传入 `viewer_name` 时：
  - 自己的 hole cards 可见。
  - 其他玩家未公开的 hole cards 会被隐藏。
  - 已弃牌玩家的手牌不会暴露给其他玩家。
- 当 `GET /api/v1/replays/{hand_id}` 不传 `viewer_name` 时，回放按公开视角返回：只公开摊牌已亮出的牌。
- `POST /api/v1/sessions/{session_id}/actions` 可使用 `actor_name` 代替 `actor_id`。
- `POST /api/v1/sessions/{session_id}/chat` 可使用 `speaker_name` 代替 `speaker_id`。
- 当前仍然没有鉴权层；`viewer_name / actor_name / speaker_name` 属于信任式接入参数。
- 详细玩家轮询接入方式见 `docs/player-api.md`。
