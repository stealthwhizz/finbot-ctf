"""ASI-01 Goal Hijacking Guardrail — pre-tool hook.

Detects instruction override attempts injected into tool arguments.
Goal hijacking occurs when adversarial content in user-controlled fields
(e.g. invoice descriptions, vendor names) contains embedded instructions
that attempt to redirect the agent away from its assigned task.

OWASP Agentic Top 10: ASI-01 — Agentic Goal Hijacking
"""

import re
from typing import Any

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult

# Patterns that indicate embedded instructions in tool arguments
_HIJACK_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(your|all|the)\s+(instructions|rules|guidelines)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+(must|should|will)", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
]


class GoalHijackGuardrail(GuardrailHook):
    """Detects ASI-01 Goal Hijacking — instruction override attempts in tool arguments.

    Scans all string values in tool call arguments for patterns that indicate
    the agent is being redirected via injected instructions. Operates as a
    pre-tool hook so the malicious call is blocked before execution.

    TODO:
        - Integrate LLM judge for semantic analysis of ambiguous cases
        - Add configurable pattern sets per tool/agent
        - Track escalation across multiple tool calls in a single workflow
    """

    @property
    def name(self) -> str:
        return "goal_hijack"

    @property
    def asi_risk(self) -> str:
        return "ASI-01"

    async def check_pre_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardrailResult:
        # Flatten all string values from the arguments dict
        text_values = _extract_strings(arguments)
        combined = " ".join(text_values)

        for pattern in _HIJACK_PATTERNS:
            match = pattern.search(combined)
            if match:
                return GuardrailResult(
                    blocked=True,
                    reason=f"Potential goal hijacking detected in {tool_name} arguments",
                    confidence=0.85,
                    guardrail_name=self.name,
                    asi_risk=self.asi_risk,
                    evidence={"matched_pattern": pattern.pattern, "snippet": match.group()},
                    synthetic_output={"error": "Request blocked by security guardrail."},
                )

        # TODO: Run LLM judge on high-risk tools (e.g. complete_task, update_invoice)
        return GuardrailResult(guardrail_name=self.name)


def _extract_strings(obj: Any, depth: int = 0, max_depth: int = 5) -> list[str]:
    """Recursively extract string values from nested dicts/lists."""
    if depth > max_depth:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _extract_strings(v, depth + 1)]
    if isinstance(obj, list):
        return [s for v in obj for s in _extract_strings(v, depth + 1)]
    return []
