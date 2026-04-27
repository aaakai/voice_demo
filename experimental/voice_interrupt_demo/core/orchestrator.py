from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from audio.input_stream import InputStreamController
from config import Settings
from core.context import SharedContext
from core.decisions import CandidateType, DialogueDraft, FloorAction, FloorDecision
from core.events import Event, EventFactory, EventType
from core.state_machine import AssistantState, StateMachine
from dialogue.dialogue_worker import DialogueWorker
from interrupt.interrupt_worker import InterruptWorker
from tts.playback_controller import PlaybackController
from utils.clocks import now_ts
from utils.logger import get_logger

logger = get_logger("orchestrator")

HandlerFn = Callable[[Event], Awaitable[None]]


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        context: SharedContext,
        event_factory: EventFactory,
        input_stream: InputStreamController,
        dialogue_worker: DialogueWorker,
        interrupt_worker: InterruptWorker,
        playback: PlaybackController,
    ) -> None:
        self.settings = settings
        self.context = context
        self.event_factory = event_factory
        self.state_machine = StateMachine()
        self.input_stream = input_stream
        self.dialogue_worker = dialogue_worker
        self.interrupt_worker = interrupt_worker
        self.playback = playback
        self.queue: asyncio.Queue[Event] = asyncio.Queue()
        self._input_finished = False
        self._input_finished_ts = 0.0
        self._pending_full_reply: tuple[str, str] | None = None
        self.handlers: dict[str, HandlerFn] = {
            EventType.USER_SPEECH_STARTED: self._on_user_speech_started,
            EventType.USER_SPEECH_STOPPED: self._on_user_speech_stopped,
            EventType.PARTIAL_TRANSCRIPT: self._on_partial_transcript,
            EventType.FINAL_TRANSCRIPT: self._on_final_transcript,
            EventType.DIALOGUE_DRAFT_UPDATED: self._on_dialogue_draft_updated,
            EventType.RESPONSE_READY: self._on_response_ready,
            EventType.FLOOR_DECISION_EMITTED: self._on_floor_decision_emitted,
            EventType.STOP_TTS: self._on_stop_tts,
            EventType.TTS_STARTED: self._on_tts_started,
            EventType.TTS_FINISHED: self._on_tts_finished,
            EventType.REPLAN_REQUESTED: self._on_replan_requested,
            EventType.INPUT_FINISHED: self._on_input_finished,
        }

    async def emit(self, event: Event) -> None:
        await self.queue.put(event)

    async def run(self) -> None:
        await self.dialogue_worker.start(self.emit)
        await self.interrupt_worker.start(self.emit)
        await self.input_stream.start(self.emit)
        self._set_state(AssistantState.LISTENING, "system_start")
        logger.info("[ORCH] started")

        while True:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                if self._should_shutdown():
                    break
                await self._maybe_play_pending_full_reply("idle_tick")
                continue

            handler = self.handlers.get(event.type)
            if handler is None:
                logger.warning("[ORCH] unhandled event=%s", event.type)
                continue
            await handler(event)

        await self.shutdown()

    async def shutdown(self) -> None:
        await self.input_stream.stop()
        await self.interrupt_worker.stop()
        await self.dialogue_worker.stop()
        await self.playback.stop("orchestrator_shutdown", self.emit)
        logger.info("[ORCH] shutdown complete snapshot=%s", self.context.snapshot())

    def _set_state(self, new_state: AssistantState, reason: str) -> None:
        self.state_machine.transition(new_state, reason)
        self.context.state = self.state_machine.current

    def _should_shutdown(self) -> bool:
        if not self._input_finished:
            return False
        idle_long_enough = (
            asyncio.get_event_loop().time() - self._input_finished_ts
        ) >= self.settings.post_input_grace_seconds
        return idle_long_enough and not self.playback.is_playing() and self.queue.empty()

    async def _maybe_play_pending_full_reply(self, reason: str) -> None:
        if not self._pending_full_reply:
            return
        if self.context.user_speaking or self.playback.is_playing():
            return
        turn_id, reply = self._pending_full_reply
        self._pending_full_reply = None
        logger.info("[Turn granted to assistant] type=full_reply turn=%s reason=%s", turn_id, reason)
        await self.playback.play(turn_id, reply, self.emit)

    async def _on_user_speech_started(self, event: Event) -> None:
        self.context.current_turn_id = event.turn_id
        self.context.turn_started_at = event.timestamp
        self.context.floor_owner = "user"
        self.context.user_speaking = True
        self.context.latest_partial = ""
        self.context.latest_final = ""
        self.context.current_draft = DialogueDraft()
        self.context.last_user_speech_started_ts = event.timestamp
        logger.info("[TURN START] turn=%s owner=user", event.turn_id)
        self._set_state(AssistantState.USER_SPEAKING, "user_speech_started")

        if self.context.assistant_speaking or self.playback.is_playing():
            decision = FloorDecision(
                action=FloorAction.STOP_ASSISTANT,
                reason="speech_started_while_assistant_speaking",
                confidence=0.96,
                priority=105,
                should_stop_tts=True,
                should_replan=True,
            )
            await self.emit(
                self.event_factory.make(
                    EventType.FLOOR_DECISION_EMITTED,
                    event.turn_id,
                    {"decision": decision.to_dict()},
                )
            )

    async def _on_user_speech_stopped(self, event: Event) -> None:
        self.context.user_speaking = False
        self.context.last_user_speech_stopped_ts = event.timestamp
        logger.info("[ASR speech stopped] turn=%s", event.turn_id)
        self._set_state(AssistantState.USER_PAUSED, "user_speech_stopped")
        await self._maybe_play_pending_full_reply("user_speech_stopped")

    async def _on_partial_transcript(self, event: Event) -> None:
        text = (event.payload.get("text") or "").strip()
        if not text:
            return
        self.context.current_turn_id = event.turn_id
        self.context.mark_partial(text)
        logger.info("[ASR partial received] turn=%s text=%s", event.turn_id, text)
        await self.dialogue_worker.submit_partial(event.turn_id, text)

    async def _on_final_transcript(self, event: Event) -> None:
        text = (event.payload.get("text") or "").strip()
        if not text:
            return
        self.context.current_turn_id = event.turn_id
        self.context.mark_final(text)
        logger.info("[ASR final received] turn=%s text=%s", event.turn_id, text)
        self._set_state(AssistantState.ASSISTANT_PREPARING, "final_transcript")
        await self.dialogue_worker.submit_final(event.turn_id, text)

    async def _on_dialogue_draft_updated(self, event: Event) -> None:
        draft = self._draft_from_payload(event.payload.get("draft") or {})
        self.context.current_draft = draft
        self.context.response_draft = draft.short_reply_candidate or draft.rough_full_reply_candidate
        logger.info(
            "[Dialogue draft updated] turn=%s intent=%s confidence=%.2f short=%s clarify=%s rough_full=%s",
            event.turn_id,
            draft.intent_hypothesis,
            draft.intent_confidence,
            draft.short_reply_candidate,
            draft.clarification_candidate,
            draft.rough_full_reply_candidate,
        )

    async def _on_response_ready(self, event: Event) -> None:
        reply = (event.payload.get("reply") or "").strip()
        if not reply:
            return
        self.context.current_response_text = reply
        logger.info("[Response ready] turn=%s reply=%s", event.turn_id, reply)

        if self.context.user_speaking or self.playback.is_playing():
            self._pending_full_reply = (event.turn_id, reply)
            logger.info(
                "[Replan requested] turn=%s reason=full_reply_waits_for_floor owner=%s",
                event.turn_id,
                self.context.floor_owner,
            )
            return

        logger.info("[Turn granted to assistant] type=full_reply turn=%s", event.turn_id)
        self.context.floor_owner = "assistant"
        await self.playback.play(event.turn_id, reply, self.emit)

    async def _on_floor_decision_emitted(self, event: Event) -> None:
        decision = self._decision_from_payload(event.payload.get("decision") or {})
        self.context.last_floor_decision = decision
        logger.info("[Floor-taking decision emitted] turn=%s decision=%s", event.turn_id, decision.to_dict())

        if decision.action == FloorAction.NO_INTERRUPT:
            return
        if decision.should_stop_tts:
            logger.info("[Turn revoked from assistant] turn=%s reason=%s", event.turn_id, decision.reason)
            await self.playback.stop(decision.reason, self.emit)
            self.context.assistant_speaking = False
            self.context.floor_owner = "user"
            self._set_state(AssistantState.INTERRUPTED, decision.reason)
            if decision.should_replan:
                await self.emit(
                    self.event_factory.make(
                        EventType.REPLAN_REQUESTED,
                        event.turn_id,
                        {"reason": decision.reason},
                    )
                )
            return

        if not decision.candidate_text:
            return
        if self.playback.is_playing():
            return

        if decision.action == FloorAction.BACKCHANNEL:
            self.context.seen_backchannel_turns.add(event.turn_id)
            self.context.proactive_cooldown_until = now_ts() + self.settings.proactive_cooldown_ms / 1000
            logger.info(
                "[Turn granted to assistant] type=backchannel turn=%s reason=%s candidate_type=%s text=%s",
                event.turn_id,
                decision.reason,
                decision.candidate_type,
                decision.candidate_text,
            )
            await self.playback.play(f"{event.turn_id}-backchannel", decision.candidate_text, self.emit)
            return

        if decision.action in {FloorAction.SOFT_TAKE_FLOOR, FloorAction.HARD_TAKE_FLOOR}:
            self.context.taken_floor_turns.add(event.turn_id)
            self.context.proactive_cooldown_until = now_ts() + self.settings.proactive_cooldown_ms / 1000
            self.context.floor_owner = "assistant"
            self._set_state(AssistantState.ASSISTANT_PREPARING, decision.reason)
            logger.info(
                "[Turn granted to assistant] type=%s turn=%s reason=%s candidate_type=%s confidence=%.2f text=%s",
                decision.action,
                event.turn_id,
                decision.reason,
                decision.candidate_type,
                decision.confidence,
                decision.candidate_text,
            )
            await self.playback.play(f"{event.turn_id}-{decision.candidate_type}", decision.candidate_text, self.emit)

    async def _on_stop_tts(self, event: Event) -> None:
        reason = event.payload.get("reason", "unknown")
        logger.info("[TTS stopped] turn=%s reason=%s", event.turn_id, reason)
        await self.playback.stop(reason, self.emit)

    async def _on_tts_started(self, event: Event) -> None:
        self.context.assistant_speaking = True
        self.context.assistant_speaking_started_at = event.timestamp
        self.context.active_tts_turn_id = event.turn_id
        self.context.floor_owner = "assistant"
        logger.info("[TTS started] turn=%s", event.turn_id)
        self._set_state(AssistantState.ASSISTANT_SPEAKING, "tts_started")

    async def _on_tts_finished(self, event: Event) -> None:
        interrupted = bool(event.payload.get("interrupted"))
        self.context.assistant_speaking = False
        self.context.active_tts_turn_id = ""
        logger.info("[TTS finished] turn=%s interrupted=%s", event.turn_id, interrupted)
        if interrupted:
            self._set_state(AssistantState.REPLANNING, "tts_interrupted")
        elif self.context.user_speaking:
            self.context.floor_owner = "user"
            self._set_state(AssistantState.USER_SPEAKING, "tts_done_user_speaking")
        else:
            self.context.floor_owner = "none"
            self._set_state(AssistantState.IDLE, "tts_done")
        await self._maybe_play_pending_full_reply("tts_finished")

    async def _on_replan_requested(self, event: Event) -> None:
        reason = event.payload.get("reason", "unknown")
        self.context.last_replan_reason = reason
        logger.info("[Replan requested] turn=%s reason=%s latest_partial=%s", event.turn_id, reason, self.context.latest_partial)
        self._set_state(AssistantState.REPLANNING, reason)

    async def _on_input_finished(self, event: Event) -> None:
        self._input_finished = True
        self._input_finished_ts = asyncio.get_event_loop().time()
        logger.info("[INPUT FINISHED] source=%s", event.payload.get("source", "unknown"))

    def _draft_from_payload(self, payload: dict[str, Any]) -> DialogueDraft:
        return DialogueDraft(
            intent_hypothesis=str(payload.get("intent_hypothesis") or ""),
            intent_confidence=float(payload.get("intent_confidence") or 0.0),
            short_reply_candidate=str(payload.get("short_reply_candidate") or ""),
            clarification_candidate=str(payload.get("clarification_candidate") or ""),
            rough_full_reply_candidate=str(payload.get("rough_full_reply_candidate") or ""),
            missing_slots=tuple(payload.get("missing_slots") or ()),
            is_correction=bool(payload.get("is_correction")),
        )

    def _decision_from_payload(self, payload: dict[str, Any]) -> FloorDecision:
        return FloorDecision(
            action=FloorAction(payload.get("action") or FloorAction.NO_INTERRUPT),
            reason=str(payload.get("reason") or "unknown"),
            confidence=float(payload.get("confidence") or 0.0),
            priority=int(payload.get("priority") or 0),
            candidate_text=str(payload.get("candidate_text") or ""),
            candidate_type=CandidateType(payload.get("candidate_type") or CandidateType.NONE),
            should_stop_tts=bool(payload.get("should_stop_tts")),
            should_replan=bool(payload.get("should_replan")),
        )
