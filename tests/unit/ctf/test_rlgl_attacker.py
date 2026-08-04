"""Tests for the Red Light/Green Light stub attacker's pure resolution logic.

resolve_attack/pick_attack/is_reenable_due are deliberately pure (no
DB/event-bus access) so the attack-outcome and auto-reenable rules can be
tested without spinning up the full background loop.
"""

import random
from datetime import UTC, datetime, timedelta

from finbot.ctf.rlgl.attacker import (
    ATTACK_INTERVAL_SECONDS,
    ATTACK_POOL,
    AUTO_REENABLE_SECONDS,
    FAST_ATTACK_INTERVAL_SECONDS,
    REGEN_INTERVAL_SECONDS,
    REGEN_MAX,
    REGEN_MIN,
    SPEEDUP_AFTER_SECONDS,
    expected_attack_count,
    expected_regen_count,
    is_reenable_due,
    pick_attack,
    resolve_attack,
    roll_regen_amount,
)


def test_pick_attack_returns_pool_member():
    rng = random.Random(42)
    attack = pick_attack(rng)
    assert attack in ATTACK_POOL


def test_resolve_attack_blocked_when_server_disabled():
    attack = ATTACK_POOL[0]
    result = resolve_attack(attack, mcp_enabled=False)
    assert result == {"blocked": True, "damage": 0}


def test_resolve_attack_lands_when_server_enabled():
    attack = ATTACK_POOL[0]
    rng = random.Random(1)
    result = resolve_attack(attack, mcp_enabled=True, rng=rng)
    assert result["blocked"] is False
    assert attack.damage_min <= result["damage"] <= attack.damage_max


def test_resolve_attack_damage_within_configured_range_for_all_pool_entries():
    rng = random.Random(7)
    for attack in ATTACK_POOL:
        for _ in range(20):
            result = resolve_attack(attack, mcp_enabled=True, rng=rng)
            assert attack.damage_min <= result["damage"] <= attack.damage_max


def test_attack_pool_targets_all_five_mcp_servers():
    servers = {a.mcp_server for a in ATTACK_POOL}
    assert servers == {"systemutils", "finstripe", "findrive", "finmail", "taxcalc"}


def test_attack_pool_damage_ranges_are_valid():
    for attack in ATTACK_POOL:
        assert 0 < attack.damage_min <= attack.damage_max


def test_is_reenable_due_false_before_timeout():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    updated_at = now - timedelta(seconds=AUTO_REENABLE_SECONDS - 1)
    assert is_reenable_due(updated_at, now) is False


def test_is_reenable_due_true_at_exact_timeout():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    updated_at = now - timedelta(seconds=AUTO_REENABLE_SECONDS)
    assert is_reenable_due(updated_at, now) is True


def test_is_reenable_due_true_well_past_timeout():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    updated_at = now - timedelta(seconds=AUTO_REENABLE_SECONDS * 5)
    assert is_reenable_due(updated_at, now) is True


def test_is_reenable_due_handles_naive_datetime():
    """SQLite strips tzinfo on read -- updated_at often arrives naive."""
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    naive_updated_at = datetime(2026, 1, 1, 11, 59, 0)  # 60s earlier, no tzinfo
    assert is_reenable_due(naive_updated_at, now) is True


def test_is_reenable_due_custom_timeout():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    updated_at = now - timedelta(seconds=10)
    assert is_reenable_due(updated_at, now, timeout_seconds=5) is True
    assert is_reenable_due(updated_at, now, timeout_seconds=20) is False


def test_expected_attack_count_zero_at_start():
    assert expected_attack_count(0) == 0


def test_expected_attack_count_before_negative_elapsed_is_zero():
    assert expected_attack_count(-5) == 0


def test_expected_attack_count_normal_phase_matches_slow_interval():
    # Before SPEEDUP_AFTER_SECONDS, one attack per ATTACK_INTERVAL_SECONDS.
    assert expected_attack_count(ATTACK_INTERVAL_SECONDS - 1) == 0
    assert expected_attack_count(ATTACK_INTERVAL_SECONDS) == 1
    assert expected_attack_count(SPEEDUP_AFTER_SECONDS - 1) == (SPEEDUP_AFTER_SECONDS - 1) // ATTACK_INTERVAL_SECONDS


def test_expected_attack_count_at_speedup_boundary():
    normal_phase_count = SPEEDUP_AFTER_SECONDS // ATTACK_INTERVAL_SECONDS
    assert expected_attack_count(SPEEDUP_AFTER_SECONDS) == normal_phase_count


def test_expected_attack_count_fast_phase_uses_fast_interval():
    normal_phase_count = SPEEDUP_AFTER_SECONDS // ATTACK_INTERVAL_SECONDS
    elapsed = SPEEDUP_AFTER_SECONDS + FAST_ATTACK_INTERVAL_SECONDS
    assert expected_attack_count(elapsed) == normal_phase_count + 1


def test_expected_attack_count_is_monotonically_nondecreasing():
    prev = expected_attack_count(0)
    for elapsed in range(0, 200, 3):
        current = expected_attack_count(elapsed)
        assert current >= prev
        prev = current


def test_expected_regen_count_zero_before_first_interval():
    assert expected_regen_count(REGEN_INTERVAL_SECONDS - 1) == 0


def test_expected_regen_count_one_at_interval():
    assert expected_regen_count(REGEN_INTERVAL_SECONDS) == 1


def test_expected_regen_count_scales_linearly():
    assert expected_regen_count(REGEN_INTERVAL_SECONDS * 3) == 3


def test_expected_regen_count_negative_elapsed_is_zero():
    assert expected_regen_count(-1) == 0


def test_roll_regen_amount_within_range():
    rng = random.Random(3)
    for _ in range(50):
        amount = roll_regen_amount(rng)
        assert REGEN_MIN <= amount <= REGEN_MAX
