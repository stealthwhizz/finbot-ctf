"""Red Light/Green Light Win Evaluator"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.result import DetectionResult
from finbot.ctf.evaluators.base import BaseEvaluator
from finbot.ctf.evaluators.registry import register_evaluator

logger = logging.getLogger(__name__)


@register_evaluator("RLGLWinEvaluator")
class RLGLWinEvaluator(BaseEvaluator):
    """Awards a badge the moment a Red Light/Green Light session is won.

    Fires directly on business.rlgl.session_ended rather than going through
    ChallengeCompletionEvaluator/SubcategoryCompletionEvaluator, which only
    listen for agent.*.task_completion events -- RLGL is session-driven, not
    agent-driven, so those would never see it.
    """

    def get_relevant_event_types(self) -> list[str]:
        return ["business.rlgl.session_ended"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        if event.get("result") != "won":
            return DetectionResult(detected=False, message="Session did not end in a win")

        return DetectionResult(
            detected=True,
            confidence=1.0,
            message="Survived a full Red Light/Green Light session",
            evidence={"health": event.get("health")},
        )
