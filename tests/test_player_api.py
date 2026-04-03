from __future__ import annotations


def create_session_with_names(client, seat_count=2, seat_names=None, seed=1234):
    response = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": seat_count,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 5000,
            "seed": seed,
            "seat_names": seat_names or [f"玩家{i + 1}" for i in range(seat_count)],
        },
    )
    return response


def start_hand(client, session_id: str, dealer_seat: int = 0):
    return client.post(
        f"/api/v1/sessions/{session_id}/hands",
        json={"dealer_seat": dealer_seat},
    )


def test_create_session_with_custom_names(client) -> None:
    response = create_session_with_names(
        client,
        seat_count=3,
        seat_names=["Alice", "Bob", "Carol"],
        seed=999,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert [seat["display_name"] for seat in data["seats"]] == ["Alice", "Bob", "Carol"]

    state = client.get(f"/api/v1/sessions/{data['session_id']}/state?viewer_name=Alice")
    assert state.status_code == 200
    assert state.json()["data"]["viewer"]["viewer_name"] == "Alice"


def test_duplicate_seat_names_rejected(client) -> None:
    response = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Alice"],
    )
    assert response.status_code == 422


def test_unknown_viewer_name_returns_404(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Bob"],
    ).json()["data"]
    response = client.get(f"/api/v1/sessions/{created['session_id']}/state?viewer_name=Carol")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SEAT_NOT_FOUND"


def test_actor_id_and_actor_name_mismatch_returns_422(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Bob"],
    ).json()["data"]
    session_id = created["session_id"]
    start_hand(client, session_id)

    response = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": "seat_0", "actor_name": "Bob", "action": "call"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_viewer_state_hides_other_players_private_cards(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Bob"],
        seed=2024,
    ).json()["data"]
    session_id = created["session_id"]
    start_hand(client, session_id)

    state = client.get(f"/api/v1/sessions/{session_id}/state?viewer_name=Alice")
    assert state.status_code == 200
    payload = state.json()["data"]
    assert payload["viewer"]["viewer_seat_id"] == "seat_0"
    assert payload["viewer"]["is_actor"] is True

    seats = {seat["display_name"]: seat for seat in payload["current_hand"]["seats"]}
    assert len(seats["Alice"]["hole_cards"]) == 2
    assert seats["Alice"]["hole_cards_visible"] is True
    assert seats["Bob"]["hole_cards"] == []
    assert seats["Bob"]["hole_cards_visible"] is False
    assert payload["current_hand"]["turn_order"]
    assert [
        item["display_name"] for item in payload["current_hand"]["turn_order"]
    ] == ["Bob", "Alice"]
    assert payload["current_hand"]["action_history"] == []
    assert payload["current_hand"]["chat_messages"] == []
    assert any(item["event_type"] == "hand_started" for item in payload["current_hand"]["timeline"])


def test_folded_player_cannot_act_but_can_chat_and_cards_hide_from_others(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=3,
        seat_names=["Alice", "Bob", "Carol"],
        seed=2025,
    ).json()["data"]
    session_id = created["session_id"]
    started = start_hand(client, session_id, dealer_seat=0)
    hand = started.json()["data"]["current_hand"]

    first_actor_id = hand["actor_id"]
    fold_response = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": first_actor_id, "action": "fold"},
    )
    assert fold_response.status_code == 200
    assert fold_response.json()["data"]["hand_ended"] is False

    folded_again = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": first_actor_id, "action": "call"},
    )
    assert folded_again.status_code == 409

    chat_response = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"speaker_id": first_actor_id, "text": "我弃牌了，但继续聊。"},
    )
    assert chat_response.status_code == 201

    bob_state = client.get(f"/api/v1/sessions/{session_id}/state?viewer_name=Bob")
    assert bob_state.status_code == 200
    hand_state = bob_state.json()["data"]["current_hand"]
    seats = {seat["seat_id"]: seat for seat in hand_state["seats"]}
    assert seats[first_actor_id]["is_folded"] is True
    assert seats[first_actor_id]["hole_cards"] == []
    assert seats[first_actor_id]["hole_cards_visible"] is False
    assert hand_state["action_history"][0]["actor_id"] == first_actor_id
    assert hand_state["action_history"][0]["action"] == "fold"
    assert hand_state["chat_messages"][0]["text"] == "我弃牌了，但继续聊。"
    assert hand_state["timeline"][-1]["event_type"] == "chat_sent"


