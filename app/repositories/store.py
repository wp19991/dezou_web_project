from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, text

from app.core.utils import json_dumps, json_loads


class Store:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def fetch_session(self, session_id: str) -> dict[str, Any] | None:
        sql = text("SELECT * FROM sessions WHERE session_id = :session_id")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"session_id": session_id}).mappings().first()
        return dict(row) if row else None

    def fetch_session_seats(self, session_id: str) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT * FROM session_seats
            WHERE session_id = :session_id
            ORDER BY seat_no ASC
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"session_id": session_id}).mappings().all()
        return [dict(row) for row in rows]

    def fetch_hand(self, hand_id: str) -> dict[str, Any] | None:
        sql = text("SELECT * FROM hands WHERE hand_id = :hand_id")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"hand_id": hand_id}).mappings().first()
        return dict(row) if row else None

    def fetch_current_hand(self, session_id: str) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT h.*
            FROM hands h
            JOIN sessions s ON s.current_hand_id = h.hand_id
            WHERE s.session_id = :session_id
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"session_id": session_id}).mappings().first()
        return dict(row) if row else None

    def fetch_hand_seats(self, hand_id: str) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT * FROM hand_seats
            WHERE hand_id = :hand_id
            ORDER BY seat_no ASC
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"hand_id": hand_id}).mappings().all()
        return [dict(row) for row in rows]

    def fetch_last_event_id(self, session_id: str) -> int:
        sql = text(
            """
            SELECT COALESCE(MAX(event_id), 0) AS value
            FROM events
            WHERE session_id = :session_id
            """
        )
        with self.engine.connect() as conn:
            value = conn.execute(sql, {"session_id": session_id}).scalar_one()
        return int(value)

    def list_events(self, session_id: str, since_event_id: int, limit: int) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT * FROM events
            WHERE session_id = :session_id
              AND event_id > :since_event_id
            ORDER BY event_id ASC
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "session_id": session_id,
                    "since_event_id": since_event_id,
                    "limit": limit,
                },
            ).mappings().all()
        return [dict(row) for row in rows]

    def list_hand_events(self, hand_id: str) -> list[dict[str, Any]]:
        sql = text(
            """
            SELECT * FROM events
            WHERE hand_id = :hand_id
            ORDER BY event_id ASC
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"hand_id": hand_id}).mappings().all()
        return [dict(row) for row in rows]

    def fetch_replay_row(self, hand_id: str) -> dict[str, Any] | None:
        sql = text("SELECT * FROM hand_replays WHERE hand_id = :hand_id")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"hand_id": hand_id}).mappings().first()
        return dict(row) if row else None

    def fetch_idempotency(
        self,
        session_id: str,
        request_id: str,
        request_kind: str,
    ) -> dict[str, Any] | None:
        sql = text(
            """
            SELECT * FROM idempotency_requests
            WHERE session_id = :session_id
              AND request_id = :request_id
              AND request_kind = :request_kind
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(
                sql,
                {
                    "session_id": session_id,
                    "request_id": request_id,
                    "request_kind": request_kind,
                },
            ).mappings().first()
        return dict(row) if row else None

    def next_hand_no(self, session_id: str) -> int:
        sql = text(
            """
            SELECT COALESCE(MAX(hand_no), 0) + 1 AS value
            FROM hands
            WHERE session_id = :session_id
            """
        )
        with self.engine.connect() as conn:
            value = conn.execute(sql, {"session_id": session_id}).scalar_one()
        return int(value)

    def count_hand_chat_events(self, hand_id: str) -> int:
        sql = text(
            """
            SELECT COUNT(*) AS value
            FROM events
            WHERE hand_id = :hand_id
              AND channel = 'chat'
            """
        )
        with self.engine.connect() as conn:
            value = conn.execute(sql, {"hand_id": hand_id}).scalar_one()
        return int(value)

    def list_hands(
        self,
        session_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        total_sql = text("SELECT COUNT(*) AS value FROM hands WHERE session_id = :session_id")
        items_sql = text(
            """
            SELECT h.hand_id, h.hand_no, h.dealer_seat, h.started_at, h.ended_at, hr.summary_json
            FROM hands h
            LEFT JOIN hand_replays hr ON hr.hand_id = h.hand_id
            WHERE h.session_id = :session_id
            ORDER BY h.hand_no DESC
            LIMIT :limit OFFSET :offset
            """
        )
        with self.engine.connect() as conn:
            total = int(conn.execute(total_sql, {"session_id": session_id}).scalar_one())
            rows = conn.execute(
                items_sql,
                {"session_id": session_id, "limit": limit, "offset": offset},
            ).mappings().all()
        items: list[dict[str, Any]] = []
        for row in rows:
            summary = json_loads(row["summary_json"]) if row["summary_json"] else None
            if summary:
                items.append(summary)
            else:
                items.append(
                    {
                        "hand_id": row["hand_id"],
                        "hand_no": row["hand_no"],
                        "dealer_seat": row["dealer_seat"],
                        "winner_ids": [],
                        "pot_total": 0,
                        "action_count": 0,
                        "chat_count": 0,
                        "started_at": row["started_at"],
                        "ended_at": row["ended_at"],
                    }
                )
        return items, total

    def create_session(
        self,
        session_row: dict[str, Any],
        seat_rows: Sequence[dict[str, Any]],
        events: Sequence[dict[str, Any]],
        request_id: str | None,
        response: dict[str, Any],
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sessions (
                        session_id, seat_count, small_blind, big_blind, starting_stack,
                        rng_seed,
                        phase, current_hand_id, next_dealer_seat, created_at, updated_at
                    ) VALUES (
                        :session_id, :seat_count, :small_blind, :big_blind, :starting_stack,
                        :rng_seed,
                        :phase, :current_hand_id, :next_dealer_seat, :created_at, :updated_at
                    )
                    """
                ),
                session_row,
            )
            for seat_row in seat_rows:
                conn.execute(
                    text(
                        """
                        INSERT INTO session_seats (
                            session_id, seat_id, seat_no, display_name,
                            stack, created_at, updated_at
                        ) VALUES (
                            :session_id, :seat_id, :seat_no, :display_name,
                            :stack, :created_at, :updated_at
                        )
                        """
                    ),
                    seat_row,
                )
            self._insert_events(conn, events)
            if request_id:
                self._insert_idempotency(
                    conn,
                    session_row["session_id"],
                    request_id,
                    "create_session",
                    session_row["session_id"],
                    response,
                )

    def start_hand(
        self,
        session_update: dict[str, Any],
        hand_row: dict[str, Any],
        hand_seats: Sequence[dict[str, Any]],
        events: Sequence[dict[str, Any]],
        request_id: str | None,
        response: dict[str, Any],
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET phase = :phase,
                        current_hand_id = :current_hand_id,
                        next_dealer_seat = :next_dealer_seat,
                        updated_at = :updated_at
                    WHERE session_id = :session_id
                    """
                ),
                session_update,
            )
            conn.execute(
                text(
                    """
                    INSERT INTO hands (
                        hand_id, session_id, hand_no, seed, dealer_seat,
                        small_blind_seat, big_blind_seat,
                        phase, street, board_cards_json, pot_total, actor_id, started_at, ended_at
                    ) VALUES (
                        :hand_id, :session_id, :hand_no, :seed, :dealer_seat,
                        :small_blind_seat, :big_blind_seat, :phase, :street,
                        :board_cards_json, :pot_total, :actor_id, :started_at,
                        :ended_at
                    )
                    """
                ),
                hand_row,
            )
            for hand_seat in hand_seats:
                conn.execute(
                    text(
                        """
                        INSERT INTO hand_seats (
                            hand_id, seat_id, seat_no, display_name, hole_cards_json,
                            stack_start, stack_end, in_hand, is_folded, is_all_in,
                            contribution_total, contribution_street
                        ) VALUES (
                            :hand_id, :seat_id, :seat_no, :display_name, :hole_cards_json,
                            :stack_start, :stack_end, :in_hand, :is_folded, :is_all_in,
                            :contribution_total, :contribution_street
                        )
                        """
                    ),
                    hand_seat,
                )
            self._insert_events(conn, events)
            if request_id:
                self._insert_idempotency(
                    conn,
                    session_update["session_id"],
                    request_id,
                    "start_hand",
                    hand_row["hand_id"],
                    response,
                )

    def persist_hand_progress(
        self,
        session_update: dict[str, Any],
        hand_update: dict[str, Any],
        hand_seats: Sequence[dict[str, Any]],
        events: Sequence[dict[str, Any]],
        request_id: str | None,
        response: dict[str, Any],
        replay_summary: dict[str, Any] | None = None,
        replay_final_state: dict[str, Any] | None = None,
        final_session_seats: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET phase = :phase,
                        current_hand_id = :current_hand_id,
                        next_dealer_seat = :next_dealer_seat,
                        updated_at = :updated_at
                    WHERE session_id = :session_id
                    """
                ),
                session_update,
            )
            conn.execute(
                text(
                    """
                    UPDATE hands
                    SET phase = :phase,
                        street = :street,
                        board_cards_json = :board_cards_json,
                        pot_total = :pot_total,
                        actor_id = :actor_id,
                        ended_at = :ended_at
                    WHERE hand_id = :hand_id
                    """
                ),
                hand_update,
            )
            for hand_seat in hand_seats:
                conn.execute(
                    text(
                        """
                        UPDATE hand_seats
                        SET hole_cards_json = :hole_cards_json,
                            stack_end = :stack_end,
                            in_hand = :in_hand,
                            is_folded = :is_folded,
                            is_all_in = :is_all_in,
                            contribution_total = :contribution_total,
                            contribution_street = :contribution_street
                        WHERE hand_id = :hand_id
                          AND seat_id = :seat_id
                        """
                    ),
                    hand_seat,
                )
            self._insert_events(conn, events)
            if final_session_seats:
                for session_seat in final_session_seats:
                    conn.execute(
                        text(
                            """
                            UPDATE session_seats
                            SET stack = :stack, updated_at = :updated_at
                            WHERE session_id = :session_id
                              AND seat_id = :seat_id
                            """
                        ),
                        session_seat,
                    )
            if replay_summary and replay_final_state:
                conn.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO hand_replays (
                            hand_id, session_id, summary_json, final_state_json, created_at
                        ) VALUES (
                            :hand_id, :session_id, :summary_json, :final_state_json, :created_at
                        )
                        """
                    ),
                    {
                        "hand_id": replay_summary["hand_id"],
                        "session_id": replay_summary["session_id"],
                        "summary_json": json_dumps(replay_summary),
                        "final_state_json": json_dumps(replay_final_state),
                        "created_at": replay_summary["ended_at"],
                    },
                )
            if request_id:
                self._insert_idempotency(
                    conn,
                    session_update["session_id"],
                    request_id,
                    "submit_action",
                    hand_update["hand_id"],
                    response,
                )

    def record_chat(
        self,
        session_id: str,
        hand_id: str | None,
        event: dict[str, Any],
    ) -> int:
        with self.engine.begin() as conn:
            event_id = self._insert_events(conn, [event])[0]
        return event_id

    def save_chat_idempotency(
        self,
        session_id: str,
        request_id: str,
        hand_id: str | None,
        response: dict[str, Any],
    ) -> None:
        with self.engine.begin() as conn:
            self._insert_idempotency(
                conn,
                session_id,
                request_id,
                "send_chat",
                hand_id,
                response,
            )

    def _insert_events(self, conn: Any, events: Sequence[dict[str, Any]]) -> list[int]:
        event_ids: list[int] = []
        for event in events:
            result = conn.execute(
                text(
                    """
                    INSERT INTO events (
                        session_id, hand_id, channel, event_type, payload_json, created_at
                    ) VALUES (
                        :session_id, :hand_id, :channel, :event_type, :payload_json, :created_at
                    )
                    """
                ),
                {
                    "session_id": event["session_id"],
                    "hand_id": event.get("hand_id"),
                    "channel": event["channel"],
                    "event_type": event["event_type"],
                    "payload_json": json_dumps(event["payload"]),
                    "created_at": event["created_at"],
                },
            )
            event_ids.append(int(result.lastrowid))
        return event_ids

    def _insert_idempotency(
        self,
        conn: Any,
        session_id: str,
        request_id: str,
        request_kind: str,
        resource_id: str | None,
        response: dict[str, Any],
    ) -> None:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO idempotency_requests (
                    session_id, request_id, request_kind, resource_id, response_json, created_at
                ) VALUES (
                    :session_id, :request_id, :request_kind, :resource_id,
                    :response_json, :created_at
                )
                """
            ),
            {
                "session_id": session_id,
                "request_id": request_id,
                "request_kind": request_kind,
                "resource_id": resource_id,
                "response_json": json_dumps(response),
                "created_at": (
                    response.get("created_at")
                    or response.get("data", {}).get("created_at")
                ),
            },
        )

    @staticmethod
    def deserialize_event(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "session_id": row["session_id"],
            "hand_id": row["hand_id"],
            "channel": row["channel"],
            "event_type": row["event_type"],
            "payload": json_loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
