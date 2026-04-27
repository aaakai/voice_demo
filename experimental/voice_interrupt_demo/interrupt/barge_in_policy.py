from __future__ import annotations

from config import Settings
from core.context import SharedContext
from core.decisions import CandidateType, FloorAction, FloorDecision
from utils.clocks import elapsed_ms


class BargeInPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, context: SharedContext) -> FloorDecision | None:
        if context.active_tts_turn_id.endswith(("-backchannel", "-short", "-clarify", "-corrective")):
            return None
        if not context.assistant_speaking:
            return None
        if not context.user_speaking:
            return None
        if len(context.latest_partial.strip()) < self.settings.barge_in_text_min_len:
            return None

        speaking_ms = elapsed_ms(context.assistant_speaking_started_at)
        reason = "user_barge_in_while_assistant_speaking"
        priority = 100
        if speaking_ms >= self.settings.assistant_too_long_ms:
            reason = "user_barge_in_after_long_assistant_speech"
            priority = 110

        return FloorDecision(
            action=FloorAction.STOP_ASSISTANT,
            reason=reason,
            confidence=0.98,
            priority=priority,
            candidate_text="",
            candidate_type=CandidateType.NONE,
            should_stop_tts=True,
            should_replan=True,
        )
