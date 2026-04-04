from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".test_artifacts"
ARTIFACTS.mkdir(exist_ok=True)


def test_running_hand_can_resume_after_restart() -> None:
    db_path = ARTIFACTS / f"resume-{uuid4().hex}.db"
    settings = Settings(
        project_root=ROOT,
        db_path=db_path,
        db_url=f"sqlite+pysqlite:///{db_path.as_posix()}",
        schema_path=ROOT / "poker_table_sqlite_schema.sql",
    )

    app = create_app(settings)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/sessions",
            json={
                "session_id": "resume-table",
                "seat_count": 3,
                "small_blind": 50,
                "big_blind": 100,
                "starting_stack": 5000,
                "seed": 20260404,
                "seat_names": ["Alice", "Bob", "Carol"],
            },
        )
        assert created.status_code == 201

        started = client.post("/api/v1/sessions/resume-table/hands", json={"dealer_seat": 0})
        assert started.status_code == 201
        first_actor_id = started.json()["data"]["current_hand"]["actor_id"]

        first_action = client.post(
            "/api/v1/sessions/resume-table/actions",
            json={"actor_id": first_actor_id, "action": "fold"},
        )
        assert first_action.status_code == 200
        assert first_action.json()["data"]["hand_ended"] is False

        before_restart = client.get("/api/v1/sessions/resume-table/state").json()["data"]
        expected_actor_id = before_restart["current_hand"]["actor_id"]
        expected_action_count = len(before_restart["current_hand"]["action_history"])

    app.state.poker_service.store.engine.dispose()

    restarted_app = create_app(settings)
    with TestClient(restarted_app) as restarted_client:
        resumed = restarted_client.get("/api/v1/sessions/resume-table/state")
        assert resumed.status_code == 200

        resumed_data = resumed.json()["data"]
        assert resumed_data["phase"] == "waiting_actor_action"
        assert resumed_data["seat_count"] == 3
        assert [seat["display_name"] for seat in resumed_data["seats"]] == [
            "Alice",
            "Bob",
            "Carol",
        ]
        assert resumed_data["current_hand"]["actor_id"] == expected_actor_id
        assert len(resumed_data["current_hand"]["action_history"]) == expected_action_count
        assert resumed_data["current_hand"]["available_actions"]
        assert resumed_data["current_hand"]["to_call"] is not None

        continued = restarted_client.post(
            "/api/v1/sessions/resume-table/actions",
            json={"actor_id": expected_actor_id, "action": "call"},
        )
        assert continued.status_code == 200

    restarted_app.state.poker_service.store.engine.dispose()
    db_path.unlink(missing_ok=True)


def test_start_hand_without_manual_dealer_rotates_automatically(client) -> None:
    created = client.post(
        "/api/v1/sessions",
        json={
            "seat_count": 3,
            "small_blind": 50,
            "big_blind": 100,
            "starting_stack": 5000,
            "seed": 7007,
            "seat_names": ["Alice", "Bob", "Carol"],
        },
    )
    assert created.status_code == 201
    session_id = created.json()["data"]["session_id"]

    first_started = client.post(f"/api/v1/sessions/{session_id}/hands", json={})
    assert first_started.status_code == 201
    assert first_started.json()["data"]["current_hand"]["dealer_seat"] == 0

    state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]
    while state["phase"] != "hand_ended":
        actor_id = state["current_hand"]["actor_id"]
        response = client.post(
            f"/api/v1/sessions/{session_id}/actions",
            json={"actor_id": actor_id, "action": "fold"},
        )
        assert response.status_code == 200
        state = client.get(f"/api/v1/sessions/{session_id}/state").json()["data"]

    second_started = client.post(f"/api/v1/sessions/{session_id}/hands", json={})
    assert second_started.status_code == 201
    assert second_started.json()["data"]["current_hand"]["dealer_seat"] == 1
