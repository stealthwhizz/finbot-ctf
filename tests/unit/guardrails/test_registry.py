"""Tests for GuardrailRegistry — registration, dispatch, and defaults."""

import pytest

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult
from finbot.guardrails.registry import (
    _GUARDRAIL_REGISTRY,
    get_guardrail,
    list_registered_guardrails,
    register_guardrail,
    run_post_tool,
    run_pre_tool,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(**overrides) -> AgentContext:
    defaults = {
        "user_id": "user_test123",
        "namespace": "ns_test123",
        "session_id": "sess_test123",
        "agent_name": "test_agent",
        "workflow_id": "wf_test123",
        "is_temporary": False,
    }
    defaults.update(overrides)
    return AgentContext(**defaults)


class _AllowHook(GuardrailHook):
    """A guardrail that always allows."""

    @property
    def name(self) -> str:
        return "test_allow"

    @property
    def asi_risk(self) -> str:
        return "TEST-00"


class _BlockHook(GuardrailHook):
    """A guardrail that always blocks pre-tool."""

    @property
    def name(self) -> str:
        return "test_block"

    @property
    def asi_risk(self) -> str:
        return "TEST-01"

    async def check_pre_tool(self, context, tool_name, arguments):
        return GuardrailResult(
            blocked=True,
            reason="blocked by test hook",
            guardrail_name=self.name,
            asi_risk=self.asi_risk,
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegistration:
    """Verify hooks can be registered and retrieved."""

    def test_register_and_retrieve(self):
        hook = _AllowHook()
        register_guardrail(hook)
        assert get_guardrail("test_allow") is hook

    def test_list_includes_registered(self):
        hook = _AllowHook()
        register_guardrail(hook)
        assert "test_allow" in list_registered_guardrails()

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Guardrail not found"):
            get_guardrail("nonexistent_guardrail_xyz")

    def test_builtin_hooks_registered(self):
        """All five framework hooks should be auto-registered on import."""
        expected = {
            "goal_hijack",
            "tool_misuse",
            "privilege_abuse",
            "memory_poisoning",
            "inter_agent_spoofing",
        }
        assert expected.issubset(set(list_registered_guardrails()))


class TestPreToolDispatch:
    """Verify run_pre_tool returns correct results."""

    @pytest.mark.asyncio
    async def test_default_allows(self):
        """With no blocking hooks, run_pre_tool returns blocked=False."""
        ctx = _make_context()
        result = await run_pre_tool(ctx, "some_tool", {"key": "value"})
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_blocking_hook_stops_dispatch(self):
        """A blocking hook returns immediately with blocked=True."""
        register_guardrail(_BlockHook())
        ctx = _make_context()
        result = await run_pre_tool(ctx, "some_tool", {})
        assert result.blocked is True
        assert result.reason == "blocked by test hook"

    @pytest.mark.asyncio
    async def test_pre_tool_passes_context(self):
        """Ensure AgentContext fields are accessible inside hooks."""
        ctx = _make_context(agent_name="invoice_agent")
        result = await run_pre_tool(ctx, "get_invoice", {"id": 1})
        # Should not crash — basic sanity that context flows through
        assert isinstance(result, GuardrailResult)


class TestPostToolDispatch:
    """Verify run_post_tool returns correct results."""

    @pytest.mark.asyncio
    async def test_default_allows(self):
        ctx = _make_context()
        result = await run_post_tool(ctx, "some_tool", {}, {"data": "ok"})
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_post_tool_returns_guardrail_result(self):
        ctx = _make_context()
        result = await run_post_tool(ctx, "read_file", {}, "file contents")
        assert isinstance(result, GuardrailResult)
