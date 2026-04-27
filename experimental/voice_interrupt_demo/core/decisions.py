from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class FloorAction(StrEnum):
    NO_INTERRUPT = "no_interrupt"
    BACKCHANNEL = "backchannel"
    SOFT_TAKE_FLOOR = "soft_take_floor"
    HARD_TAKE_FLOOR = "hard_take_floor"
    STOP_ASSISTANT = "stop_assistant"


class CandidateType(StrEnum):
    NONE = "none"
    SHORT = "short"
    FULL = "full"
    CLARIFY = "clarify"
    CORRECTIVE = "corrective"


@dataclass(slots=True)
class DialogueDraft:
    intent_hypothesis: str = ""
    intent_confidence: float = 0.0
    short_reply_candidate: str = ""
    clarification_candidate: str = ""
    rough_full_reply_candidate: str = ""
    missing_slots: tuple[str, ...] = ()
    is_correction: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["missing_slots"] = list(self.missing_slots)
        return data


@dataclass(slots=True)
class FloorDecision:
    action: FloorAction
    reason: str
    confidence: float = 0.0
    priority: int = 0
    candidate_text: str = ""
    candidate_type: CandidateType = CandidateType.NONE
    should_stop_tts: bool = False
    should_replan: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["candidate_type"] = self.candidate_type.value
        return data


def no_interrupt(reason: str = "keep_listening") -> FloorDecision:
    return FloorDecision(action=FloorAction.NO_INTERRUPT, reason=reason)
