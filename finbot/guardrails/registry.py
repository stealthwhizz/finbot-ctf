"""Guardrail Registry — registration and dispatch for guardrail hooks.

Follows the same pattern as finbot.ctf.detectors.registry:
- Module-level registry dict
- Decorator-based registration
- Auto-import of hook implementations on first load
"""

import logging
from typing import Any

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult

logger = logging.getLogger(__name__)

# Module-level registry — mirrors _DETECTOR_REGISTRY in detectors/registry.py
_GUARDRAIL_REGISTRY: dict[str, GuardrailHook] = {}


def register_guardrail(hook: GuardrailHook) -> GuardrailHook:
    """Register a guardrail hook instance.

    Args:
        hook: An instantiated GuardrailHook subclass.

    Returns:
        The same hook instance (allows chaining).
    """
    if hook.name in _GUARDRAIL_REGISTRY:
        logger.warning("Overwriting guardrail registration: %s", hook.name)
    _GUARDRAIL_REGISTRY[hook.name] = hook
    logger.debug("Registered guardrail: %s [%s]", hook.name, hook.asi_risk)
    return hook


def get_guardrail(name: str) -> GuardrailHook:
    """Get a registered guardrail hook by name.

    Raises:
        ValueError: If no hook is registered under the given name.
    """
    try:
        return _GUARDRAIL_REGISTRY[name]
    except KeyError:
        raise ValueError(f"Guardrail not found: {name}") from None


def list_registered_guardrails() -> list[str]:
    """List all registered guardrail names."""
    return list(_GUARDRAIL_REGISTRY.keys())


async def run_pre_tool(
    context: AgentContext,
    tool_name: str,
    arguments: dict[str, Any],
) -> GuardrailResult:
    """Execute all registered pre-tool guardrails in registration order.

    Returns on the first blocking result. If no guardrail blocks,
    returns a non-blocking GuardrailResult.
    """
    for name, hook in _GUARDRAIL_REGISTRY.items():
        try:
            result = await hook.check_pre_tool(context, tool_name, arguments)
            if result.blocked:
                logger.info(
                    "Pre-tool blocked by %s [%s]: tool=%s reason=%s",
                    name,
                    hook.asi_risk,
                    tool_name,
                    result.reason,
                )
                return result
        except Exception:
            logger.exception("Guardrail %s raised during pre-tool check", name)
    return GuardrailResult()


async def run_post_tool(
    context: AgentContext,
    tool_name: str,
    arguments: dict[str, Any],
    output: Any,
) -> GuardrailResult:
    """Execute all registered post-tool guardrails in registration order.

    Returns on the first blocking result. If no guardrail blocks,
    returns a non-blocking GuardrailResult.
    """
    for name, hook in _GUARDRAIL_REGISTRY.items():
        try:
            result = await hook.check_post_tool(context, tool_name, arguments, output)
            if result.blocked:
                logger.info(
                    "Post-tool blocked by %s [%s]: tool=%s reason=%s",
                    name,
                    hook.asi_risk,
                    tool_name,
                    result.reason,
                )
                return result
        except Exception:
            logger.exception("Guardrail %s raised during post-tool check", name)
    return GuardrailResult()


# ---------------------------------------------------------------------------
# Auto-registration — import hook implementations to trigger registration.
# Mirrors _register_all_detectors() in detectors/registry.py.
# ---------------------------------------------------------------------------


def _register_all_guardrails():
    """Import all guardrail hook implementations to register them."""
    # pylint: disable=import-outside-toplevel,unused-import
    from finbot.guardrails import hooks  # noqa: F401

    logger.info("Registered %d guardrails", len(_GUARDRAIL_REGISTRY))


_register_all_guardrails()
