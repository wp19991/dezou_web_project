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
