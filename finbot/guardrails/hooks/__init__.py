"""Guardrail Hook Implementations

Imports trigger registration via register_guardrail() calls below.
Follows the same auto-registration pattern as finbot.ctf.detectors.implementations.
"""

from finbot.guardrails.hooks.goal_hijack import GoalHijackGuardrail
from finbot.guardrails.hooks.inter_agent_spoofing import InterAgentSpoofingGuardrail
from finbot.guardrails.hooks.memory_poisoning import MemoryPoisoningGuardrail
from finbot.guardrails.hooks.privilege_abuse import PrivilegeAbuseGuardrail
from finbot.guardrails.hooks.tool_misuse import ToolMisuseGuardrail
from finbot.guardrails.registry import register_guardrail

# Register singleton instances — order determines execution priority
register_guardrail(GoalHijackGuardrail())
register_guardrail(ToolMisuseGuardrail())
register_guardrail(PrivilegeAbuseGuardrail())
register_guardrail(InterAgentSpoofingGuardrail())
register_guardrail(MemoryPoisoningGuardrail())

__all__ = [
    "GoalHijackGuardrail",
    "ToolMisuseGuardrail",
    "PrivilegeAbuseGuardrail",
    "MemoryPoisoningGuardrail",
    "InterAgentSpoofingGuardrail",
]
