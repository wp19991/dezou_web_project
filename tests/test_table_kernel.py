from __future__ import annotations

from app.engine.table_kernel import TableKernel


def test_kernel_heads_up_mapping_and_runout() -> None:
    kernel = TableKernel()
    session_row = {
        "session_id": "kernel-demo",
        "seat_count": 2,
        "small_blind": 50,
        "big_blind": 100,
        "starting_stack": 2000,
        "rng_seed": 123,
        "next_dealer_seat": 0,
    }
    session_seats = [
        {"seat_id": "seat_0", "seat_no": 0, "display_name": "玩家1", "stack": 2000},
        {"seat_id": "seat_1", "seat_no": 1, "display_name": "玩家2", "stack": 2000},
    ]

    runtime, _ = kernel.start_hand(session_row, session_seats, hand_no=1, seed=123, dealer_seat=0)
    assert runtime.small_blind_seat == 0
    assert runtime.big_blind_seat == 1
    assert runtime.actor_id == "seat_0"
    assert runtime.session_seed == 123

    kernel.apply_action(runtime, "seat_0", "all_in", None)
    _, _, ended = kernel.apply_action(runtime, "seat_1", "call", None)
    assert ended is True
    assert runtime.phase == "ended"
    assert len(runtime.board_cards) == 5
    assert sum(runtime.winners.values()) == 4000
