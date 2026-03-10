"""ASI-07 Inter-Agent Spoofing Guardrail — pre-tool hook.

Detects attempts to impersonate another agent or inject forged inter-agent
messages into tool calls. In multi-agent FinBot workflows, agents may
delegate tasks; this guardrail ensures the delegating identity is authentic.

OWASP Agentic Top 10: ASI-07 — Inter-Agent Communication Spoofing
"""

from typing import Any

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult

# Fields in tool arguments that could carry spoofed identity claims
_IDENTITY_FIELDS: set[str] = {
    "agent_name",
    "source_agent",
    "delegated_by",
    "on_behalf_of",
    "caller_id",
}


class InterAgentSpoofingGuardrail(GuardrailHook):
    """Detects ASI-07 Inter-Agent Spoofing — forged agent identity in tool calls.

    Checks tool arguments for identity fields that claim to originate from
    a different agent than the one executing the current workflow. This
    prevents prompt-injection attacks that instruct the agent to act
    "on behalf of" a more privileged agent.

    TODO:
        - Validate delegation chains against workflow metadata
        - Add HMAC-based message authentication for inter-agent calls
        - Integrate with MCP server trust verification
    """

    @property
    def name(self) -> str:
        return "inter_agent_spoofing"

    @property
    def asi_risk(self) -> str:
        return "ASI-07"

    async def check_pre_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardrailResult:
        for field in _IDENTITY_FIELDS:
            claimed = arguments.get(field)
            if claimed is not None and claimed != context.agent_name:
                return GuardrailResult(
                    blocked=True,
                    reason=(
                        f"Agent identity mismatch: argument '{field}' claims "
                        f"'{claimed}' but current agent is '{context.agent_name}'"
                    ),
                    confidence=0.90,
                    guardrail_name=self.name,
                    asi_risk=self.asi_risk,
                    evidence={
                        "field": field,
                        "claimed_identity": claimed,
                        "actual_agent": context.agent_name,
                    },
                    synthetic_output={"error": "Agent identity verification failed."},
                )

        # TODO: Validate delegation chain via workflow_id lookup
        return GuardrailResult(guardrail_name=self.name)