def test_player_name_action_and_replay_timeline(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Bob"],
        seed=3030,
    ).json()["data"]
    session_id = created["session_id"]
    start = start_hand(client, session_id, dealer_seat=0)
    hand_id = start.json()["data"]["current_hand"]["hand_id"]

    action = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_name": "Alice", "action": "fold"},
    )
    assert action.status_code == 200
    assert action.json()["data"]["hand_ended"] is True

    chat = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"speaker_name": "Alice", "text": "这手让你了。"},
    )
    assert chat.status_code == 201
    assert chat.json()["data"]["hand_id"] == hand_id

    hands = client.get(f"/api/v1/sessions/{session_id}/hands")
    assert hands.status_code == 200
    assert hands.json()["data"]["items"][0]["chat_count"] == 1

    replay = client.get(f"/api/v1/replays/{hand_id}?viewer_name=Bob")
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert replay_data["timeline"]
    assert [item["created_at"] for item in replay_data["timeline"]] == sorted(
        item["created_at"] for item in replay_data["timeline"]
    )
    assert any(item["event_type"] == "action_applied" for item in replay_data["timeline"])
    assert any(item["event_type"] == "chat_sent" for item in replay_data["timeline"])

    final_seats = {seat["display_name"]: seat for seat in replay_data["final_state"]["seats"]}
    assert final_seats["Alice"]["hole_cards"] == []
    assert final_seats["Alice"]["hole_cards_visible"] is False
    assert len(final_seats["Bob"]["hole_cards"]) == 2
    assert replay_data["chat_messages"][0]["text"] == "这手让你了。"


def test_state_history_resets_when_next_hand_starts(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=3,
        seat_names=["Alice", "Bob", "Carol"],
        seed=4040,
    ).json()["data"]
    session_id = created["session_id"]

    first_hand = start_hand(client, session_id, dealer_seat=0).json()["data"]["current_hand"]
    first_hand_id = first_hand["hand_id"]
    first_actor_id = first_hand["actor_id"]

    folded = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": first_actor_id, "action": "fold"},
    )
    assert folded.status_code == 200

    chat = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"speaker_name": "Alice", "text": "第一手我先弃了。"},
    )
    assert chat.status_code == 201

    state_after_first = client.get(f"/api/v1/sessions/{session_id}/state?viewer_name=Bob")
    assert state_after_first.status_code == 200
    first_current = state_after_first.json()["data"]["current_hand"]
    assert first_current["hand_id"] == first_hand_id
    assert len(first_current["action_history"]) == 1
    assert len(first_current["chat_messages"]) == 1
    assert any(item["event_type"] == "chat_sent" for item in first_current["timeline"])

    second_state = state_after_first.json()["data"]
    while second_state["phase"] != "hand_ended":
        actor_id = second_state["current_hand"]["actor_id"]
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={"actor_id": actor_id, "action": "fold"},
        )
        assert response.status_code == 200
        second_state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]

    next_hand = start_hand(client, session_id, dealer_seat=1)
    assert next_hand.status_code == 201

    refreshed = client.get(f"/api/v1/sessions/{session_id}/state?viewer_name=Bob")
    assert refreshed.status_code == 200
    current_hand = refreshed.json()["data"]["current_hand"]
    assert current_hand["hand_id"] != first_hand_id
    assert current_hand["hand_no"] == 2
    assert current_hand["action_history"] == []
    assert current_hand["chat_messages"] == []
    assert all(item["event_type"] != "chat_sent" for item in current_hand["timeline"])
    assert current_hand["timeline"][0]["event_type"] == "hand_started"


def test_replay_without_viewer_hides_non_showdown_cards(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Bob"],
        seed=5050,
    ).json()["data"]
    session_id = created["session_id"]
    hand = start_hand(client, session_id, dealer_seat=0).json()["data"]["current_hand"]
    hand_id = hand["hand_id"]

    action = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_name": "Alice", "action": "fold"},
    )
    assert action.status_code == 200
    assert action.json()["data"]["hand_ended"] is True

    replay = client.get(f"/api/v1/replays/{hand_id}")
    assert replay.status_code == 200
    seats = {seat["display_name"]: seat for seat in replay.json()["data"]["final_state"]["seats"]}
    assert seats["Alice"]["hole_cards"] == []
    assert seats["Alice"]["hole_cards_visible"] is False
    assert seats["Bob"]["hole_cards"] == []
    assert seats["Bob"]["hole_cards_visible"] is False


def test_public_replay_after_showdown_reveals_only_showdown_cards(client) -> None:
    created = create_session_with_names(
        client,
        seat_count=2,
        seat_names=["Alice", "Bob"],
        seed=6060,
    ).json()["data"]
    session_id = created["session_id"]
    hand_id = start_hand(
        client,
        session_id,
        dealer_seat=0,
    ).json()["data"]["current_hand"]["hand_id"]

    first_state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    first_actor_id = first_state["current_hand"]["actor_id"]
    first_action = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": first_actor_id, "action": "all_in"},
    )
    assert first_action.status_code == 200

    second_state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    second_actor_id = second_state["current_hand"]["actor_id"]
    second_action = client.post(
        f"/api/v1/sessions/{session_id}/actions",
        json={"actor_id": second_actor_id, "action": "call"},
    )
    assert second_action.status_code == 200
    assert second_action.json()["data"]["hand_ended"] is True

    replay = client.get(f"/api/v1/replays/{hand_id}")
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    seats = replay_data["final_state"]["seats"]
    assert replay_data["final_state"]["showdown_seat_ids"]
    assert all(seat["hole_cards_visible"] for seat in seats)
    assert all(len(seat["hole_cards"]) == 2 for seat in seats)
