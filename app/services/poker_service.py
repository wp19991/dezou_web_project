from __future__ import annotations

from copy import deepcopy
from secrets import randbelow
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError
from app.core.utils import generate_session_id, json_loads, to_iso
from app.domain.schemas import (
    CreateSessionRequest,
    SendChatRequest,
    StartHandRequest,
    SubmitActionRequest,
)
from app.engine.table_kernel import TableKernel
from app.repositories.store import Store
from app.services.runtime_registry import RuntimeRegistry


class PokerService:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        registry: RuntimeRegistry,
        kernel: TableKernel,
    ) -> None:
        self.settings = settings
        self.store = store
        self.registry = registry
        self.kernel = kernel

    async def create_session(self, request: CreateSessionRequest) -> dict[str, Any]:
        session_id = request.session_id or generate_session_id()
        if request.request_id and request.session_id:
            cached = self.store.fetch_idempotency(session_id, request.request_id, "create_session")
            if cached:
                return json_loads(cached["response_json"])

        if self.store.fetch_session(session_id):
            raise AppError("INVALID_REQUEST", "session_id 已存在", 409)

        created_at = to_iso()
        session_seed = request.seed if request.seed is not None else randbelow(2_147_483_648)
        seat_names = request.seat_names or [f"玩家{i + 1}" for i in range(request.seat_count)]
        seat_rows = [
            {
                "session_id": session_id,
                "seat_id": f"seat_{seat_no}",
                "seat_no": seat_no,
                "display_name": seat_names[seat_no],
                "stack": request.starting_stack,
                "created_at": created_at,
                "updated_at": created_at,
            }
            for seat_no in range(request.seat_count)
        ]
        session_row = {
            "session_id": session_id,
            "seat_count": request.seat_count,
            "small_blind": request.small_blind,
            "big_blind": request.big_blind,
            "starting_stack": request.starting_stack,
            "rng_seed": session_seed,
            "phase": "waiting_start",
            "current_hand_id": None,
            "next_dealer_seat": 0,
            "created_at": created_at,
            "updated_at": created_at,
        }
        data = {
            "session_id": session_id,
            "phase": "waiting_start",
            "seat_count": request.seat_count,
            "small_blind": request.small_blind,
            "big_blind": request.big_blind,
            "starting_stack": request.starting_stack,
            "session_seed": session_seed,
            "seats": [
                {
                    "seat_id": row["seat_id"],
                    "seat_no": row["seat_no"],
                    "display_name": row["display_name"],
                    "stack": row["stack"],
                }
                for row in seat_rows
            ],
            "created_at": created_at,
        }
        response = self._ok(data)
        events = [
            {
                "session_id": session_id,
                "hand_id": None,
                "channel": "system",
                "event_type": "session_created",
                "payload": {
                    "session_id": session_id,
                    "seat_count": request.seat_count,
                    "small_blind": request.small_blind,
                    "big_blind": request.big_blind,
                    "starting_stack": request.starting_stack,
                    "session_seed": session_seed,
                },
                "created_at": created_at,
            }
        ]
        idempotency_key = request.request_id if request.session_id else None
        self.store.create_session(session_row, seat_rows, events, idempotency_key, response)
        return response

    async def get_state(
        self,
        session_id: str,
        viewer_name: str | None = None,
    ) -> dict[str, Any]:
        session_row = self._require_session(session_id)
        session_seats = self.store.fetch_session_seats(session_id)
        current_hand = self._current_hand_state(session_row)
        current_hand = self._attach_hand_activity(current_hand)
        viewer = None
        if viewer_name:
            viewer_seat = self._require_named_seat(session_id, viewer_name)
            current_hand = self._filter_hand_for_viewer(current_hand, viewer_seat["seat_id"])
            viewer = self._viewer_payload(viewer_seat, current_hand)
        return self._ok(
            {
                "session_id": session_id,
                "phase": session_row["phase"],
                "seat_count": int(session_row["seat_count"]),
                "small_blind": int(session_row["small_blind"]),
                "big_blind": int(session_row["big_blind"]),
                "starting_stack": int(session_row["starting_stack"]),
                "session_seed": int(session_row["rng_seed"]),
                "next_dealer_seat": int(session_row["next_dealer_seat"]),
                "seats": [
                    {
                        "seat_id": seat["seat_id"],
                        "seat_no": int(seat["seat_no"]),
                        "display_name": seat["display_name"],
                        "stack": int(seat["stack"]),
                    }
                    for seat in session_seats
                ],
                "current_hand": current_hand,
                "viewer": viewer,
                "last_event_id": self.store.fetch_last_event_id(session_id),
            }
        )

    async def start_hand(self, session_id: str, request: StartHandRequest) -> dict[str, Any]:
        async with self.registry.get_lock(session_id):
            session_row = self._require_session(session_id)
            if request.request_id:
                cached = self.store.fetch_idempotency(session_id, request.request_id, "start_hand")
                if cached:
                    return json_loads(cached["response_json"])
            if session_row["phase"] not in {"waiting_start", "hand_ended"}:
                raise AppError("HAND_ALREADY_RUNNING", "当前已有未结束手牌", 409)

            seat_count = int(session_row["seat_count"])
            if request.dealer_seat is not None:
                dealer_seat = request.dealer_seat
            else:
                dealer_seat = int(session_row["next_dealer_seat"])
            if dealer_seat >= seat_count:
                raise AppError("INVALID_REQUEST", "dealer_seat 超出 seat_count", 422)

            runtime = self._get_or_restore_runtime(session_row)
            if runtime and runtime.phase != "ended":
                raise AppError("HAND_ALREADY_RUNNING", "当前已有未结束手牌", 409)

            session_seats = self.store.fetch_session_seats(session_id)
            hand_no = self.store.next_hand_no(session_id)
            hand_seed = self._derive_hand_seed(int(session_row["rng_seed"]), hand_no)
            runtime, events = self.kernel.start_hand(
                session_row,
                session_seats,
                hand_no,
                hand_seed,
                dealer_seat,
            )

            updated_at = to_iso()
            session_update = {
                "session_id": session_id,
                "phase": "waiting_actor_action" if runtime.actor_id else "hand_ended",
                "current_hand_id": runtime.hand_id,
                "next_dealer_seat": (dealer_seat + 1) % seat_count,
                "updated_at": updated_at,
            }
            data = {
                "session_id": session_id,
                "session_seed": int(session_row["rng_seed"]),
                "phase": session_update["phase"],
                "current_hand": self.kernel.current_hand_state(runtime),
            }
            response = self._ok(data)
            self.store.start_hand(
                session_update,
                self.kernel.hand_row(runtime),
                self.kernel.hand_seat_rows(runtime),
                events,
                request.request_id,
                response,
            )
            self.registry.set_runtime(session_id, runtime)
            return response

    async def submit_action(self, session_id: str, request: SubmitActionRequest) -> dict[str, Any]:
        async with self.registry.get_lock(session_id):
            session_row = self._require_session(session_id)
            if request.request_id:
                cached = self.store.fetch_idempotency(
                    session_id,
                    request.request_id,
                    "submit_action",
                )
                if cached:
                    return json_loads(cached["response_json"])
            if session_row["phase"] != "waiting_actor_action":
                raise AppError("SESSION_PHASE_INVALID", "当前阶段不允许提交动作", 409)

            runtime = self.registry.get_runtime(session_id)
            if not runtime or runtime.hand_id != session_row["current_hand_id"]:
                raise AppError("SESSION_PHASE_INVALID", "当前牌局运行时状态不可用", 409)

            actor_id = self._resolve_actor_id(
                session_id,
                request.actor_id,
                request.actor_name,
            )
            applied_action, events, hand_ended = self.kernel.apply_action(
                runtime, actor_id, request.action, request.amount
            )
            updated_at = to_iso()
            phase = "hand_ended" if hand_ended else "waiting_actor_action"
            session_update = {
                "session_id": session_id,
                "phase": phase,
                "current_hand_id": runtime.hand_id,
                "next_dealer_seat": session_row["next_dealer_seat"],
                "updated_at": updated_at,
            }
            response = self._ok(
                {
                    "accepted": True,
                    "phase": phase,
                    "applied_action": applied_action,
                    "next_actor_id": runtime.actor_id,
                    "hand_ended": hand_ended,
                }
            )

            replay_summary = None
            replay_final_state = None
            final_session_seats = None
            if hand_ended:
                chat_count = self.store.count_hand_chat_events(runtime.hand_id)
                replay_summary = self.kernel.summary(runtime, chat_count)
                replay_final_state = self.kernel.replay_final_state(runtime)
                final_session_seats = [
                    {
                        "session_id": session_id,
                        "seat_id": seat_id,
                        "stack": stack,
                        "updated_at": updated_at,
                    }
                    for seat_id, stack in replay_final_state["final_stacks"].items()
                ]

            self.store.persist_hand_progress(
                session_update,
                self.kernel.hand_row(runtime),
                self.kernel.hand_seat_rows(runtime),
                events,
                request.request_id,
                response,
                replay_summary=replay_summary,
                replay_final_state=replay_final_state,
                final_session_seats=final_session_seats,
            )
            self.registry.set_runtime(session_id, runtime)
            return response

    async def send_chat(self, session_id: str, request: SendChatRequest) -> dict[str, Any]:
        async with self.registry.get_lock(session_id):
            session_row = self._require_session(session_id)
            if request.request_id:
                cached = self.store.fetch_idempotency(session_id, request.request_id, "send_chat")
                if cached:
                    return json_loads(cached["response_json"])
            speaker_id = self._resolve_actor_id(
                session_id,
                request.speaker_id,
                request.speaker_name,
            )

            created_at = to_iso()
            hand_id = session_row["current_hand_id"]
            event = {
                "session_id": session_id,
                "hand_id": hand_id,
                "channel": "chat",
                "event_type": "chat_sent",
                "payload": {"speaker_id": speaker_id, "text": request.text},
                "created_at": created_at,
            }
            response = self._ok(
                {
                    "session_id": session_id,
                    "hand_id": hand_id,
                    "event_id": 0,
                    "created_at": created_at,
                }
            )
            event_id = self.store.record_chat(session_id, hand_id, event)
            response["data"]["event_id"] = event_id
            if hand_id:
                self.store.refresh_replay_chat_count(hand_id)
            if request.request_id:
                self.store.save_chat_idempotency(session_id, request.request_id, hand_id, response)
            return response

    async def list_events(self, session_id: str, since_event_id: int, limit: int) -> dict[str, Any]:
        self._require_session(session_id)
        rows = self.store.list_events(session_id, since_event_id, limit)
        events = [self.store.deserialize_event(row) for row in rows]
        next_since = events[-1]["event_id"] if events else since_event_id
        return self._ok(
            {
                "session_id": session_id,
                "count": len(events),
                "events": [
                    {
                        "event_id": event["event_id"],
                        "hand_id": event["hand_id"],
                        "channel": event["channel"],
                        "event_type": event["event_type"],
                        "created_at": event["created_at"],
                        "payload": event["payload"],
                    }
                    for event in events
                ],
                "next_since_event_id": next_since,
            }
        )

    async def list_hands(self, session_id: str, limit: int, offset: int) -> dict[str, Any]:
        self._require_session(session_id)
        items, total = self.store.list_hands(session_id, limit, offset)
        return self._ok({"session_id": session_id, "items": items, "total": total})

    async def get_replay(
        self,
        hand_id: str,
        viewer_name: str | None = None,
    ) -> dict[str, Any]:
        replay_row = self.store.fetch_replay_row(hand_id)
        if not replay_row:
            if self.store.fetch_hand(hand_id):
                raise AppError("REPLAY_NOT_READY", "回放尚未生成", 409)
            raise AppError("HAND_NOT_FOUND", "hand 不存在", 404)

        final_state = json_loads(replay_row["final_state_json"])
        events = [self.store.deserialize_event(row) for row in self.store.list_hand_events(hand_id)]
        final_state = self._attach_hand_activity(final_state, events)
        if viewer_name:
            viewer_seat = self._require_named_seat(final_state["session_id"], viewer_name)
            final_state = self._filter_hand_for_viewer(final_state, viewer_seat["seat_id"])
        else:
            final_state = self._filter_hand_for_public_replay(final_state)
        return self._ok(
            {
                "hand_id": final_state["hand_id"],
                "session_id": final_state["session_id"],
                "hand_no": final_state["hand_no"],
                "session_seed": final_state.get("session_seed"),
                "seed": final_state["seed"],
                "dealer_seat": final_state["dealer_seat"],
                "board_cards": final_state["board_cards"],
                "winners": final_state["winners"],
                "final_stacks": final_state["final_stacks"],
                "actions": final_state["action_history"],
                "chat_messages": final_state["chat_messages"],
                "timeline": final_state["timeline"],
                "final_state": final_state,
            }
        )

    async def get_health(self) -> dict[str, Any]:
        return self._ok({"service": self.settings.service_name, "status": "up"})

    def persisted_hand_state(
        self,
        session_row: dict[str, Any],
        hand_row: dict[str, Any],
        hand_seats: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "hand_id": hand_row["hand_id"],
            "hand_no": hand_row["hand_no"],
            "session_seed": int(session_row["rng_seed"]),
            "seed": hand_row["seed"],
            "street": hand_row["street"],
            "dealer_seat": hand_row["dealer_seat"],
            "small_blind_seat": hand_row["small_blind_seat"],
            "big_blind_seat": hand_row["big_blind_seat"],
            "actor_id": hand_row["actor_id"],
            "to_call": None,
            "min_bet_to": None,
            "min_raise_to": None,
            "pot_total": hand_row["pot_total"],
            "board_cards": json_loads(hand_row["board_cards_json"]),
            "showdown_started": hand_row["street"] == "showdown",
            "showdown_seat_ids": [],
            "winners": [],
            "seats": [
                {
                    "seat_id": seat["seat_id"],
                    "seat_no": seat["seat_no"],
                    "display_name": seat["display_name"],
                    "stack": (
                        seat["stack_end"]
                        if seat["stack_end"] is not None
                        else seat["stack_start"]
                    ),
                    "stack_start": seat["stack_start"],
                    "contribution_total": seat["contribution_total"],
                    "contribution_street": seat["contribution_street"],
                    "is_folded": bool(seat["is_folded"]),
                    "is_all_in": bool(seat["is_all_in"]),
                    "in_hand": bool(seat["in_hand"]),
                    "hole_cards": json_loads(seat["hole_cards_json"]),
                    "hole_cards_visible": True,
                    "showdown_competing": False,
                    "best_hand_label": None,
                    "best_hand_cards": [],
                    "is_winner": False,
                    "win_amount": 0,
                }
                for seat in hand_seats
            ],
            "available_actions": [],
        }

    def _current_hand_state(self, session_row: dict[str, Any]) -> dict[str, Any] | None:
        session_id = session_row["session_id"]
        runtime = self._get_or_restore_runtime(session_row)
        if runtime and runtime.hand_id == session_row["current_hand_id"]:
            return self.kernel.current_hand_state(runtime)
        if not session_row["current_hand_id"]:
            return None
        hand_row = self.store.fetch_current_hand(session_id)
        if not hand_row:
            return None
        hand_seats = self.store.fetch_hand_seats(hand_row["hand_id"])
        replay_row = self.store.fetch_replay_row(hand_row["hand_id"])
        replay_final_state = (
            json_loads(replay_row["final_state_json"]) if replay_row else None
        )
        state = self.persisted_hand_state(session_row, hand_row, hand_seats)
        if replay_final_state:
            self._merge_replay_state(state, replay_final_state)
        return state

    def _get_or_restore_runtime(self, session_row: dict[str, Any]) -> Any | None:
        session_id = session_row["session_id"]
        runtime = self.registry.get_runtime(session_id)
        if runtime and runtime.hand_id == session_row["current_hand_id"]:
            return runtime
        if session_row["phase"] != "waiting_actor_action" or not session_row["current_hand_id"]:
            return runtime

        hand_row = self.store.fetch_current_hand(session_id)
        if not hand_row or hand_row["phase"] != "running":
            return runtime

        session_seats = self.store.fetch_session_seats(session_id)
        hand_events = [
            self.store.deserialize_event(row)
            for row in self.store.list_hand_events(hand_row["hand_id"])
        ]
        restored = self.kernel.restore_hand(session_row, session_seats, hand_row, hand_events)
        self.registry.set_runtime(session_id, restored)
        return restored

    def _require_session(self, session_id: str) -> dict[str, Any]:
        session_row = self.store.fetch_session(session_id)
        if not session_row:
            raise AppError("SESSION_NOT_FOUND", "session 不存在", 404)
        return session_row

    def _ok(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "data": data}

    def _derive_hand_seed(self, session_seed: int, hand_no: int) -> int:
        return int((session_seed + hand_no - 1) % 2_147_483_648)

    def _merge_replay_state(
        self,
        current_hand: dict[str, Any],
        replay_final_state: dict[str, Any],
    ) -> None:
        current_hand["showdown_started"] = bool(
            replay_final_state.get("showdown_seat_ids")
        )
        current_hand["showdown_seat_ids"] = list(
            replay_final_state.get("showdown_seat_ids", [])
        )
        current_hand["winners"] = list(replay_final_state.get("winners", []))
        seat_overrides = {
            seat["seat_id"]: seat for seat in replay_final_state.get("seats", [])
        }
        for seat in current_hand["seats"]:
            override = seat_overrides.get(seat["seat_id"])
            if not override:
                continue
            seat["showdown_competing"] = bool(override.get("showdown_competing"))
            seat["best_hand_label"] = override.get("best_hand_label")
            seat["best_hand_cards"] = list(override.get("best_hand_cards", []))
            seat["is_winner"] = bool(override.get("is_winner"))
            seat["win_amount"] = int(override.get("win_amount") or 0)
            seat["hole_cards_visible"] = bool(override.get("hole_cards_visible", True))

    def _attach_hand_activity(
        self,
        current_hand: dict[str, Any] | None,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        if current_hand is None:
            return None
        hand_events = events
        if hand_events is None:
            hand_events = [
                self.store.deserialize_event(row)
                for row in self.store.list_hand_events(current_hand["hand_id"])
            ]
        current_hand["turn_order"] = self._turn_order(current_hand)
        current_hand["action_history"] = self._action_history(
            hand_events,
            current_hand.get("seats", []),
        )
        current_hand["chat_messages"] = self._chat_history(
            hand_events,
            current_hand.get("seats", []),
        )
        current_hand["timeline"] = self._timeline(
            hand_events,
            current_hand.get("seats", []),
        )
        return current_hand

    def _require_named_seat(self, session_id: str, display_name: str) -> dict[str, Any]:
        normalized = display_name.strip()
        seats = self.store.fetch_session_seats(session_id)
        for seat in seats:
            if seat["display_name"] == normalized:
                return seat
        raise AppError("SEAT_NOT_FOUND", f"未找到玩家 {normalized}", 404)

    def _resolve_actor_id(
        self,
        session_id: str,
        seat_id: str | None,
        display_name: str | None,
    ) -> str:
        seats = self.store.fetch_session_seats(session_id)
        seat_by_id = {seat["seat_id"]: seat for seat in seats}
        seat_by_name = {seat["display_name"]: seat for seat in seats}
        resolved_by_id = None
        resolved_by_name = None
        if seat_id:
            resolved_by_id = seat_by_id.get(seat_id)
            if not resolved_by_id:
                raise AppError("SEAT_NOT_FOUND", "seat 不存在", 404)
        if display_name:
            resolved_by_name = seat_by_name.get(display_name.strip())
            if not resolved_by_name:
                raise AppError("SEAT_NOT_FOUND", f"未找到玩家 {display_name.strip()}", 404)
        if (
            resolved_by_id
            and resolved_by_name
            and resolved_by_id["seat_id"] != resolved_by_name["seat_id"]
        ):
            raise AppError("INVALID_REQUEST", "actor_id 与 actor_name 不匹配", 422)
        resolved = resolved_by_id or resolved_by_name
        if not resolved:
            raise AppError("INVALID_REQUEST", "必须提供 actor_id 或 actor_name", 422)
        return str(resolved["seat_id"])

    def _filter_hand_for_viewer(
        self,
        current_hand: dict[str, Any] | None,
        viewer_seat_id: str,
    ) -> dict[str, Any] | None:
        if current_hand is None:
            return None
        filtered = deepcopy(current_hand)
        showdown_visible = set(filtered.get("showdown_seat_ids", []))
        for seat in filtered.get("seats", []):
            visible = (
                seat["seat_id"] == viewer_seat_id
                or seat["seat_id"] in showdown_visible
            )
            seat["hole_cards_visible"] = visible
            if not visible:
                seat["hole_cards"] = []
                seat["best_hand_cards"] = []
                if not seat.get("showdown_competing"):
                    seat["best_hand_label"] = None
        return filtered

    def _filter_hand_for_public_replay(
        self,
        current_hand: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if current_hand is None:
            return None
        filtered = deepcopy(current_hand)
        showdown_visible = set(filtered.get("showdown_seat_ids", []))
        for seat in filtered.get("seats", []):
            visible = seat["seat_id"] in showdown_visible
            seat["hole_cards_visible"] = visible
            if not visible:
                seat["hole_cards"] = []
                seat["best_hand_cards"] = []
                seat["best_hand_label"] = None
        return filtered

    def _viewer_payload(
        self,
        viewer_seat: dict[str, Any],
        current_hand: dict[str, Any] | None,
    ) -> dict[str, Any]:
        viewer_hand_state = None
        if current_hand:
            viewer_hand_state = next(
                (
                    seat
                    for seat in current_hand.get("seats", [])
                    if seat["seat_id"] == viewer_seat["seat_id"]
                ),
                None,
            )
        return {
            "viewer_name": viewer_seat["display_name"],
            "viewer_seat_id": viewer_seat["seat_id"],
            "viewer_seat_no": viewer_seat["seat_no"],
            "is_actor": bool(
                current_hand
                and current_hand.get("actor_id") == viewer_seat["seat_id"]
            ),
            "can_act": bool(
                current_hand
                and current_hand.get("actor_id") == viewer_seat["seat_id"]
                and current_hand.get("available_actions")
            ),
            "is_folded": bool(viewer_hand_state and viewer_hand_state.get("is_folded")),
            "in_hand": bool(viewer_hand_state and viewer_hand_state.get("in_hand")),
        }

    def _turn_order(self, current_hand: dict[str, Any]) -> list[dict[str, Any]]:
        seats = sorted(current_hand.get("seats", []), key=lambda item: item["seat_no"])
        seat_nos = [seat["seat_no"] for seat in seats]
        dealer_seat = current_hand["dealer_seat"]
        pivot = seat_nos.index(dealer_seat)
        rotated = seat_nos[pivot + 1 :] + seat_nos[: pivot + 1]
        seat_by_no = {seat["seat_no"]: seat for seat in seats}
        return [
            {
                "seat_id": seat_by_no[seat_no]["seat_id"],
                "display_name": seat_by_no[seat_no]["display_name"],
                "seat_no": seat_no,
            }
            for seat_no in rotated
        ]

    def _action_history(
        self,
        hand_events: list[dict[str, Any]],
        seats: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items = []
        for index, event in enumerate(
            [item for item in hand_events if item["event_type"] == "action_applied"],
            start=1,
        ):
            items.append(
                {
                    "seq": index,
                    "event_id": event["event_id"],
                    "created_at": event["created_at"],
                    "actor_id": event["payload"]["actor_id"],
                    "actor_name": self._seat_name(event["payload"]["actor_id"], seats),
                    "street": event["payload"]["street"],
                    "action": event["payload"]["action"],
                    "amount": event["payload"].get("amount"),
                }
            )
        return items

    def _chat_history(
        self,
        hand_events: list[dict[str, Any]],
        seats: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items = []
        for index, event in enumerate(
            [item for item in hand_events if item["event_type"] == "chat_sent"],
            start=1,
        ):
            items.append(
                {
                    "seq": index,
                    "event_id": event["event_id"],
                    "created_at": event["created_at"],
                    "speaker_id": event["payload"]["speaker_id"],
                    "speaker_name": self._seat_name(event["payload"]["speaker_id"], seats),
                    "text": event["payload"]["text"],
                }
            )
        return items

    def _timeline(
        self,
        hand_events: list[dict[str, Any]],
        seats: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items = []
        for index, event in enumerate(hand_events, start=1):
            payload = dict(event["payload"])
            if "actor_id" in payload:
                payload["actor_name"] = self._seat_name(payload["actor_id"], seats)
            if "speaker_id" in payload:
                payload["speaker_name"] = self._seat_name(payload["speaker_id"], seats)
            if "seat_id" in payload:
                payload["seat_name"] = self._seat_name(payload["seat_id"], seats)
            items.append(
                {
                    "seq": index,
                    "event_id": event["event_id"],
                    "channel": event["channel"],
                    "event_type": event["event_type"],
                    "created_at": event["created_at"],
                    "payload": payload,
                }
            )
        return items

    def _seat_name(self, seat_id: str, seats: list[dict[str, Any]]) -> str:
        for seat in seats:
            if seat["seat_id"] == seat_id:
                return str(seat["display_name"])
        return seat_id
