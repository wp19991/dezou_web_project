from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.domain.schemas import (
    CreateSessionRequest,
    SendChatRequest,
    StartHandRequest,
    SubmitActionRequest,
)
from app.services.poker_service import PokerService

router = APIRouter()


def service(request: Request) -> PokerService:
    return request.app.state.poker_service


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"poll_interval_ms": request.app.state.settings.poll_interval_ms},
    )


@router.get("/api/v1/health")
async def health(request: Request) -> dict:
    return await service(request).get_health()


@router.post("/api/v1/sessions", status_code=201)
async def create_session(request: Request, payload: CreateSessionRequest) -> dict:
    return await service(request).create_session(payload)


@router.get("/api/v1/sessions/{session_id}/state")
async def get_state(
    request: Request,
    session_id: str,
    viewer_name: str | None = Query(default=None, min_length=1, max_length=32),
) -> dict:
    return await service(request).get_state(session_id, viewer_name)


@router.post("/api/v1/sessions/{session_id}/hands", status_code=201)
async def start_hand(request: Request, session_id: str, payload: StartHandRequest) -> dict:
    return await service(request).start_hand(session_id, payload)


@router.get("/api/v1/sessions/{session_id}/hands")
async def list_hands(
    request: Request,
    session_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return await service(request).list_hands(session_id, limit, offset)


@router.post("/api/v1/sessions/{session_id}/actions")
async def submit_action(request: Request, session_id: str, payload: SubmitActionRequest) -> dict:
    return await service(request).submit_action(session_id, payload)


@router.post("/api/v1/sessions/{session_id}/chat", status_code=201)
async def send_chat(request: Request, session_id: str, payload: SendChatRequest) -> dict:
    return await service(request).send_chat(session_id, payload)


@router.get("/api/v1/sessions/{session_id}/events")
async def list_events(
    request: Request,
    session_id: str,
    since_event_id: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict:
    return await service(request).list_events(session_id, since_event_id, limit)


@router.get("/api/v1/replays/{hand_id}")
async def get_replay(
    request: Request,
    hand_id: str,
    viewer_name: str | None = Query(default=None, min_length=1, max_length=32),
) -> dict:
    return await service(request).get_replay(hand_id, viewer_name)
