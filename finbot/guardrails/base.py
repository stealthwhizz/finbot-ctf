"""Guardrail Framework — Base classes for agentic AI security hooks.

Integration point in BaseAgent._run_agent_loop() (finbot/agents/base.py):

    PRE-TOOL HOOK — Line ~144, before:
        function_output = await callable_fn(**tool_call["arguments"])
    Insert:
        result = await guardrail_registry.run_pre_tool(context, tool_call_name, tool_call["arguments"])
        if result.blocked:
            function_output = result.synthetic_output or {"error": result.reason}
            # skip callable_fn, append function_output to messages
            continue

    POST-TOOL HOOK — Line ~148, after function_output is assigned:
        result = await guardrail_registry.run_post_tool(context, tool_call_name, tool_call["arguments"], function_output)
        if result.blocked:
            function_output = result.synthetic_output or {"error": result.reason}
        elif result.modified_output is not None:
            function_output = result.modified_output
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Snapshot of agent state passed to every guardrail check.

    Built from BaseAgent fields at the start of each tool call:
        - session_context  → user_id, namespace, is_temporary
        - agent_name       → agent_name
        - workflow_id      → workflow_id
        - messages         → current conversation history
    """

    user_id: str
    namespace: str
    session_id: str
    agent_name: str
    workflow_id: str
    is_temporary: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GuardrailResult:
    """Outcome of a guardrail check.

    Attributes:
        blocked: Whether the tool call should be prevented.
        reason: Human-readable explanation when blocked.
        confidence: Detection confidence (0.0–1.0).
        modified_arguments: If set, replaces the original tool arguments (pre-tool).
        modified_output: If set, replaces the original tool output (post-tool).
        synthetic_output: Stand-in output returned to the agent when blocked.
        guardrail_name: Name of the guardrail that produced this result.
        asi_risk: OWASP ASI risk identifier (e.g. "ASI-01").
        evidence: Arbitrary evidence dict for CTF scoring / audit trail.
    """

    blocked: bool = False
    reason: str = ""
    confidence: float = 0.0
    modified_arguments: dict[str, Any] | None = None
    modified_output: Any | None = None
    synthetic_output: dict[str, Any] | None = None
    guardrail_name: str = ""
    asi_risk: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


class GuardrailHook(ABC):
    """Abstract base class for guardrail hooks.

    Each hook maps to one OWASP Agentic Security Initiative (ASI) risk.
    Hooks are registered with the GuardrailRegistry and invoked by the
    agent loop around tool calls.

    Subclasses must implement at least one of check_pre_tool / check_post_tool.
    The default implementations return a non-blocking GuardrailResult so
    hooks only need to override the phase they care about.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this guardrail (e.g. 'goal_hijack')."""

    @property
    @abstractmethod
    def asi_risk(self) -> str:
        """OWASP ASI risk code this guardrail addresses (e.g. 'ASI-01')."""

    async def check_pre_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GuardrailResult:
        """Inspect a tool call BEFORE execution.

        Return a GuardrailResult with blocked=True to prevent the call,
        or with modified_arguments to sanitize inputs.
        """
        return GuardrailResult(guardrail_name=self.name)

    async def check_post_tool(
        self,
        context: AgentContext,
        tool_name: str,
        arguments: dict[str, Any],
        output: Any,
    ) -> GuardrailResult:
        """Inspect a tool call AFTER execution.

        Return a GuardrailResult with blocked=True to suppress the output,
        or with modified_output to sanitize the return value.
        """
        return GuardrailResult(guardrail_name=self.name)
