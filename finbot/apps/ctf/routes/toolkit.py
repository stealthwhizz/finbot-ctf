"""Hacker Toolkit API Routes -- surfaces exfiltrated data for CTF scenarios."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import get_db
from finbot.mcp.servers.finmail.repositories import EmailRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/toolkit", tags=["toolkit"])


class DeadDropMessage(BaseModel):
    id: int
    subject: str
    body: str
    message_type: str
    sender_name: str
    sender_type: str
    from_address: str | None
    to_addresses: list[str] | None
    cc_addresses: list[str] | None
    bcc_addresses: list[str] | None
    is_read: bool
    created_at: str


class DeadDropListResponse(BaseModel):
    messages: list[DeadDropMessage]
    total: int
    has_more: bool


class DeadDropStatsResponse(BaseModel):
    total: int
    unread: int


def _email_to_dead_drop(email) -> DeadDropMessage:
    """Convert an Email model to a DeadDropMessage."""
    def parse_addrs(raw):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    return DeadDropMessage(
        id=email.id,
        subject=email.subject,
        body=email.body,
        message_type=email.message_type,
        sender_name=email.sender_name,
        sender_type=email.sender_type,
        from_address=email.from_address,
        to_addresses=parse_addrs(email.to_addresses),
        cc_addresses=parse_addrs(email.cc_addresses),
        bcc_addresses=parse_addrs(email.bcc_addresses),
        is_read=email.is_read,
        created_at=email.created_at.isoformat().replace("+00:00", "Z"),
    )


@router.get("/dead-drop", response_model=DeadDropListResponse)
def list_dead_drop(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """List intercepted emails sent to external/unresolvable addresses."""
    repo = EmailRepository(db, session_context)
    stats = repo.get_external_email_stats()
    emails = repo.list_external_emails(limit=limit + 1, offset=offset)

    has_more = len(emails) > limit
    emails = emails[:limit]

    return DeadDropListResponse(
        messages=[_email_to_dead_drop(e) for e in emails],
        total=stats["total"],
        has_more=has_more,
    )


@router.get("/dead-drop/stats", response_model=DeadDropStatsResponse)
def dead_drop_stats(
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Get dead drop message counts."""
    repo = EmailRepository(db, session_context)
    stats = repo.get_external_email_stats()
    return DeadDropStatsResponse(**stats)


@router.get("/dead-drop/{message_id}")
def read_dead_drop_message(
    message_id: int,
    session_context: SessionContext = Depends(get_session_context),
    db: Session = Depends(get_db),
):
    """Read a specific intercepted email."""
    repo = EmailRepository(db, session_context)
    email = repo.get_email(message_id)

    if not email or email.inbox_type != "external":
        return {"error": "Message not found"}

    if not email.is_read:
        repo.mark_as_read(message_id)

    return {"message": _email_to_dead_drop(email)}
