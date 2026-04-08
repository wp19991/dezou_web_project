from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from random import Random
from typing import Any

from pokerkit import Automation, Mode, NoLimitTexasHoldem, StandardHighHand

from app.core.errors import AppError
from app.core.utils import generate_hand_id, to_iso

AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.CARD_BURNING,
    Automation.BOARD_DEALING,
    Automation.RUNOUT_COUNT_SELECTION,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


@dataclass(slots=True)
class SeatRuntimeState:
    seat_id: str
    seat_no: int
    display_name: str
    player_index: int
    stack_start: int
    current_stack: int
    stack_end: int | None = None
    hole_cards: list[str] = field(default_factory=list)
    in_hand: bool = True
    is_folded: bool = False
    is_all_in: bool = False
    contribution_total: int = 0
    contribution_street: int = 0
    win_amount: int = 0
    showdown_competing: bool = False
    best_hand_label: str | None = None
    best_hand_cards: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HandRuntime:
    session_id: str
    hand_id: str
    hand_no: int
    session_seed: int
    seed: int
    dealer_seat: int
    small_blind_seat: int
    big_blind_seat: int
    started_at: str
    seat_order: list[int]
    state: Any
    seat_by_id: dict[str, SeatRuntimeState]
    seat_by_player: dict[int, SeatRuntimeState]
    board_cards: list[str] = field(default_factory=list)
    street: str = "preflop"
    actor_id: str | None = None
    phase: str = "running"
    ended_at: str | None = None
    operation_cursor: int = 0
    winners: dict[str, int] = field(default_factory=dict)
    action_count: int = 0
    showdown_started: bool = False


