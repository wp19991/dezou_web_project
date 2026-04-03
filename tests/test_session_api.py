from __future__ import annotations


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
    assert len(payload["seats"]) == 6

    state_response = client.get(f"/api/v1/sessions/{payload['session_id']}/state")
    assert state_response.status_code == 200
    state = state_response.json()["data"]
    assert state["phase"] == "waiting_start"
    assert state["session_seed"] == 9876
    assert state["current_hand"] is None
    assert state["last_event_id"] >= 1
