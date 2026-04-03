# Player API

面向“玩家客户端轮询接入”的完整说明。只看本文档，就可以把另一个客户端接到当前德州扑克服务。

本文档默认服务地址为 `http://localhost:8000`，所有请求和响应都使用 UTF-8 JSON。

## 1. 接入目标

一个玩家客户端至少要完成这些能力：

- 知道自己的玩家名 `viewer_name`
- 轮询当前牌局状态
- 看到当前这手的公共信息
- 看到自己的 hole cards
- 在轮到自己时提交合法动作
- 任意阶段发送聊天
- 查看历史手牌和单手回放

## 1.1 当前边界

当前实现是“按玩家名信任”的接口模型，还没有账号体系、签名校验或座位级鉴权。

这意味着：

- 只要知道 `viewer_name`，就能请求该玩家视角的状态
- 只要知道 `actor_name` / `speaker_name`，就能代表该玩家提交动作或聊天

所以它适合：

- 本地联调
- 内网联机
- 已经有上层网关或鉴权代理的环境

如果要直接暴露给不可信客户端，下一步必须补鉴权层。

## 2. 可见性规则

这是玩家客户端最重要的部分。

- 创建 Session 时，每个座位必须有唯一玩家名。
- 玩家客户端读取状态时，必须带 `viewer_name`。
- `viewer_name` 会决定哪些牌可见。

可见信息：

- 自己的玩家名、位置、筹码、hole cards
- 所有玩家的名字、位置、筹码、当前街投入、本手累计投入、弃牌/全下状态
- 当前公共牌
- 当前合法动作
- 当前这手已经发生的动作历史
- 当前这手的聊天记录
- 当前这手的事件时间线
- 历史手牌列表
- 历史回放中的公共事件、动作、聊天、赢家和结算结果

不可见信息：

- 其他玩家未公开的 hole cards
- 已弃牌玩家对其他人隐藏的 hole cards

特殊说明：

- `GET /api/v1/replays/{hand_id}` 在不传 `viewer_name` 时，会按“公开回放”处理：
  - 只有进入摊牌公开的牌可见
  - 非摊牌玩家的手牌不会公开
- 如果传了 `viewer_name`：
  - 自己的 hole cards 仍然可见
  - 其他未公开牌仍然不可见

## 3. 典型轮询流程

### 3.1 创建牌桌

请求：

```http
POST /api/v1/sessions
Content-Type: application/json
```

```json
{
  "session_id": "table-demo-01",
  "seat_count": 3,
  "small_blind": 50,
  "big_blind": 100,
  "starting_stack": 5000,
  "seed": 1234,
  "seat_names": ["Alice", "Bob", "Carol"]
}
```

成功响应：

```json
{
  "ok": true,
  "data": {
    "session_id": "table-demo-01",
    "phase": "waiting_start",
    "seat_count": 3,
    "small_blind": 50,
    "big_blind": 100,
    "starting_stack": 5000,
    "session_seed": 1234,
    "seats": [
      {"seat_id": "seat_0", "seat_no": 0, "display_name": "Alice", "stack": 5000},
      {"seat_id": "seat_1", "seat_no": 1, "display_name": "Bob", "stack": 5000},
      {"seat_id": "seat_2", "seat_no": 2, "display_name": "Carol", "stack": 5000}
    ],
    "created_at": "2026-04-04T10:00:00Z"
  }
}
```

接入要求：

- `seat_names` 长度必须等于 `seat_count`
- `seat_names` 必须唯一
- 之后玩家客户端用的是 `viewer_name`，不是固定 `seat_id`

### 3.2 开始新一手

请求：

```http
POST /api/v1/sessions/table-demo-01/hands
Content-Type: application/json
```

```json
{
  "dealer_seat": 0
}
```

说明：

- `seed` 是 Session 级的
- 每一手的真实 `hand seed` 由后端自动派生

### 3.3 玩家轮询当前状态

请求：

```http
GET /api/v1/sessions/table-demo-01/state?viewer_name=Alice
```

响应重点结构：

