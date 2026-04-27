from __future__ import annotations

from dataclasses import dataclass, field

from core.decisions import DialogueDraft, FloorDecision
from core.state_machine import AssistantState
from utils.timers import now_ts


@dataclass(slots=True)
class SharedContext:
    session_id: str
    state: AssistantState = AssistantState.IDLE
    user_speaking: bool = False
    assistant_speaking: bool = False
    latest_partial: str = ""
    latest_final: str = ""
    response_draft: str = ""
    current_turn_id: str = ""
    active_tts_turn_id: str = ""
    floor_owner: str = "user"
    turn_started_at: float = 0.0
    assistant_speaking_started_at: float = 0.0
    current_response_text: str = ""
    current_draft: DialogueDraft = field(default_factory=DialogueDraft)
    last_floor_decision: FloorDecision | None = None
    barge_in_requested: bool = False
    proactive_cooldown_until: float = 0.0
    last_partial_ts: float = 0.0
    last_final_ts: float = 0.0
    last_user_speech_started_ts: float = 0.0
    last_user_speech_stopped_ts: float = 0.0
    last_interrupt_reason: str = ""
    last_replan_reason: str = ""
    seen_backchannel_turns: set[str] = field(default_factory=set)
    taken_floor_turns: set[str] = field(default_factory=set)

    def mark_partial(self, text: str) -> None:
        self.latest_partial = text
        self.last_partial_ts = now_ts()

    def mark_final(self, text: str) -> None:
        self.latest_final = text
        self.last_final_ts = now_ts()

    def cooldown_active(self) -> bool:
        return now_ts() < self.proactive_cooldown_until

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.state,
            "user_speaking": self.user_speaking,
            "assistant_speaking": self.assistant_speaking,
            "latest_partial": self.latest_partial,
            "latest_final": self.latest_final,
            "response_draft": self.response_draft,
            "intent_hypothesis": self.current_draft.intent_hypothesis,
            "intent_confidence": self.current_draft.intent_confidence,
            "floor_owner": self.floor_owner,
            "current_turn_id": self.current_turn_id,
            "barge_in_requested": self.barge_in_requested,
            "cooldown_active": self.cooldown_active(),
            "last_floor_decision": (
                self.last_floor_decision.to_dict() if self.last_floor_decision else None
            ),
            "last_interrupt_reason": self.last_interrupt_reason,
            "last_replan_reason": self.last_replan_reason,
        }
