PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- =========================================================
-- 1) sessions
-- =========================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,
    seat_count          INTEGER NOT NULL CHECK (seat_count BETWEEN 2 AND 9),
    small_blind         INTEGER NOT NULL CHECK (small_blind > 0),
    big_blind           INTEGER NOT NULL CHECK (big_blind > small_blind),
    starting_stack      INTEGER NOT NULL CHECK (starting_stack >= big_blind * 20),
    rng_seed            INTEGER NOT NULL DEFAULT 0 CHECK (rng_seed >= 0),
    user_participates   INTEGER NOT NULL DEFAULT 0 CHECK (user_participates IN (0, 1)),
    phase               TEXT NOT NULL CHECK (phase IN (
                            'waiting_start',
                            'running',
                            'waiting_actor_action',
                            'hand_ended',
                            'closed'
                        )),
    current_hand_id     TEXT NULL,
    next_dealer_seat    INTEGER NOT NULL CHECK (next_dealer_seat BETWEEN 0 AND 8),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_phase
    ON sessions (phase);

-- =========================================================
-- 2) session_seats
-- =========================================================
CREATE TABLE IF NOT EXISTS session_seats (
    session_id          TEXT NOT NULL,
    seat_id             TEXT NOT NULL,
    seat_no             INTEGER NOT NULL CHECK (seat_no BETWEEN 0 AND 8),
    display_name        TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 32),
    stack               INTEGER NOT NULL CHECK (stack >= 0),
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,

    PRIMARY KEY (session_id, seat_id),
    UNIQUE (session_id, seat_no),

    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_seats_session_id
    ON session_seats (session_id);

-- =========================================================
-- 3) hands
-- =========================================================
CREATE TABLE IF NOT EXISTS hands (
    hand_id              TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL,
    hand_no              INTEGER NOT NULL CHECK (hand_no >= 1),
    seed                 INTEGER NOT NULL CHECK (seed >= 0),
    dealer_seat          INTEGER NOT NULL CHECK (dealer_seat BETWEEN 0 AND 8),
    small_blind_seat     INTEGER NOT NULL CHECK (small_blind_seat BETWEEN 0 AND 8),
    big_blind_seat       INTEGER NOT NULL CHECK (big_blind_seat BETWEEN 0 AND 8),
    phase                TEXT NOT NULL CHECK (phase IN ('running', 'ended')),
    street               TEXT NOT NULL CHECK (street IN (
                             'preflop',
                             'flop',
                             'turn',
                             'river',
                             'showdown'
                         )),
    board_cards_json     TEXT NOT NULL DEFAULT '[]',
    pot_total            INTEGER NOT NULL DEFAULT 0 CHECK (pot_total >= 0),
    actor_id             TEXT NULL,
    started_at           TEXT NOT NULL,
    ended_at             TEXT NULL,

    UNIQUE (session_id, hand_no),

    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hands_session_id_hand_no
    ON hands (session_id, hand_no DESC);

CREATE INDEX IF NOT EXISTS idx_hands_session_id_phase
    ON hands (session_id, phase);

-- =========================================================
-- 4) hand_seats
-- =========================================================
CREATE TABLE IF NOT EXISTS hand_seats (
    hand_id               TEXT NOT NULL,
    seat_id               TEXT NOT NULL,
    seat_no               INTEGER NOT NULL CHECK (seat_no BETWEEN 0 AND 8),
    display_name          TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 32),
    hole_cards_json       TEXT NOT NULL,
    stack_start           INTEGER NOT NULL CHECK (stack_start >= 0),
    stack_end             INTEGER NULL CHECK (stack_end IS NULL OR stack_end >= 0),
    in_hand               INTEGER NOT NULL CHECK (in_hand IN (0, 1)),
    is_folded             INTEGER NOT NULL CHECK (is_folded IN (0, 1)),
    is_all_in             INTEGER NOT NULL CHECK (is_all_in IN (0, 1)),
    contribution_total    INTEGER NOT NULL DEFAULT 0 CHECK (contribution_total >= 0),
    contribution_street   INTEGER NOT NULL DEFAULT 0 CHECK (contribution_street >= 0),

    PRIMARY KEY (hand_id, seat_id),
    UNIQUE (hand_id, seat_no),

    FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hand_seats_hand_id
    ON hand_seats (hand_id);

-- =========================================================
-- 5) events
-- =========================================================
CREATE TABLE IF NOT EXISTS events (
    event_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL,
    hand_id               TEXT NULL,
    channel               TEXT NOT NULL CHECK (channel IN ('system', 'action', 'chat')),
    event_type            TEXT NOT NULL CHECK (event_type IN (
                             'session_created',
                             'hand_started',
                             'street_changed',
                             'waiting_actor_action',
                             'board_dealt',
                             'showdown_started',
                             'hand_ended',
                             'blind_posted',
                             'action_applied',
                             'folded',
                             'checked',
                             'called',
                             'bet_to',
                             'raised_to',
                             'all_in',
                             'pot_awarded',
                             'chat_sent'
                         )),
    payload_json          TEXT NOT NULL,
    created_at            TEXT NOT NULL,

    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_session_event_id
    ON events (session_id, event_id);

CREATE INDEX IF NOT EXISTS idx_events_session_hand_event_id
    ON events (session_id, hand_id, event_id);

CREATE INDEX IF NOT EXISTS idx_events_hand_id
    ON events (hand_id);

-- =========================================================
-- 6) hand_replays
-- =========================================================
CREATE TABLE IF NOT EXISTS hand_replays (
    hand_id               TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL,
    summary_json          TEXT NOT NULL,
    final_state_json      TEXT NOT NULL,
    created_at            TEXT NOT NULL,

    FOREIGN KEY (hand_id) REFERENCES hands(hand_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hand_replays_session_id
    ON hand_replays (session_id);

-- =========================================================
-- 7) idempotency_requests
--    用于 POST 写接口防重复提交
-- =========================================================
CREATE TABLE IF NOT EXISTS idempotency_requests (
    session_id            TEXT NOT NULL,
    request_id            TEXT NOT NULL,
    request_kind          TEXT NOT NULL CHECK (request_kind IN (
                             'create_session',
                             'start_hand',
                             'submit_action',
                             'send_chat'
                         )),
    resource_id           TEXT NULL,
    response_json         TEXT NOT NULL,
    created_at            TEXT NOT NULL,

    PRIMARY KEY (session_id, request_id),

    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_idempotency_session_kind_created_at
    ON idempotency_requests (session_id, request_kind, created_at DESC);

-- =========================================================
-- 8) 可选触发器：sessions.updated_at 自动维护
-- =========================================================
CREATE TRIGGER IF NOT EXISTS trg_sessions_updated_at
AFTER UPDATE ON sessions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE sessions
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE session_id = NEW.session_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_session_seats_updated_at
AFTER UPDATE ON session_seats
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE session_seats
       SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE session_id = NEW.session_id
       AND seat_id = NEW.seat_id;
END;

COMMIT;

-- =========================================================
-- 设计说明
-- 1. 时间统一以 UTC ISO-8601 字符串保存
-- 2. JSON 字段使用 TEXT 存储，由应用层负责序列化/反序列化
-- 3. 金额全部为整数筹码点数
-- 4. 写接口推荐使用 session 级串行锁 + 单事务提交
-- =========================================================