class TableKernel:
    def restore_hand(
        self,
        session_row: dict[str, Any],
        hand_seats: list[dict[str, Any]],
        hand_row: dict[str, Any],
        hand_events: list[dict[str, Any]],
    ) -> HandRuntime:
        restored_seats = [
            {
                "seat_id": seat["seat_id"],
                "seat_no": int(seat["seat_no"]),
                "display_name": seat["display_name"],
                "stack": int(seat["stack_start"]),
            }
            for seat in hand_seats
        ]
        runtime, _ = self.start_hand(
            session_row,
            restored_seats,
            int(hand_row["hand_no"]),
            int(hand_row["seed"]),
            int(hand_row["dealer_seat"]),
        )
        runtime.hand_id = str(hand_row["hand_id"])
        runtime.started_at = str(hand_row["started_at"])
        runtime.ended_at = hand_row["ended_at"]

        action_events = [
            event for event in hand_events if event["event_type"] == "action_applied"
        ]
        for event in action_events:
            payload = event["payload"]
            self.apply_action(
                runtime,
                str(payload["actor_id"]),
                str(payload["action"]),
                payload.get("amount"),
            )

        runtime.hand_id = str(hand_row["hand_id"])
        runtime.started_at = str(hand_row["started_at"])
        runtime.ended_at = hand_row["ended_at"]
        return runtime

    def start_hand(
        self,
        session_row: dict[str, Any],
        session_seats: list[dict[str, Any]],
        hand_no: int,
        seed: int,
        dealer_seat: int,
    ) -> tuple[HandRuntime, list[dict[str, Any]]]:
        started_at = to_iso()
        seat_count = len(session_seats)
        if seat_count < 2:
            raise AppError(
                "NOT_ENOUGH_ACTIVE_SEATS",
                "筹码足够参与本手的玩家不足 2 人，无法开局",
                409,
                {"active_seat_count": seat_count},
            )
        seat_order = self._rotate_seats([seat["seat_no"] for seat in session_seats], dealer_seat)
        stacks = tuple(
            next(self._seat_stack(seat) for seat in session_seats if seat["seat_no"] == seat_no)
            for seat_no in seat_order
        )
        if any(stack <= 0 for stack in stacks):
            raise AppError(
                "INVALID_HAND_PARTICIPANTS",
                "本手参与玩家的筹码必须大于 0",
                409,
                {"stacks": list(stacks)},
            )
        state = NoLimitTexasHoldem.create_state(
            AUTOMATIONS,
            False,
            0,
            {0: session_row["small_blind"], 1: session_row["big_blind"]},
            session_row["big_blind"],
            stacks,
            seat_count,
            mode=Mode.CASH_GAME,
        )
        deck_cards = list(state.deck)
        Random(seed).shuffle(deck_cards)
        state.deck_cards = deque(deck_cards)

        seat_by_id: dict[str, SeatRuntimeState] = {}
        seat_by_player: dict[int, SeatRuntimeState] = {}
        for player_index, seat_no in enumerate(seat_order):
            seat_row = next(item for item in session_seats if item["seat_no"] == seat_no)
            tracker = SeatRuntimeState(
                seat_id=seat_row["seat_id"],
                seat_no=seat_row["seat_no"],
                display_name=seat_row["display_name"],
                player_index=player_index,
                stack_start=self._seat_stack(seat_row),
                current_stack=self._seat_stack(seat_row),
            )
            seat_by_id[tracker.seat_id] = tracker
            seat_by_player[player_index] = tracker

        if seat_count == 2:
            small_blind_seat = dealer_seat
            big_blind_seat = seat_order[0]
        else:
            small_blind_seat = seat_order[0]
            big_blind_seat = seat_order[1]

        runtime = HandRuntime(
            session_id=session_row["session_id"],
            hand_id=generate_hand_id(session_row["session_id"], hand_no, started_at),
            hand_no=hand_no,
            session_seed=int(session_row["rng_seed"]),
            seed=seed,
            dealer_seat=dealer_seat,
            small_blind_seat=small_blind_seat,
            big_blind_seat=big_blind_seat,
            started_at=started_at,
            seat_order=seat_order,
            state=state,
            seat_by_id=seat_by_id,
            seat_by_player=seat_by_player,
        )

        events = [
            self._event(
                runtime,
                "system",
                "hand_started",
                {
                    "hand_id": runtime.hand_id,
                    "hand_no": runtime.hand_no,
                    "dealer_seat": runtime.dealer_seat,
                    "small_blind_seat": runtime.small_blind_seat,
                    "big_blind_seat": runtime.big_blind_seat,
                    "session_seed": runtime.session_seed,
                    "seed": runtime.seed,
                },
            )
        ]
        events.extend(self._drain_operations(runtime))
        for _ in range(seat_count * 2):
            runtime.state.deal_hole()
        events.extend(self._drain_operations(runtime))
        events.extend(self.advance(runtime))
        return runtime, events

    def apply_action(
        self,
        runtime: HandRuntime,
        actor_id: str,
        action: str,
        amount: int | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        if runtime.phase == "ended":
            raise AppError("SESSION_PHASE_INVALID", "本手已结束，请开始下一手", 409)
        if runtime.actor_id != actor_id:
            raise AppError(
                "ACTOR_TURN_MISMATCH",
                "当前不是该玩家行动回合",
                409,
                {"expected_actor_id": runtime.actor_id, "actual_actor_id": actor_id},
            )
        if actor_id not in runtime.seat_by_id:
            raise AppError("SEAT_NOT_FOUND", "seat 不存在", 404)

        actor = runtime.seat_by_id[actor_id]
        available = {item["action"]: item for item in self.available_actions(runtime)}
        if action not in available:
            raise AppError("ACTION_NOT_ALLOWED", "当前动作不合法", 409)

        state = runtime.state
        action_street = runtime.street
        normalized_amount: int | None = None
        current_bet = int(state.bets[actor.player_index])
        max_bet = int(max(state.bets))
        remaining_stack = int(state.stacks[actor.player_index])
        to_call = max_bet - current_bet

        if action in {"bet", "raise"}:
            if amount is None:
                raise AppError("INVALID_REQUEST", "下注或加注必须提供 amount", 422)
            bounds = available[action]
            if amount < int(bounds["min"]) or amount > int(bounds["max"]):
                raise AppError(
                    "AMOUNT_OUT_OF_RANGE",
                    "金额超出允许范围",
                    409,
                    {"min": bounds["min"], "max": bounds["max"], "amount": amount},
                )
            normalized_amount = amount
            state.complete_bet_or_raise_to(normalized_amount)
        elif action == "all_in":
            normalized_amount = current_bet + int(state.stacks[actor.player_index])
            if normalized_amount <= max_bet:
                state.check_or_call()
            else:
                state.complete_bet_or_raise_to(normalized_amount)
        elif action == "call":
            normalized_amount = current_bet + min(to_call, remaining_stack)
            state.check_or_call()
        elif action == "check":
            state.check_or_call()
        elif action == "fold":
            state.fold()
        else:
            raise AppError("ACTION_NOT_ALLOWED", "当前动作不合法", 409)

        runtime.action_count += 1
        events = self._drain_operations(runtime)
        applied_action = {
            "actor_id": actor_id,
            "street": action_street,
            "action": action,
            "amount": normalized_amount,
        }
        events.append(self._event(runtime, "action", "action_applied", applied_action))
        events.append(
            self._event(
                runtime,
                "action",
                {
                    "fold": "folded",
                    "check": "checked",
                    "call": "called",
                    "bet": "bet_to",
                    "raise": "raised_to",
                    "all_in": "all_in",
                }[action],
                applied_action,
            )
        )
        events.extend(self.advance(runtime))
        return applied_action, events, runtime.phase == "ended"

    def advance(self, runtime: HandRuntime) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            if not runtime.state.status:
                break
            if runtime.state.actor_index is not None:
                runtime.actor_id = runtime.seat_by_player[runtime.state.actor_index].seat_id
                runtime.phase = "running"
                events.append(
                    self._event(
                        runtime,
                        "system",
                        "waiting_actor_action",
                        {
                            "actor_id": runtime.actor_id,
                            "street": runtime.street,
                            "to_call": self.to_call(runtime),
                        },
                    )
                )
                break

            if runtime.state.can_collect_bets():
                runtime.state.collect_bets()
            elif runtime.state.can_show_or_muck_hole_cards():
                runtime.state.show_or_muck_hole_cards()
            elif runtime.state.can_burn_card():
                runtime.state.burn_card()
            elif runtime.state.can_deal_board():
                runtime.state.deal_board()
            elif runtime.state.can_kill_hand():
                runtime.state.kill_hand()
            elif runtime.state.can_push_chips():
                runtime.state.push_chips()
            elif runtime.state.can_pull_chips():
                runtime.state.pull_chips()
            elif runtime.state.can_no_operate():
                runtime.state.no_operate()
            else:
                break
            events.extend(self._drain_operations(runtime))

        if not runtime.state.status:
            runtime.phase = "ended"
            runtime.actor_id = None
            runtime.ended_at = runtime.ended_at or to_iso()
            for tracker in runtime.seat_by_id.values():
                tracker.current_stack = int(runtime.state.stacks[tracker.player_index])
                tracker.stack_end = tracker.current_stack
            self._populate_showdown_details(runtime)
            events.append(
                self._event(
                    runtime,
                    "system",
                    "hand_ended",
                    {
                        "hand_id": runtime.hand_id,
                        "winners": [
                            {"seat_id": seat_id, "win_amount": amount}
                            for seat_id, amount in sorted(runtime.winners.items())
                        ],
                        "showdown_seat_ids": self.showdown_seat_ids(runtime),
                        "pot_total": self.pot_total(runtime),
                        "final_stacks": self.final_stacks(runtime),
                    },
                )
            )
        return events

    def available_actions(self, runtime: HandRuntime) -> list[dict[str, Any]]:
        state = runtime.state
        if runtime.phase == "ended" or state.actor_index is None:
            return []
        actor_index = state.actor_index
        max_bet = int(max(state.bets))
        to_call = max_bet - int(state.bets[actor_index])
        actions: list[dict[str, Any]] = []
        if state.can_fold():
            actions.append(self._action("fold"))
        if state.can_check_or_call():
            actions.append(self._action("check" if to_call == 0 else "call"))
        if state.can_complete_bet_or_raise_to():
            minimum = int(state.min_completion_betting_or_raising_to_amount)
            maximum = int(state.max_completion_betting_or_raising_to_amount)
            if max_bet == 0:
                actions.append(self._action("bet", "bet_to", minimum, maximum, minimum))
            else:
                actions.append(self._action("raise", "raise_to", minimum, maximum, minimum))
        if int(state.stacks[actor_index]) > 0:
            actions.append(self._action("all_in"))
        return actions

    def current_hand_state(self, runtime: HandRuntime) -> dict[str, Any]:
        state = runtime.state
        current_hand: dict[str, Any] = {
            "hand_id": runtime.hand_id,
            "hand_no": runtime.hand_no,
            "session_seed": runtime.session_seed,
            "seed": runtime.seed,
            "street": runtime.street,
            "dealer_seat": runtime.dealer_seat,
            "small_blind_seat": runtime.small_blind_seat,
            "big_blind_seat": runtime.big_blind_seat,
            "actor_id": runtime.actor_id,
            "to_call": None,
            "min_bet_to": None,
            "min_raise_to": None,
            "pot_total": self.pot_total(runtime),
            "board_cards": list(runtime.board_cards),
            "showdown_started": runtime.showdown_started,
            "showdown_seat_ids": self.showdown_seat_ids(runtime),
            "winners": [
                {"seat_id": seat_id, "win_amount": amount}
                for seat_id, amount in sorted(runtime.winners.items())
            ],
            "seats": [],
            "available_actions": self.available_actions(runtime),
        }
        if runtime.actor_id is not None and state.can_complete_bet_or_raise_to():
            minimum = int(state.min_completion_betting_or_raising_to_amount)
            current_hand["to_call"] = self.to_call(runtime)
            if int(max(state.bets)) == 0:
                current_hand["min_bet_to"] = minimum
            else:
                current_hand["min_raise_to"] = minimum
        elif runtime.actor_id is not None:
            current_hand["to_call"] = self.to_call(runtime)

        for tracker in sorted(runtime.seat_by_id.values(), key=lambda item: item.seat_no):
            current_hand["seats"].append(
                {
                    "seat_id": tracker.seat_id,
                    "seat_no": tracker.seat_no,
                    "display_name": tracker.display_name,
                    "stack": tracker.current_stack,
                    "stack_start": tracker.stack_start,
                    "contribution_total": tracker.contribution_total,
                    "contribution_street": tracker.contribution_street,
                    "is_folded": tracker.is_folded,
                    "is_all_in": tracker.is_all_in,
                    "in_hand": tracker.in_hand,
                    "hole_cards": list(tracker.hole_cards),
                    "hole_cards_visible": True,
                    "showdown_competing": tracker.showdown_competing,
                    "best_hand_label": tracker.best_hand_label,
                    "best_hand_cards": list(tracker.best_hand_cards),
                    "is_winner": tracker.win_amount > 0,
                    "win_amount": tracker.win_amount,
                }
            )
        return current_hand

    def hand_row(self, runtime: HandRuntime) -> dict[str, Any]:
        return {
            "hand_id": runtime.hand_id,
            "session_id": runtime.session_id,
            "hand_no": runtime.hand_no,
            "session_seed": runtime.session_seed,
            "seed": runtime.seed,
            "dealer_seat": runtime.dealer_seat,
            "small_blind_seat": runtime.small_blind_seat,
            "big_blind_seat": runtime.big_blind_seat,
            "phase": "ended" if runtime.phase == "ended" else "running",
            "street": runtime.street,
            "board_cards_json": self._json(runtime.board_cards),
            "pot_total": self.pot_total(runtime),
            "actor_id": runtime.actor_id,
            "started_at": runtime.started_at,
            "ended_at": runtime.ended_at,
        }

    def hand_seat_rows(self, runtime: HandRuntime) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for tracker in runtime.seat_by_id.values():
            rows.append(
                {
                    "hand_id": runtime.hand_id,
                    "seat_id": tracker.seat_id,
                    "seat_no": tracker.seat_no,
                    "display_name": tracker.display_name,
                    "hole_cards_json": self._json(tracker.hole_cards),
                    "stack_start": tracker.stack_start,
                    "stack_end": tracker.stack_end,
                    "in_hand": int(tracker.in_hand),
                    "is_folded": int(tracker.is_folded),
                    "is_all_in": int(tracker.is_all_in),
                    "contribution_total": tracker.contribution_total,
                    "contribution_street": tracker.contribution_street,
                }
            )
        return rows

    def final_stacks(self, runtime: HandRuntime) -> dict[str, int]:
        return {
            tracker.seat_id: (
                tracker.stack_end if tracker.stack_end is not None else tracker.current_stack
            )
            for tracker in sorted(runtime.seat_by_id.values(), key=lambda item: item.seat_no)
        }

    def replay_final_state(self, runtime: HandRuntime) -> dict[str, Any]:
        return {
            "hand_id": runtime.hand_id,
            "session_id": runtime.session_id,
            "hand_no": runtime.hand_no,
            "session_seed": runtime.session_seed,
            "seed": runtime.seed,
            "dealer_seat": runtime.dealer_seat,
            "small_blind_seat": runtime.small_blind_seat,
            "big_blind_seat": runtime.big_blind_seat,
            "board_cards": list(runtime.board_cards),
            "pot_total": self.pot_total(runtime),
            "showdown_seat_ids": self.showdown_seat_ids(runtime),
            "winners": [
                {"seat_id": seat_id, "win_amount": amount}
                for seat_id, amount in sorted(runtime.winners.items())
            ],
            "final_stacks": self.final_stacks(runtime),
            "seats": self.current_hand_state(runtime)["seats"],
        }

    def summary(self, runtime: HandRuntime, chat_count: int) -> dict[str, Any]:
        return {
            "hand_id": runtime.hand_id,
            "session_id": runtime.session_id,
            "hand_no": runtime.hand_no,
            "phase": "ended" if runtime.phase == "ended" else "running",
            "dealer_seat": runtime.dealer_seat,
            "winner_ids": [seat_id for seat_id, _ in sorted(runtime.winners.items())],
            "winners": [
                {"seat_id": seat_id, "win_amount": amount}
                for seat_id, amount in sorted(runtime.winners.items())
            ],
            "pot_total": self.pot_total(runtime),
            "action_count": runtime.action_count,
            "chat_count": chat_count,
            "started_at": runtime.started_at,
            "ended_at": runtime.ended_at,
        }

    def to_call(self, runtime: HandRuntime) -> int | None:
        if runtime.state.actor_index is None:
            return None
        return int(max(runtime.state.bets) - runtime.state.bets[runtime.state.actor_index])

    def _drain_operations(self, runtime: HandRuntime) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        operations = runtime.state.operations[runtime.operation_cursor :]
        if not operations:
            return events

        for operation in operations:
            name = operation.__class__.__name__
            if name == "BlindOrStraddlePosting":
                tracker = runtime.seat_by_player[operation.player_index]
                tracker.contribution_total += int(operation.amount)
                tracker.contribution_street += int(operation.amount)
                events.append(
                    self._event(
                        runtime,
                        "action",
                        "blind_posted",
                        {"actor_id": tracker.seat_id, "amount": int(operation.amount)},
                    )
                )
            elif name == "HoleDealing":
                tracker = runtime.seat_by_player[operation.player_index]
                tracker.hole_cards.extend(repr(card) for card in operation.cards)
            elif name == "CheckingOrCalling":
                tracker = runtime.seat_by_player[operation.player_index]
                tracker.contribution_total += int(operation.amount)
                tracker.contribution_street += int(operation.amount)
            elif name == "CompletionBettingOrRaisingTo":
                tracker = runtime.seat_by_player[operation.player_index]
                target = int(operation.amount)
                delta = max(0, target - tracker.contribution_street)
                tracker.contribution_total += delta
                tracker.contribution_street = target
            elif name == "BetCollection":
                for tracker in runtime.seat_by_id.values():
                    tracker.contribution_street = 0
            elif name == "Folding":
                tracker = runtime.seat_by_player[operation.player_index]
                tracker.is_folded = True
                tracker.in_hand = False
            elif name == "BoardDealing":
                new_cards = [repr(card) for card in operation.cards]
                runtime.board_cards.extend(new_cards)
                runtime.street = self._street_from_board(runtime.board_cards)
                events.append(
                    self._event(
                        runtime,
                        "system",
                        "board_dealt",
                        {"street": runtime.street, "cards": new_cards},
                    )
                )
                events.append(
                    self._event(
                        runtime,
                        "system",
                        "street_changed",
                        {"street": runtime.street, "board_cards": list(runtime.board_cards)},
                    )
                )
            elif name == "HoleCardsShowingOrMucking" and not runtime.showdown_started:
                runtime.showdown_started = True
                runtime.street = "showdown"
                events.append(
                    self._event(
                        runtime,
                        "system",
                        "showdown_started",
                        {"street": "showdown", "board_cards": list(runtime.board_cards)},
                    )
                )
            elif name == "HandKilling":
                tracker = runtime.seat_by_player[operation.player_index]
                tracker.in_hand = False
            elif name == "ChipsPushing":
                for index, amount in enumerate(operation.amounts):
                    amount_int = int(amount)
                    if amount_int <= 0:
                        continue
                    tracker = runtime.seat_by_player[index]
                    tracker.win_amount += amount_int
                    runtime.winners[tracker.seat_id] = (
                        runtime.winners.get(tracker.seat_id, 0) + amount_int
                    )
                    events.append(
                        self._event(
                            runtime,
                            "action",
                            "pot_awarded",
                            {
                                "seat_id": tracker.seat_id,
                                "amount": amount_int,
                                "pot_index": operation.pot_index,
                            },
                        )
                    )

        runtime.operation_cursor = len(runtime.state.operations)
        for tracker in runtime.seat_by_id.values():
            tracker.current_stack = int(runtime.state.stacks[tracker.player_index])
            tracker.is_all_in = (
                tracker.current_stack == 0
                and not tracker.is_folded
                and (runtime.phase != "ended" or tracker.win_amount == 0)
            )
        return events

    def _rotate_seats(self, seat_numbers: list[int], dealer_seat: int) -> list[int]:
        ordered = sorted(seat_numbers)
        if dealer_seat not in ordered:
            raise AppError("SEAT_NOT_FOUND", "dealer seat 不存在", 404)
        pivot = ordered.index(dealer_seat)
        return ordered[pivot + 1 :] + ordered[: pivot + 1]

    def _seat_stack(self, seat: dict[str, Any]) -> int:
        if "stack" in seat and seat["stack"] is not None:
            return int(seat["stack"])
        return int(seat["stack_start"])

    def _action(
        self,
        action: str,
        amount_type: str | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> dict[str, Any]:
        return {
            "action": action,
            "amount_type": amount_type,
            "min": minimum,
            "max": maximum,
            "default": default,
            "enabled": True,
        }

    def _event(
        self,
        runtime: HandRuntime,
        channel: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "session_id": runtime.session_id,
            "hand_id": runtime.hand_id,
            "channel": channel,
            "event_type": event_type,
            "payload": payload,
            "created_at": to_iso(),
        }

    def _json(self, value: Any) -> str:
        import json

        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _street_from_board(self, board_cards: list[str]) -> str:
        count = len(board_cards)
        if count == 0:
            return "preflop"
        if count == 3:
            return "flop"
        if count == 4:
            return "turn"
        if count >= 5:
            return "river"
        return "preflop"

    def pot_total(self, runtime: HandRuntime) -> int:
        return sum(tracker.contribution_total for tracker in runtime.seat_by_id.values())

    def showdown_seat_ids(self, runtime: HandRuntime) -> list[str]:
        return [
            tracker.seat_id
            for tracker in sorted(runtime.seat_by_id.values(), key=lambda item: item.seat_no)
            if tracker.showdown_competing
        ]

    def _populate_showdown_details(self, runtime: HandRuntime) -> None:
        if not runtime.showdown_started or len(runtime.board_cards) < 5:
            return

        for tracker in runtime.seat_by_id.values():
            tracker.showdown_competing = False
            tracker.best_hand_label = None
            tracker.best_hand_cards = []

        for tracker in runtime.seat_by_id.values():
            if tracker.is_folded or not tracker.hole_cards:
                continue
            hand = StandardHighHand.from_game(
                "".join(tracker.hole_cards),
                "".join(runtime.board_cards),
            )
            tracker.showdown_competing = True
            tracker.best_hand_label = self._translate_hand_label(hand.entry.label.value)
            tracker.best_hand_cards = [repr(card) for card in hand.cards]

    def _translate_hand_label(self, label: str) -> str:
        return {
            "High card": "高牌",
            "One pair": "一对",
            "Two pair": "两对",
            "Three of a kind": "三条",
            "Straight": "顺子",
            "Flush": "同花",
            "Full house": "葫芦",
            "Four of a kind": "四条",
            "Straight flush": "同花顺",
        }.get(label, label)
