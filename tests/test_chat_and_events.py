from __future__ import annotations


def test_chat_before_and_during_hand_and_events_cursor(client) -> None:
    created = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 2,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 2000,
            "seed": 123,
        },
    ).json()["data"]
    session_id = created["session_id"]

    before = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"speaker_id": "seat_0", "text": "开始前先说一句"},
    )
    assert before.status_code == 201
    assert before.json()["data"]["hand_id"] is None

    start = client.post(
        f"/api/v1/sessions/{session_id}/hands",
        json={"dealer_seat": 0},
    )
    assert start.status_code == 201
    hand_id = start.json()["data"]["current_hand"]["hand_id"]

    during = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"speaker_id": "seat_1", "text": "这手我跟。"},
    )
    assert during.status_code == 201
    assert during.json()["data"]["hand_id"] == hand_id

    events = client.get(f"/api/v1/sessions/{session_id}/events?since_event_id=0&limit=200")
    assert events.status_code == 200
    payload = events.json()["data"]
    assert payload["count"] >= 4
    assert payload["next_since_event_id"] >= payload["events"][-1]["event_id"]
    assert any(item["event_type"] == "chat_sent" for item in payload["events"])
