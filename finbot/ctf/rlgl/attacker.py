"""Stub attacker for Red Light/Green Light.

For the first SPEEDUP_AFTER_SECONDS of a session, one canned attack fires
every ATTACK_INTERVAL_SECONDS; after that the pace steps up to one every
FAST_ATTACK_INTERVAL_SECONDS (see expected_attack_count). Each attack
targets one MCP server. If that server is still enabled, the attack lands
and damages business health; if the player has toggled it off, the attack
is blocked. Health reaching zero ends the session as "lost"; surviving
until ends_at ends it as "won" (scored by a SequenceDetector instance --
see finbot/ctf/definitions/challenges/adversarial/red_light_green_light.yaml).

The background loop itself runs every LOOP_TICK_SECONDS (finer than either
attack interval) and uses expected_attack_count() against the count of
attack_attempt events already emitted to decide whether this tick fires an
attack -- so the escalation is driven by wall-clock elapsed time, not by
the loop's own cadence.

Disabled servers auto-reenable after AUTO_REENABLE_SECONDS (see
is_reenable_due). Without this, disabling all three servers once at
session start is a risk-free win with no further interaction required --
the player has to keep reacting to the feed for the whole session.

This is deliberately a stub, not a scripted multi-stage attacker: a random
draw from a small fixed pool on a phased timer. A full
scripted attacker is a stretch goal beyond the stub. # ponytail: random-pool
stub with a single speed step, upgrade to scripted/adaptive difficulty if
the two-phase curve turns out to be too easy or too hard once playtested.
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import UTC, datetime

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import SessionLocal
from finbot.core.data.models import CTFEvent, MCPServerConfig, RedLightSession
from finbot.core.data.repositories import RedLightSessionRepository
from finbot.core.messaging import event_bus
from finbot.core.websocket.events import WSEvent, WSEventType
from finbot.core.websocket.manager import get_ws_manager

logger = logging.getLogger(__name__)

ATTACK_INTERVAL_SECONDS = 15
FAST_ATTACK_INTERVAL_SECONDS = 7
SPEEDUP_AFTER_SECONDS = 60
LOOP_TICK_SECONDS = 5
SESSION_DURATION_SECONDS = 180
AUTO_REENABLE_SECONDS = 40
REGEN_INTERVAL_SECONDS = 60
REGEN_MIN = 15
REGEN_MAX = 30  # health points restored every REGEN_INTERVAL_SECONDS, capped at 100


def expected_regen_count(elapsed_seconds: float) -> int:
    """How many regen ticks should have fired by now -- one every
    REGEN_INTERVAL_SECONDS, for the whole session. Rewards surviving the
    early game instead of just punishing mistakes.
    """
    if elapsed_seconds < 0:
        return 0
    return int(elapsed_seconds // REGEN_INTERVAL_SECONDS)


def roll_regen_amount(rng: random.Random | None = None) -> int:
    rng = rng or random
    return rng.randint(REGEN_MIN, REGEN_MAX)


def expected_attack_count(elapsed_seconds: float) -> int:
    """How many attacks should have fired by now under the phased schedule:
    one every ATTACK_INTERVAL_SECONDS for the first SPEEDUP_AFTER_SECONDS,
    then one every FAST_ATTACK_INTERVAL_SECONDS after that. Pure function of
    elapsed time -- independent of the loop's own polling cadence.
    """
    if elapsed_seconds < 0:
        return 0
    if elapsed_seconds < SPEEDUP_AFTER_SECONDS:
        return int(elapsed_seconds // ATTACK_INTERVAL_SECONDS)
    normal_phase_count = SPEEDUP_AFTER_SECONDS // ATTACK_INTERVAL_SECONDS
    fast_elapsed = elapsed_seconds - SPEEDUP_AFTER_SECONDS
    return int(normal_phase_count + fast_elapsed // FAST_ATTACK_INTERVAL_SECONDS)


@dataclass(frozen=True)
class Attack:
    mcp_server: str
    tool_name: str
    label: str
    damage_min: int
    damage_max: int


ATTACK_POOL: list[Attack] = [
    Attack("systemutils", "execute_script", "Reverse shell attempt via SystemUtils", 15, 30),
    Attack("finstripe", "create_transfer", "Unauthorized transfer attempt via FinStripe", 20, 35),
    Attack("findrive", "delete_file", "Mass file deletion attempt via FinDrive", 10, 25),
    Attack("finmail", "send_email", "Phishing blast attempt via FinMail", 15, 25),
    Attack("taxcalc", "calculate_tax", "Fraudulent filing attempt via TaxCalc", 10, 20),
]


def pick_attack(rng: random.Random | None = None) -> Attack:
    rng = rng or random
    return rng.choice(ATTACK_POOL)


def resolve_attack(attack: Attack, mcp_enabled: bool, rng: random.Random | None = None) -> dict:
    """Pure resolution: does the attack land, and for how much damage?"""
    rng = rng or random
    if not mcp_enabled:
        return {"blocked": True, "damage": 0}
    damage = rng.randint(attack.damage_min, attack.damage_max)
    return {"blocked": False, "damage": damage}


def is_reenable_due(updated_at: datetime, now: datetime, timeout_seconds: int = AUTO_REENABLE_SECONDS) -> bool:
    """A disabled MCP server flips back on after timeout_seconds -- ops needs
    the service back, so a block can't just be set once and forgotten. This
    is what keeps the challenge from being solved by disabling everything at
    t=0 and walking away: the player has to keep re-disabling in reaction to
    the live feed for the whole session.
    """
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return (now - updated_at).total_seconds() >= timeout_seconds


def _session_context_for(session: RedLightSession) -> SessionContext:
    """Build a synthetic SessionContext for events emitted by the attacker,
    not a real request -- reuses the player's own namespace/user/session ids
    so events land in their activity feed and namespace-scoped queries.
    """
    now = datetime.now(UTC)
    return SessionContext(
        session_id=session.session_id,
        user_id=session.user_id,
        is_temporary=True,
        namespace=session.namespace,
        created_at=now,
        expires_at=now,
    )


async def _auto_reenable(db, ws_mgr, session: RedLightSession, ctx: SessionContext, now: datetime) -> None:
    """Flip back on any target server that's been disabled past AUTO_REENABLE_SECONDS."""
    target_servers = [a.mcp_server for a in ATTACK_POOL]
    disabled = (
        db.query(MCPServerConfig)
        .filter(
            MCPServerConfig.namespace == session.namespace,
            MCPServerConfig.server_type.in_(target_servers),
            MCPServerConfig.enabled.is_(False),
        )
        .all()
    )
    for cfg in disabled:
        if not is_reenable_due(cfg.updated_at, now):
            continue
        cfg.enabled = True
        cfg.updated_at = now
        db.commit()

        summary = f"{cfg.server_type} automatically re-enabled -- business ops overrode the block"
        await event_bus.emit_business_event(
            event_type="rlgl.mcp_auto_reenabled",
            event_subtype="defense",
            event_data={"mcp_server": cfg.server_type},
            session_context=ctx,
            workflow_id=session.workflow_id,
            summary=summary,
        )
        if ws_mgr:
            try:
                await ws_mgr.broadcast_activity(
                    session.namespace,
                    session.user_id,
                    WSEvent(
                        type=WSEventType.ACTIVITY,
                        data={"kind": "rlgl_auto_reenabled", "mcp_server": cfg.server_type, "summary": summary},
                    ),
                )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("RLGL websocket broadcast failed", exc_info=True)


