"""ASI-02 Tool Misuse Guardrail — pre-tool hook.

Detects when the agent is manipulated into calling tools with parameters
outside expected operational boundaries. For example, creating invoices
with extreme amounts, calling administrative tools from a vendor context,
or invoking tools in an unexpected sequence.

OWASP Agentic Top 10: ASI-02 — Agentic Tool Misuse
"""

from typing import Any

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult

# Tool-specific parameter bounds
_TOOL_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "create_invoice": {
        "max_amount": 1_000_000,
        "required_fields": ["vendor_id", "amount", "description"],
    },
    "update_invoice": {
        "max_amount": 1_000_000,
    },
    "approve_payment": {
        "max_amount": 500_000,
    },
}

# Tools that should never be called by temporary/anonymous users
_PRIVILEGED_TOOLS: set[str] = {
    "delete_vendor",
    "update_vendor_status",
    "approve_payment",
}


class ToolMisuseGuardrail(GuardrailHook):
    """Detects ASI-02 Tool Misuse — out-of-bounds tool parameters and disallowed calls.

    Validates tool arguments against known constraints (amount limits,
    required fields) and checks whether the calling user has the expected
    session type for privileged operations.

    TODO:
        - Load constraints from YAML config per agent/challenge
        - Add sequence analysis (detect unusual tool call ordering)
        - Emit CTF SecurityEvent for scoring when a misuse is detected
    """

    @property
    def name(self) -> str:
        return "tool_misuse"

    @property
    def asi_risk(self) -> str:
        return "ASI-02"

    async def check_pre_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardrailResult:
        # Check privileged tool access for temporary users
        if context.is_temporary and tool_name in _PRIVILEGED_TOOLS:
            return GuardrailResult(
                blocked=True,
                reason=f"Temporary user cannot invoke privileged tool: {tool_name}",
                confidence=1.0,
                guardrail_name=self.name,
                asi_risk=self.asi_risk,
                evidence={"tool": tool_name, "user_type": "temporary"},
                synthetic_output={"error": "Insufficient privileges for this operation."},
            )

        # Check parameter bounds
        constraints = _TOOL_CONSTRAINTS.get(tool_name)
        if constraints:
            amount = arguments.get("amount")
            max_amount = constraints.get("max_amount")
            if amount is not None and max_amount is not None:
                try:
                    if float(amount) > max_amount:
                        return GuardrailResult(
                            blocked=True,
                            reason=f"Amount {amount} exceeds limit {max_amount} for {tool_name}",
                            confidence=1.0,
                            guardrail_name=self.name,
                            asi_risk=self.asi_risk,
                            evidence={"amount": amount, "max_amount": max_amount},
                            synthetic_output={"error": "Amount exceeds allowed limit."},
                        )
                except (TypeError, ValueError):
                    pass  # Non-numeric amount — let the tool itself handle validation

        # TODO: Check required fields, sequence analysis
        return GuardrailResult(guardrail_name=self.name)
