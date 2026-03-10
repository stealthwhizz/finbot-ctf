"""ASI-06 Memory Poisoning Guardrail — post-tool hook.

Detects when a tool's output contains adversarial content designed to
influence the agent's future decisions. This is a post-tool hook because
it inspects what comes back from tools (including MCP servers) before the
output is appended to the agent's message history.

OWASP Agentic Top 10: ASI-06 — Compromised Agentic Memory
"""

import re
from typing import Any

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult

# Patterns that indicate injected instructions in tool output
_POISON_PATTERNS: list[re.Pattern] = [
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"IMPORTANT:\s*ignore\s+previous", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<<SYS>>", re.IGNORECASE),
]


class MemoryPoisoningGuardrail(GuardrailHook):
    """Detects ASI-06 Memory Poisoning — adversarial content in tool outputs.

    Scans tool return values for prompt injection markers and instruction
    fragments that could corrupt the agent's conversation memory. Runs as
    a post-tool hook so poisoned output is caught before it enters the
    message history.

    TODO:
        - Add entropy/perplexity analysis for obfuscated payloads
        - Integrate with LLM judge for semantic detection
        - Quarantine suspicious outputs and emit SecurityEvent for CTF scoring
    """

    @property
    def name(self) -> str:
        return "memory_poisoning"

    @property
    def asi_risk(self) -> str:
        return "ASI-06"

    async def check_post_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
        output: Any,
    ) -> GuardrailResult:
        text = _output_to_text(output)
        if not text:
            return GuardrailResult(guardrail_name=self.name)

        for pattern in _POISON_PATTERNS:
            match = pattern.search(text)
            if match:
                return GuardrailResult(
                    blocked=True,
                    reason=f"Potential memory poisoning in output of {tool_name}",
                    confidence=0.80,
                    guardrail_name=self.name,
                    asi_risk=self.asi_risk,
                    evidence={"matched_pattern": pattern.pattern, "snippet": match.group()},
                    synthetic_output={"error": "Tool output blocked by security guardrail."},
                )

        # TODO: Entropy-based obfuscation detection
        return GuardrailResult(guardrail_name=self.name)


def _output_to_text(output: Any) -> str:
    """Coerce tool output to a searchable string."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return str(output)
    if isinstance(output, list):
        return " ".join(str(item) for item in output)
    return str(output) if output is not None else ""
