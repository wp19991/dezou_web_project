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

以下写接口支持 `request_id`：

- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{session_id}/hands`
- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/chat`

带 `request_id` 时，会优先返回已存储结果，避免重复入账与重复事件。

## Runtime Recovery

运行中的 hand 会保存在进程内，但服务也支持按持久化事件恢复未结束的对局：

- 服务重启后，已结束 hand 的历史与 replay 仍可查询
- 如果当前 session 有未结束 hand，重新读取 `/state` 或继续提交动作时会自动恢复运行时
- 内置网页可以直接载入已有牌桌并继续当前对局

## Random Seed

- `seed` 在 `POST /api/v1/sessions` 上配置，作用域是整个 session
- `POST /api/v1/sessions/{session_id}/hands` 不要求 hand 级 seed
- 每一手实际使用的 `hand seed` 由 `session_seed + hand_no - 1` 派生
- `state` 和 `replay` 都会返回该 hand seed

## Session Mode Metadata

`POST /api/v1/sessions` 支持：

- `user_participates: bool`

`GET /api/v1/sessions/{session_id}/state` 会返回：

- `user_participates`

这项字段只用于让内置网页在重新载入 session 时恢复正确模式：

- `true`：恢复为用户参与视图
- `false`：恢复为旁观视图

注意：

- 它不会改变后端的权限模型
- 后端不会因为它而自动限制动作、聊天或当前手时间线的返回
- 当前网页上的“只能一个用户、其它名字从 5 个候选里随机、人数上限 5/6”是前端约束，不是后端 API 约束

## Player View

- `GET /api/v1/sessions/{session_id}/state` 支持 `viewer_name`
- `GET /api/v1/replays/{hand_id}` 支持 `viewer_name`
- 传入 `viewer_name` 时：
  - 自己的 hole cards 可见
  - 其他玩家未公开的 hole cards 会被隐藏
  - 已弃牌玩家的手牌不会暴露给其他玩家
- `GET /api/v1/replays/{hand_id}` 不传 `viewer_name` 时，回放按公开视角返回，只公开摊牌已亮出的牌

## Name-Based Actions

- `POST /api/v1/sessions/{session_id}/actions` 可使用 `actor_name` 代替 `actor_id`
- `POST /api/v1/sessions/{session_id}/chat` 可使用 `speaker_name` 代替 `speaker_id`

当前仍然没有鉴权层；`viewer_name / actor_name / speaker_name` 属于信任式接入参数。
