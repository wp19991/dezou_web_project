from __future__ import annotations


def create_started_heads_up(client):
    response = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 2,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 2000,
            "seed": 123,
        },
    )
    session_id = response.json()["data"]["session_id"]
    client.post(
        f"/api/v1/sessions/{session_id}/hands",
        json={"dealer_seat": 0},
    )
    return session_id


def test_heads_up_turn_order_and_actor_mismatch(client) -> None:
    session_id = create_started_heads_up(client)
    state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    assert state["current_hand"]["small_blind_seat"] == 0
    assert state["current_hand"]["big_blind_seat"] == 1
    assert state["current_hand"]["actor_id"] == "seat_0"
    assert state["session_seed"] == 123
    assert state["current_hand"]["seed"] == 123

    mismatch = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": "seat_1", "action": "call"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "ACTOR_TURN_MISMATCH"


def test_invalid_raise_amount_returns_409(client) -> None:
    session_id = create_started_heads_up(client)
    response = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": "seat_0", "action": "raise", "amount": 150},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AMOUNT_OUT_OF_RANGE"


def test_all_in_flow_generates_history_and_replay(client) -> None:
    session_id = create_started_heads_up(client)
    state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    actor_id = state["current_hand"]["actor_id"]

    first = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": actor_id, "action": "all_in"},
    )
    assert first.status_code == 200
    assert first.json()["data"]["phase"] == "waiting_actor_action"

    state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    second_actor = state["current_hand"]["actor_id"]
    second = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": second_actor, "action": "call"},
    )
    assert second.status_code == 200
    assert second.json()["data"]["phase"] == "hand_ended"
    assert second.json()["data"]["hand_ended"] is True

    final_state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    hand_id = final_state["current_hand"]["hand_id"]
    assert final_state["phase"] == "hand_ended"
    assert len(final_state["current_hand"]["board_cards"]) == 5
    assert final_state["current_hand"]["winners"]
    assert final_state["current_hand"]["showdown_seat_ids"]
    assert any(seat["showdown_competing"] for seat in final_state["current_hand"]["seats"])

    replay = client.get(f"/api/v1/replays/{hand_id}")
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["hand_id"] == hand_id
    assert replay_data["session_seed"] == 123
    assert len(replay_data["actions"]) == 2
    assert replay_data["actions"][0]["action"] == "all_in"
    assert replay_data["actions"][1]["action"] == "call"
    assert any(seat["showdown_competing"] for seat in replay_data["final_state"]["seats"])

    hands = client.get(f"/api/v1/sessions/{session_id}/hands")
    assert hands.status_code == 200
    items = hands.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["hand_id"] == hand_id
    assert items[0]["action_count"] == 2
    assert items[0]["winners"]

def test_request_id_persists_start_hand_and_action(client) -> None:
    created = client.post(
        "/api/v1/sessions",
        json={
            "session_id": "request-id-session",
            "request_id": "create-1",
            "seat_count": 2,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 2000,
            "seed": 456,
            "seat_names": ["Alice", "Bob"],
        },
    )
    assert created.status_code == 201
    session_id = created.json()["data"]["session_id"]

    started = client.post(
        f"/api/v1/sessions/{session_id}/hands",
        json={"dealer_seat": 0, "request_id": "start-1"},
    )
    assert started.status_code == 201
    hand_id = started.json()["data"]["current_hand"]["hand_id"]

    state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    actor_id = state["current_hand"]["actor_id"]
    first_action = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": actor_id, "action": "call", "request_id": "action-1"},
    )
    assert first_action.status_code == 200
    assert first_action.json()["data"]["accepted"] is True

    repeated_start = client.post(
        f"/api/v1/sessions/{session_id}/hands",
        json={"dealer_seat": 0, "request_id": "start-1"},
    )
    assert repeated_start.status_code == 201
    assert repeated_start.json() == started.json()

    repeated_action = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": actor_id, "action": "call", "request_id": "action-1"},
    )
    assert repeated_action.status_code == 200
    assert repeated_action.json() == first_action.json()

    events = client.get(f"/api/v1/sessions/{session_id}/events?since_event_id=0&limit=50")
    assert events.status_code == 200
    event_types = [item["event_type"] for item in events.json()["data"]["events"]]
    assert "action_applied" in event_types

    hands = client.get(f"/api/v1/sessions/{session_id}/hands")
    assert hands.status_code == 200
    assert hands.json()["data"]["items"][0]["hand_id"] == hand_id
