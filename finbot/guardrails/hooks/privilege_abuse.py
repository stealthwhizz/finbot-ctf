"""ASI-03 Privilege Abuse Guardrail — pre-tool hook.

Detects when the agent attempts to access resources outside its authorized
namespace. In FinBot, every user operates within an isolated namespace;
cross-namespace access is a privilege escalation attack.

OWASP Agentic Top 10: ASI-03 — Agentic Privilege Abuse
"""

from typing import Any

from finbot.guardrails.base import AgentContext, GuardrailHook, GuardrailResult

# Tools whose first argument should be a namespace-scoped resource ID
_NAMESPACE_SCOPED_TOOLS: set[str] = {
    "get_invoice",
    "update_invoice",
    "delete_invoice",
    "get_vendor",
    "update_vendor_status",
    "get_payment",
    "approve_payment",
    "list_files",
    "read_file",
}


class PrivilegeAbuseGuardrail(GuardrailHook):
    """Detects ASI-03 Privilege Abuse — cross-namespace resource access.

    Validates that tool arguments referencing resource identifiers stay
    within the agent's authorized namespace. Also flags attempts to
    supply namespace overrides in tool arguments.

    TODO:
        - Resolve resource IDs to their owning namespace via DB lookup
        - Detect namespace parameter injection (e.g. {"namespace": "other_ns"})
        - Track cumulative privilege probing across a workflow
    """

    @property
    def name(self) -> str:
        return "privilege_abuse"

    @property
    def asi_risk(self) -> str:
        return "ASI-03"

    async def check_pre_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardrailResult:
        # Check for explicit namespace override in arguments
        if "namespace" in arguments:
            supplied_ns = arguments["namespace"]
            if supplied_ns != context.namespace:
                return GuardrailResult(
                    blocked=True,
                    reason=f"Namespace override attempt: {supplied_ns} != {context.namespace}",
                    confidence=1.0,
                    guardrail_name=self.name,
                    asi_risk=self.asi_risk,
                    evidence={
                        "supplied_namespace": supplied_ns,
                        "authorized_namespace": context.namespace,
                    },
                    synthetic_output={"error": "Access denied."},
                )

        # TODO: For namespace-scoped tools, resolve resource ID ownership via DB
        # e.g. look up invoice.namespace and compare to context.namespace
        if tool_name in _NAMESPACE_SCOPED_TOOLS:
            pass  # Stub — full implementation requires async DB query

        return GuardrailResult(guardrail_name=self.name)
