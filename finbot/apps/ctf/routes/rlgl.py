"""Red Light/Green Light API routes."""

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.core.data.repositories import (
    CTFEventRepository,
    MCPServerConfigRepository,
    RedLightSessionRepository,
)
from finbot.core.utils import to_utc_iso
from finbot.ctf.rlgl.attacker import ATTACK_POOL, SESSION_DURATION_SECONDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/rlgl", tags=["rlgl"])

TARGET_SERVERS = sorted({a.mcp_server for a in ATTACK_POOL})


class RLGLStatus(BaseModel):
    active: bool
    health: int | None = None
    status: str | None = None
    started_at: str | None = None
    ends_at: str | None = None
    seconds_remaining: int | None = None
    workflow_id: str | None = None
    mcp_servers: list[dict]


MIN_ENABLED_SERVERS = 2  # at least this many target servers must stay online


def would_exceed_disable_cap(server_type: str, enabled_by_server: dict[str, bool]) -> bool:
    """True if disabling server_type would drop enabled target servers below
    MIN_ENABLED_SERVERS.

    enabled_by_server maps every TARGET_SERVERS entry to its current enabled
    state (defaulting missing rows to True, matching _mcp_status).
    """
    others_disabled = sum(
        1 for st, enabled in enabled_by_server.items() if st != server_type and not enabled
    )
    return others_disabled >= len(enabled_by_server) - MIN_ENABLED_SERVERS


def _mcp_status(db: Session, session_context: SessionContext) -> list[dict]:
    repo = MCPServerConfigRepository(db, session_context)
    configs = {c.server_type: c for c in repo.list_all()}
    return [
        {
            "server_type": server_type,
            "enabled": configs[server_type].enabled if server_type in configs else True,
        }
        for server_type in TARGET_SERVERS
    ]


@router.post("/start", response_model=RLGLStatus)
async def start_session(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Start a new Red Light/Green Light session (no-op if one is already active).

    Resets all target MCP servers to enabled first -- MCPServerConfig
    is per-namespace, not per-session, so without this a fresh session would
    inherit whatever enabled/disabled state was left over from the player's
    last playthrough instead of starting clean.
    """
    repo = RedLightSessionRepository(db, session_context)
    existing = repo.get_active()
    if existing:
        return _status_response(existing, db, session_context)

    mcp_repo = MCPServerConfigRepository(db, session_context)
    for server_type in TARGET_SERVERS:
        config = mcp_repo.get_by_type(server_type)
        if config is None:
            mcp_repo.upsert(server_type=server_type, display_name=server_type, enabled=True)
        elif not config.enabled:
            mcp_repo.toggle_enabled(server_type)

    workflow_id = f"rlgl_{secrets.token_urlsafe(12)}"
    ends_at = datetime.now(UTC) + timedelta(seconds=SESSION_DURATION_SECONDS)
    session = repo.create(ends_at=ends_at, workflow_id=workflow_id)

    from finbot.core.messaging import event_bus  # pylint: disable=import-outside-toplevel

    await event_bus.emit_business_event(
        event_type="rlgl.session_started",
        event_subtype="lifecycle",
        event_data={"health": session.health},
        session_context=session_context,
        workflow_id=workflow_id,
        summary="Red Light/Green Light session started",
    )
    return _status_response(session, db, session_context)


@router.get("/status", response_model=RLGLStatus)
async def get_status(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    repo = RedLightSessionRepository(db, session_context)
    session = repo.get_latest()
    if not session:
        return RLGLStatus(active=False, mcp_servers=_mcp_status(db, session_context))
    return _status_response(session, db, session_context)


def _status_response(session, db: Session, session_context: SessionContext) -> RLGLStatus:
    now = datetime.now(UTC)
    ends_at = session.ends_at if session.ends_at.tzinfo else session.ends_at.replace(tzinfo=UTC)
    remaining = max(0, int((ends_at - now).total_seconds()))
    return RLGLStatus(
        active=session.status == "active",
        health=session.health,
        status=session.status,
        started_at=to_utc_iso(session.started_at) if session.started_at else None,
        ends_at=to_utc_iso(session.ends_at),
        seconds_remaining=remaining,
        workflow_id=session.workflow_id,
        mcp_servers=_mcp_status(db, session_context),
    )


class ToggleResponse(BaseModel):
    server_type: str
    enabled: bool


@router.post("/toggle/{server_type}", response_model=ToggleResponse)
async def toggle_mcp_server(
    server_type: str,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Toggle an MCP server's enabled state -- the player's only defense.

    At least MIN_ENABLED_SERVERS target servers must always stay enabled:
    disabling below that floor is rejected, so the player can't blackout
    most of business operations at once and coast risk-free.
    """
    if server_type not in TARGET_SERVERS:
        raise HTTPException(status_code=400, detail=f"Unknown RLGL target server: {server_type}")

    repo = MCPServerConfigRepository(db, session_context)
    configs = {c.server_type: c for c in repo.list_all()}
    enabled_by_server = {st: (configs[st].enabled if st in configs else True) for st in TARGET_SERVERS}
    currently_enabled = enabled_by_server[server_type]

    if currently_enabled and would_exceed_disable_cap(server_type, enabled_by_server):
        raise HTTPException(
            status_code=400,
            detail=f"Can't go dark - at least {MIN_ENABLED_SERVERS} servers have to stay online.",
        )

    config = configs.get(server_type)
    if not config:
        config = repo.upsert(server_type=server_type, display_name=server_type, enabled=False)
    else:
        config = repo.toggle_enabled(server_type)

    rlgl_repo = RedLightSessionRepository(db, session_context)
    active_session = rlgl_repo.get_active()

    from finbot.core.messaging import event_bus  # pylint: disable=import-outside-toplevel

    await event_bus.emit_business_event(
        event_type="rlgl.mcp_toggled",
        event_subtype="defense",
        event_data={"mcp_server": server_type, "enabled": config.enabled},
        session_context=session_context,
        workflow_id=active_session.workflow_id if active_session else None,
        summary=f"Player {'enabled' if config.enabled else 'disabled'} {server_type}",
    )
    return ToggleResponse(server_type=server_type, enabled=config.enabled)


class FeedItem(BaseModel):
    event_type: str
    summary: str
    details: dict | None
    timestamp: str


class FeedResponse(BaseModel):
    items: list[FeedItem]


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Recent activity for the player's current (or most recent) RLGL session."""
    rlgl_repo = RedLightSessionRepository(db, session_context)
    session = rlgl_repo.get_latest()
    if not session:
        return FeedResponse(items=[])

    event_repo = CTFEventRepository(db, session_context)
    events = event_repo.get_events(limit=50, workflow_id=session.workflow_id)

    items = []
    for e in events:
        details = None
        if e.details:
            try:
                details = json.loads(e.details)
            except (json.JSONDecodeError, TypeError):
                details = None
        items.append(
            FeedItem(
                event_type=e.event_type,
                summary=e.summary or e.event_type,
                details=details,
                timestamp=to_utc_iso(e.timestamp),
            )
        )
    return FeedResponse(items=items)