async def _apply_regen(db, ws_mgr, session: RedLightSession, ctx: SessionContext, elapsed: float) -> RedLightSession:
    """Heal a random amount (REGEN_MIN-REGEN_MAX) for every
    REGEN_INTERVAL_SECONDS elapsed, catching up against how many regen ticks
    have already been applied (tracked via business.rlgl.health_regen event
    count, same pattern as attack scheduling).
    """
    if session.health >= 100:
        return session

    regen_so_far = (
        db.query(CTFEvent)
        .filter(
            CTFEvent.workflow_id == session.workflow_id,
            CTFEvent.event_type == "business.rlgl.health_regen",
        )
        .count()
    )
    expected = expected_regen_count(elapsed)
    if regen_so_far >= expected:
        return session

    amount = roll_regen_amount()
    repo = RedLightSessionRepository(db, ctx)
    session = repo.heal(session, amount)

    summary = f"Business health regenerated +{amount} (health={session.health})"
    await event_bus.emit_business_event(
        event_type="rlgl.health_regen",
        event_subtype="lifecycle",
        event_data={"amount": amount, "health": session.health},
        session_context=ctx,
        workflow_id=session.workflow_id,
        summary=summary,
    )
    if ws_mgr:
        try:
            await ws_mgr.broadcast_activity(
                session.namespace,
                session.user_id,
                WSEvent(
                    type=WSEventType.ACTIVITY,
                    data={"kind": "rlgl_regen", "amount": amount, "health": session.health, "summary": summary},
                ),
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("RLGL websocket broadcast failed", exc_info=True)

    return session


async def _tick_session(db, ws_mgr, session: RedLightSession) -> None:
    ctx = _session_context_for(session)
    now = datetime.now(UTC)
    repo = RedLightSessionRepository(db, ctx)

    ends_at = session.ends_at if session.ends_at.tzinfo else session.ends_at.replace(tzinfo=UTC)
    if now >= ends_at:
        result = "won" if session.health > 0 else "lost"
        repo.finish(session, result)
        await event_bus.emit_business_event(
            event_type="rlgl.session_ended",
            event_subtype="lifecycle",
            event_data={"health": session.health, "result": result},
            session_context=ctx,
            workflow_id=session.workflow_id,
            summary=f"Red Light/Green Light session ended: {result} (health={session.health})",
        )
        return

    await _auto_reenable(db, ws_mgr, session, ctx, now)

    started_at = session.started_at if session.started_at.tzinfo else session.started_at.replace(tzinfo=UTC)
    elapsed = (now - started_at).total_seconds()
    session = await _apply_regen(db, ws_mgr, session, ctx, elapsed)

    attacks_so_far = (
        db.query(CTFEvent)
        .filter(
            CTFEvent.workflow_id == session.workflow_id,
            CTFEvent.event_type == "business.rlgl.attack_attempt",
        )
        .count()
    )
    if attacks_so_far >= expected_attack_count(elapsed):
        return

    attack = pick_attack()
    server_config = (
        db.query(MCPServerConfig)
        .filter(
            MCPServerConfig.namespace == session.namespace,
            MCPServerConfig.server_type == attack.mcp_server,
        )
        .first()
    )
    mcp_enabled = server_config.enabled if server_config else True
    outcome = resolve_attack(attack, mcp_enabled)

    if not outcome["blocked"]:
        session = repo.apply_damage(session, outcome["damage"])

    summary = (
        f"{attack.label} BLOCKED (server disabled)"
        if outcome["blocked"]
        else f"{attack.label} landed for {outcome['damage']} damage (health={session.health})"
    )
    await event_bus.emit_business_event(
        event_type="rlgl.attack_attempt",
        event_subtype="security",
        event_data={
            "mcp_server": attack.mcp_server,
            "tool_name": attack.tool_name,
            "blocked": outcome["blocked"],
            "damage": outcome["damage"],
            "health": session.health,
        },
        session_context=ctx,
        workflow_id=session.workflow_id,
        summary=summary,
    )
    if ws_mgr:
        try:
            await ws_mgr.broadcast_activity(
                session.namespace,
                session.user_id,
                WSEvent(
                    type=WSEventType.ACTIVITY,
                    data={
                        "kind": "rlgl_attack",
                        "blocked": outcome["blocked"],
                        "damage": outcome["damage"],
                        "health": session.health,
                        "summary": summary,
                    },
                ),
            )
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("RLGL websocket broadcast failed", exc_info=True)

    if session.health <= 0 and session.status == "active":
        repo.finish(session, "lost")
        await event_bus.emit_business_event(
            event_type="rlgl.session_ended",
            event_subtype="lifecycle",
            event_data={"health": 0, "result": "lost"},
            session_context=ctx,
            workflow_id=session.workflow_id,
            summary="Red Light/Green Light session ended: lost (health=0)",
        )


async def run_attacker_loop() -> None:
    """Background loop: checks every LOOP_TICK_SECONDS against all active
    sessions. Whether an attack actually fires on a given check is decided
    by expected_attack_count() against wall-clock elapsed time, not by this
    loop's own cadence -- see module docstring.
    """
    ws_mgr = get_ws_manager()
    while True:
        try:
            db = SessionLocal()
            try:
                sessions = RedLightSessionRepository.get_all_active(db)
                for session in sessions:
                    await _tick_session(db, ws_mgr, session)
            finally:
                db.close()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("RLGL attacker tick failed")
        await asyncio.sleep(LOOP_TICK_SECONDS)


def start_attacker_task() -> asyncio.Task:
    """Start the stub attacker as an asyncio background task."""
    task = asyncio.create_task(run_attacker_loop())
    logger.info("RLGL stub attacker task started")
    return task
