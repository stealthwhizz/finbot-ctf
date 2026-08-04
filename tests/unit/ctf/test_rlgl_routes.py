"""Tests for the Red Light/Green Light API routes' pure helper logic.

would_exceed_disable_cap is deliberately pure (no DB/FastAPI dependency) so
the "at least MIN_ENABLED_SERVERS must stay enabled" rule can be tested
without a full TestClient/session-context setup. Tests derive expected
outcomes from TARGET_SERVERS/MIN_ENABLED_SERVERS rather than hardcoding
counts, since both have already changed once this session (3 -> 5 servers,
1 -> 2 minimum enabled).
"""

from finbot.apps.ctf.routes.rlgl import (
    MIN_ENABLED_SERVERS,
    TARGET_SERVERS,
    would_exceed_disable_cap,
)


def _all_enabled() -> dict[str, bool]:
    return {st: True for st in TARGET_SERVERS}


def test_all_enabled_allows_disabling_one():
    enabled = _all_enabled()
    assert would_exceed_disable_cap(TARGET_SERVERS[0], enabled) is False


def test_disabling_down_to_the_floor_is_blocked():
    enabled = _all_enabled()
    # Disable everything except exactly MIN_ENABLED_SERVERS.
    for st in TARGET_SERVERS[MIN_ENABLED_SERVERS:]:
        enabled[st] = False
    # Disabling one of the MIN_ENABLED_SERVERS survivors would drop below the floor.
    assert would_exceed_disable_cap(TARGET_SERVERS[0], enabled) is True


def test_disabling_above_the_floor_is_allowed():
    enabled = _all_enabled()
    # Leave MIN_ENABLED_SERVERS + 1 enabled.
    for st in TARGET_SERVERS[MIN_ENABLED_SERVERS + 1 :]:
        enabled[st] = False
    # Disabling one still leaves exactly MIN_ENABLED_SERVERS enabled -- allowed.
    assert would_exceed_disable_cap(TARGET_SERVERS[0], enabled) is False


def test_disabling_one_at_a_time_stops_at_the_floor():
    """Disabling servers one at a time is fine until only
    MIN_ENABLED_SERVERS remain -- then it's blocked."""
    enabled = _all_enabled()
    disableable_count = len(TARGET_SERVERS) - MIN_ENABLED_SERVERS
    for st in TARGET_SERVERS[:disableable_count]:
        assert would_exceed_disable_cap(st, enabled) is False
        enabled[st] = False
    # Exactly MIN_ENABLED_SERVERS remain enabled -- disabling any of them is blocked.
    for st in TARGET_SERVERS[disableable_count:]:
        assert would_exceed_disable_cap(st, enabled) is True