```json
{
  "ok": true,
  "data": {
    "session_id": "table-demo-01",
    "phase": "waiting_actor_action",
    "session_seed": 1234,
    "viewer": {
      "viewer_name": "Alice",
      "viewer_seat_id": "seat_0",
      "viewer_seat_no": 0,
      "is_actor": true,
      "can_act": true,
      "is_folded": false,
      "in_hand": true
    },
    "current_hand": {
      "hand_id": "table-demo-01-hand-1",
      "hand_no": 1,
      "seed": 1234,
      "street": "preflop",
      "dealer_seat": 0,
      "small_blind_seat": 1,
      "big_blind_seat": 2,
      "actor_id": "seat_0",
      "to_call": 100,
      "pot_total": 150,
      "board_cards": [],
      "turn_order": [
        {"seat_id": "seat_1", "display_name": "Bob", "seat_no": 1},
        {"seat_id": "seat_2", "display_name": "Carol", "seat_no": 2},
        {"seat_id": "seat_0", "display_name": "Alice", "seat_no": 0}
      ],
      "seats": [
        {
          "seat_id": "seat_0",
          "display_name": "Alice",
          "seat_no": 0,
          "stack": 5000,
          "contribution_street": 0,
          "contribution_total": 0,
          "is_folded": false,
          "hole_cards_visible": true,
          "hole_cards": ["As", "Kd"]
        },
        {
          "seat_id": "seat_1",
          "display_name": "Bob",
          "seat_no": 1,
          "stack": 4950,
          "contribution_street": 50,
          "contribution_total": 50,
          "is_folded": false,
          "hole_cards_visible": false,
          "hole_cards": []
        }
      ],
      "available_actions": [
        {"action": "fold", "enabled": true},
        {"action": "call", "enabled": true},
        {"action": "raise", "min": 200, "max": 5000, "default": 200, "enabled": true},
        {"action": "all_in", "enabled": true}
      ],
      "action_history": [],
      "chat_messages": [],
      "timeline": [
        {
          "seq": 1,
          "event_id": 3,
          "channel": "system",
          "event_type": "hand_started",
          "created_at": "2026-04-04T10:00:03Z",
          "payload": {
            "hand_no": 1
          }
        }
      ]
    },
    "last_event_id": 5
  }
}
```

### 3.4 如何判断“现在是不是轮到我”

只要看：

- `data.viewer.is_actor`
- `data.viewer.can_act`

建议客户端以 `can_act` 为准。

如果 `can_act = true`：

- 从 `current_hand.available_actions` 里选动作
- 不要自己猜动作是否合法
- `bet` / `raise` 必须使用后端返回的 `min` / `max`

### 3.5 提交动作

请求：

```http
POST /api/v1/sessions/table-demo-01/actions
Content-Type: application/json
```

```json
{
  "actor_name": "Alice",
  "action": "raise",
  "amount": 300
}
```

也可以传：

```json
{
  "actor_id": "seat_0",
  "action": "call"
}
```

