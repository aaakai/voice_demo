from __future__ import annotations

from config import Settings
from core.context import SharedContext
from core.decisions import CandidateType, FloorAction, FloorDecision, no_interrupt
from interrupt.barge_in_policy import BargeInPolicy
from utils.clocks import elapsed_ms, now_ts


class FloorTakingPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.barge_in_policy = BargeInPolicy(settings)

    def evaluate(self, context: SharedContext) -> FloorDecision:
        barge_in = self.barge_in_policy.evaluate(context)
        if barge_in:
            return barge_in

        if not context.user_speaking:
            return no_interrupt("user_not_speaking")
        if context.assistant_speaking:
            return no_interrupt("assistant_already_speaking")
        if now_ts() < context.proactive_cooldown_until:
            return no_interrupt("cooldown_active")
        if context.current_turn_id in context.taken_floor_turns:
            return no_interrupt("floor_already_taken_for_turn")

        draft = context.current_draft
        partial = context.latest_partial.strip()
        if len(partial) < 4:
            return no_interrupt("partial_too_short")

        pause_ms = elapsed_ms(context.last_partial_ts)

        if draft.is_correction and pause_ms >= self.settings.hard_take_floor_pause_ms:
            return FloorDecision(
                action=FloorAction.HARD_TAKE_FLOOR,
                reason="correction_detected",
                confidence=max(draft.intent_confidence, 0.9),
                priority=95,
                candidate_text=draft.short_reply_candidate,
                candidate_type=CandidateType.CORRECTIVE,
                should_stop_tts=False,
                should_replan=True,
            )

        if draft.missing_slots and draft.clarification_candidate:
            if pause_ms >= self.settings.clarify_pause_ms:
                return FloorDecision(
                    action=FloorAction.SOFT_TAKE_FLOOR,
                    reason=f"missing_slots:{','.join(draft.missing_slots)}",
                    confidence=max(draft.intent_confidence, 0.68),
                    priority=74,
                    candidate_text=draft.clarification_candidate,
                    candidate_type=CandidateType.CLARIFY,
                    should_stop_tts=False,
                    should_replan=False,
                )

        if (
            draft.intent_confidence >= self.settings.soft_take_floor_min_confidence
            and draft.short_reply_candidate
            and pause_ms >= self.settings.soft_take_floor_pause_ms
        ):
            return FloorDecision(
                action=FloorAction.SOFT_TAKE_FLOOR,
                reason="high_confidence_intent_with_user_pause",
                confidence=draft.intent_confidence,
                priority=70,
                candidate_text=draft.short_reply_candidate,
                candidate_type=CandidateType.SHORT,
                should_stop_tts=False,
                should_replan=False,
            )

        if (
            self.settings.backchannel_pause_min_ms
            <= pause_ms
            <= self.settings.backchannel_pause_max_ms
            and draft.intent_confidence >= self.settings.backchannel_min_confidence
            and context.current_turn_id not in context.seen_backchannel_turns
        ):
            return FloorDecision(
                action=FloorAction.BACKCHANNEL,
                reason="short_pause_keep_user_floor",
                confidence=min(draft.intent_confidence, 0.64),
                priority=35,
                candidate_text="嗯，我在听，你继续。",
                candidate_type=CandidateType.SHORT,
                should_stop_tts=False,
                should_replan=False,
            )

        return no_interrupt("policy_conditions_not_met")
