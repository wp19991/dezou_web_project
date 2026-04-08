from __future__ import annotations

from sqlalchemy import text


def test_create_session_and_state(client) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 6,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 10000,
            "seed": 9876,
        },
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["phase"] == "waiting_start"
    assert payload["seat_count"] == 6
    assert payload["session_seed"] == 9876
    assert payload["user_participates"] is False
    assert len(payload["seats"]) == 6

    state_response = client.get(f"/api/v1/sessions/{payload['session_id']}/state")
    assert state_response.status_code == 200
    state = state_response.json()["data"]
    assert state["phase"] == "waiting_start"
    assert state["session_seed"] == 9876
    assert state["user_participates"] is False
    assert state["current_hand"] is None
    assert state["last_event_id"] >= 1


def test_create_participant_session_and_state(client) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 4,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 10000,
            "seed": 321,
            "user_participates": True,
            "seat_names": ["玩家", "阿岚", "老岩", "唐梨"],
        },
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["user_participates"] is True
    assert payload["seats"][0]["display_name"] == "玩家"

    state_response = client.get(f"/api/v1/sessions/{payload['session_id']}/state?viewer_name=玩家")
    assert state_response.status_code == 200
    state = state_response.json()["data"]
    assert state["user_participates"] is True
    assert state["viewer"]["viewer_name"] == "玩家"


def test_start_hand_blocks_when_participant_user_has_no_chips(client) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 3,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 10000,
            "seed": 777,
            "user_participates": True,
            "seat_names": ["玩家", "阿岚", "老岩"],
        },
    )
    assert response.status_code == 201
    session_id = response.json()["data"]["session_id"]

    engine = client.app.state.poker_service.store.engine
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE session_seats
                SET stack = 0
                WHERE session_id = :session_id
                  AND seat_id = 'seat_0'
                """
            ),
            {"session_id": session_id},
        )

    started = client.post(f"/api/v1/sessions/{session_id}/hands", json={})
    assert started.status_code == 409
    error = started.json()["error"]
    assert error["code"] == "USER_OUT_OF_CHIPS"
    assert "无法开始新一手" in error["message"]


def test_start_hand_skips_other_busted_players(client) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 3,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 10000,
            "seed": 888,
            "user_participates": True,
            "seat_names": ["玩家", "阿岚", "老岩"],
        },
    )
    assert response.status_code == 201
    session_id = response.json()["data"]["session_id"]

    engine = client.app.state.poker_service.store.engine
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE session_seats
                SET stack = 0
                WHERE session_id = :session_id
                  AND seat_id = 'seat_1'
                """
            ),
            {"session_id": session_id},
        )

    started = client.post(f"/api/v1/sessions/{session_id}/hands", json={"dealer_seat": 0})
    assert started.status_code == 201
    hand = started.json()["data"]["current_hand"]

    assert hand["dealer_seat"] == 0
    assert hand["small_blind_seat"] == 0
    assert hand["big_blind_seat"] == 2
    assert hand["actor_id"] == "seat_0"
    assert [seat["seat_id"] for seat in hand["seats"]] == ["seat_0", "seat_2"]