成功响应：

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "phase": "waiting_actor_action",
    "applied_action": {
      "actor_id": "seat_0",
      "street": "preflop",
      "action": "raise",
      "amount": 300
    },
    "next_actor_id": "seat_1",
    "hand_ended": false
  }
}
```

动作说明：

- `fold`: 弃牌
- `check`: 过牌
- `call`: 跟注
- `bet`: 下注到指定总额
- `raise`: 加注到指定总额
- `all_in`: 全下

重要约束：

- 已弃牌玩家不能再动作
- 非当前行动者不能动作
- 非法金额会被拒绝
- 如果 `amount` 不在 `available_actions` 范围内，后端会返回错误

### 3.6 聊天

请求：

```http
POST /api/v1/sessions/table-demo-01/chat
Content-Type: application/json
```

```json
{
  "speaker_name": "Alice",
  "text": "这手我先过。"
}
```

也可以传：

```json
{
  "speaker_id": "seat_0",
  "text": "这手我先过。"
}
```

说明：

- 已弃牌玩家仍然可以聊天
- 聊天会出现在：
  - `current_hand.chat_messages`
  - `current_hand.timeline`
  - `GET /events`
  - `GET /replays/{hand_id}`

### 3.7 当前这手的公共历史

`GET /state?viewer_name=...` 已经直接返回本手的三类历史，不必自己再拼：

- `current_hand.action_history`
- `current_hand.chat_messages`
- `current_hand.timeline`

这些字段只属于当前这手。

当开始下一手时：

- 上一手的 `action_history`
- 上一手的 `chat_messages`
- 上一手的 `timeline`

都会自动切换为新手牌的数据，不会把上一手混进来。

### 3.8 拉事件流

请求：

```http
GET /api/v1/sessions/table-demo-01/events?since_event_id=0&limit=200
```

用途：

- 增量刷新 UI
- 做通知提醒
- 补充聊天滚动

如果客户端只想做简单轮询，也可以只轮询 `/state`，不强制依赖 `/events`。

### 3.9 历史手牌列表

请求：

```http
GET /api/v1/sessions/table-demo-01/hands
```

返回每手的摘要：

- `hand_id`
- `hand_no`
- `winner_ids`
- `winners`
- `pot_total`
- `action_count`
- `chat_count`
- `started_at`
- `ended_at`

### 3.10 单手回放

请求：

```http
GET /api/v1/replays/{hand_id}?viewer_name=Alice
```

回放返回：

- `actions`: 动作序列
- `chat_messages`: 聊天序列
- `timeline`: 按时间排序的完整事件流
- `final_state`: 该手最终状态

回放中的手牌可见性规则和 `/state` 一致。

如果不传 `viewer_name`：

- 只会公开摊牌已亮出的牌
- 弃牌玩家的牌不会显示

## 4. 玩家客户端最小实现建议

一个最小可用客户端建议这样跑：

1. 保存 `session_id` 和自己的 `viewer_name`
2. 每 1 秒轮询 `GET /state?viewer_name=...`
3. 若 `viewer.can_act = true`，读取 `available_actions`
4. 选择一个合法动作后调用 `POST /actions`
5. 任意阶段可调用 `POST /chat`
6. 每手结束后调用 `GET /hands`
7. 如果要显示回放，调用 `GET /replays/{hand_id}?viewer_name=...`

## 5. 常见错误情况

### 5.1 玩家名不存在

可能出现在：

- `viewer_name`
- `actor_name`
- `speaker_name`

返回：

```json
{
  "ok": false,
  "error": {
    "code": "SEAT_NOT_FOUND",
    "message": "未找到玩家 Alice"
  }
}
```

### 5.2 非当前行动者提交动作

返回：

```json
{
  "ok": false,
  "error": {
    "code": "ACTOR_TURN_MISMATCH",
    "message": "当前不是该玩家行动回合",
    "details": {
      "expected_actor_id": "seat_1",
      "actual_actor_id": "seat_0"
    }
  }
}
```

### 5.3 动作不合法

返回：

```json
{
  "ok": false,
  "error": {
    "code": "ACTION_NOT_ALLOWED",
    "message": "当前动作不合法"
  }
}
```

### 5.4 金额不合法

返回：

```json
{
  "ok": false,
  "error": {
    "code": "AMOUNT_OUT_OF_RANGE",
    "message": "金额超出允许范围",
    "details": {
      "min": 200,
      "max": 5000,
      "amount": 150
    }
  }
}
```

### 5.5 已弃牌后继续动作

如果某个玩家已经弃牌，再发动作，通常会得到：

- `ACTOR_TURN_MISMATCH`
- 或 `ACTION_NOT_ALLOWED`
- 或 `SESSION_PHASE_INVALID`

客户端不应该在弃牌后继续尝试动作，应该只保留聊天能力。

## 6. 字段速查

### 6.1 玩家相关

- `viewer_name`: 当前玩家名
- `viewer_seat_id`: 当前玩家的 seat id
- `viewer_seat_no`: 当前玩家的位置

### 6.2 牌局相关

- `hand_id`: 当前手唯一标识
- `hand_no`: 第几手
- `street`: `preflop / flop / turn / river / showdown`
- `board_cards`: 当前公共牌
- `pot_total`: 当前底池

### 6.3 玩家动作相关

- `actor_id`: 当前轮到谁
- `available_actions`: 后端判定的合法动作
- `to_call`: 当前需要跟注额
- `min_bet_to`: 最小下注到多少
- `min_raise_to`: 最小加注到多少

### 6.4 当前手历史相关

- `turn_order`: 当前手顺位
- `action_history`: 当前手动作历史
- `chat_messages`: 当前手聊天记录
- `timeline`: 当前手完整事件流

## 7. 相关接口总表

- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}/state?viewer_name=...`
- `POST /api/v1/sessions/{session_id}/hands`
- `POST /api/v1/sessions/{session_id}/actions`
- `POST /api/v1/sessions/{session_id}/chat`
- `GET /api/v1/sessions/{session_id}/events`
- `GET /api/v1/sessions/{session_id}/hands`
- `GET /api/v1/replays/{hand_id}`
- `GET /api/v1/replays/{hand_id}?viewer_name=...`
