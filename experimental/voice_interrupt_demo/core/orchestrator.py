from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from audio.input_stream import InputStreamController
from config import Settings
from core.context import SharedContext
from core.events import Event, EventFactory, EventType
from core.state_machine import AssistantState, StateMachine
from dialogue.dialogue_worker import DialogueWorker
from interrupt.interrupt_worker import InterruptWorker
from tts.playback_controller import PlaybackController
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
        self.handlers: dict[str, HandlerFn] = {
            EventType.USER_SPEECH_STARTED: self._on_user_speech_started,
            EventType.USER_SPEECH_STOPPED: self._on_user_speech_stopped,
            EventType.PARTIAL_TRANSCRIPT: self._on_partial_transcript,
            EventType.FINAL_TRANSCRIPT: self._on_final_transcript,
            EventType.RESPONSE_DRAFT_UPDATED: self._on_response_draft_updated,
            EventType.RESPONSE_READY: self._on_response_ready,
            EventType.INTERRUPT_REQUESTED: self._on_interrupt_requested,
            EventType.INTERRUPT_APPROVED: self._on_interrupt_approved,
            EventType.STOP_TTS: self._on_stop_tts,
            EventType.TTS_STARTED: self._on_tts_started,
            EventType.TTS_FINISHED: self._on_tts_finished,
            EventType.REPLAN_REQUESTED: self._on_replan_requested,
            EventType.INPUT_FINISHED: self._on_input_finished,
        }

        self._input_finished = False
        self._input_finished_ts = 0.0
        self._pending_reply: tuple[str, str] | None = None

    async def emit(self, event: Event) -> None:
        await self.queue.put(event)

    async def run(self) -> None:
        await self.dialogue_worker.start(self.emit)
        await self.interrupt_worker.start(self.emit)
        await self.input_stream.start(self.emit)

        self.state_machine.transition(AssistantState.LISTENING, "system_start")
        self.context.state = self.state_machine.current

        logger.info("[ORCH] started")
        while True:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                if self._should_shutdown():
                    break
                await self._maybe_play_pending_reply("idle_tick")
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
        logger.info("[ORCH] shutdown complete")

    def _set_state(self, new_state: AssistantState, reason: str) -> None:
        self.state_machine.transition(new_state, reason)
        self.context.state = self.state_machine.current

    def _should_shutdown(self) -> bool:
        if not self._input_finished:
            return False
        grace = self.settings.post_input_grace_seconds
        idle_long_enough = (asyncio.get_event_loop().time() - self._input_finished_ts) >= grace
        if not idle_long_enough:
            return False
        nothing_running = (not self.playback.is_playing()) and self.queue.empty()
        return nothing_running

    async def _maybe_play_pending_reply(self, reason: str) -> None:
        if not self._pending_reply:
            return
        turn_id, reply = self._pending_reply
        if self.context.user_speaking:
            return
        if self.playback.is_playing():
            return
        self._pending_reply = None
        logger.info("[ORCH] play pending reply turn=%s reason=%s", turn_id, reason)
        await self.playback.play(turn_id, reply, self.emit)

    async def _on_user_speech_started(self, event: Event) -> None:
        self.context.current_turn_id = event.turn_id
        self.context.user_speaking = True
        self.context.last_user_speech_started_ts = event.timestamp
        self.context.latest_partial = ""
        self.context.latest_final = ""
        logger.info("[TURN START] turn=%s", event.turn_id)

        if self.context.assistant_speaking or self.playback.is_playing():
            logger.info("[INTERRUPT] detected while speaking, request stop")
            await self.emit(
                self.event_factory.make(
                    EventType.INTERRUPT_REQUESTED,
                    event.turn_id,
                    {"reason": "user_started_while_assistant_speaking"},
                )
            )
        self._set_state(AssistantState.LISTENING, "user_speech_started")

    async def _on_user_speech_stopped(self, event: Event) -> None:
        self.context.user_speaking = False
        self.context.last_user_speech_stopped_ts = event.timestamp
        logger.info("[ASR speech stopped] turn=%s", event.turn_id)
        await self._maybe_play_pending_reply("user_speech_stopped")

    async def _on_partial_transcript(self, event: Event) -> None:
        text = (event.payload.get("text") or "").strip()
        if not text:
            return
        self.context.current_turn_id = event.turn_id
        self.context.mark_partial(text)
        logger.info("[ASR partial] turn=%s text=%s", event.turn_id, text)
        await self.dialogue_worker.submit_partial(event.turn_id, text)

    async def _on_final_transcript(self, event: Event) -> None:
        text = (event.payload.get("text") or "").strip()
        if not text:
            return
        self.context.current_turn_id = event.turn_id
        self.context.mark_final(text)
        logger.info("[ASR final] turn=%s text=%s", event.turn_id, text)
        self._set_state(AssistantState.THINKING, "final_transcript")
        await self.dialogue_worker.submit_final(event.turn_id, text)

    async def _on_response_draft_updated(self, event: Event) -> None:
        draft = (event.payload.get("draft") or "").strip()
        if not draft:
            return
        self.context.response_draft = draft
        logger.info("[Draft] turn=%s draft=%s", event.turn_id, draft)

    async def _on_response_ready(self, event: Event) -> None:
        reply = (event.payload.get("reply") or "").strip()
        if not reply:
            return
        self.context.current_response_text = reply
        logger.info("[Response ready] turn=%s reply=%s", event.turn_id, reply)

        if self.context.user_speaking:
            self._pending_reply = (event.turn_id, reply)
            logger.info("[Replan trigger] user still speaking, queue reply turn=%s", event.turn_id)
            await self.emit(
                self.event_factory.make(
                    EventType.REPLAN_REQUESTED,
                    event.turn_id,
                    {"reason": "user_still_speaking", "reply": reply},
                )
            )
            return

        await self.playback.play(event.turn_id, reply, self.emit)

    async def _on_interrupt_requested(self, event: Event) -> None:
        reason = event.payload.get("reason", "unknown")
        self.context.last_interrupt_reason = reason
        self.context.barge_in_requested = True
        logger.info("[INTERRUPT requested] turn=%s reason=%s", event.turn_id, reason)
        self._set_state(AssistantState.INTERRUPTED, reason)
        await self.emit(
            self.event_factory.make(
                EventType.STOP_TTS,
                event.turn_id,
                {"reason": reason},
            )
        )
        await self.emit(
            self.event_factory.make(
                EventType.REPLAN_REQUESTED,
                event.turn_id,
                {"reason": f"interrupt:{reason}"},
            )
        )

    async def _on_interrupt_approved(self, event: Event) -> None:
        action = event.payload.get("action")
        if action != "backchannel":
            return

        reply = (event.payload.get("reply") or "").strip()
        if not reply:
            return
        if self.playback.is_playing():
            return
        turn_id = f"{event.turn_id}-bc"
        logger.info("[Interrupt approved] action=backchannel turn=%s reply=%s", turn_id, reply)
        await self.playback.play(turn_id, reply, self.emit)

    async def _on_stop_tts(self, event: Event) -> None:
        reason = event.payload.get("reason", "unknown")
        logger.info("[STOP TTS] turn=%s reason=%s", event.turn_id, reason)
        await self.playback.stop(reason, self.emit)

    async def _on_tts_started(self, event: Event) -> None:
        self.context.assistant_speaking = True
        self.context.active_tts_turn_id = event.turn_id
        logger.info("[TTS started] turn=%s", event.turn_id)
        self._set_state(AssistantState.SPEAKING, "tts_started")

    async def _on_tts_finished(self, event: Event) -> None:
        interrupted = bool(event.payload.get("interrupted"))
        self.context.assistant_speaking = False
        self.context.active_tts_turn_id = ""
        logger.info("[TTS finished] turn=%s interrupted=%s", event.turn_id, interrupted)
        if interrupted:
            self._set_state(AssistantState.REPLANNING, "tts_interrupted")
        elif self.context.user_speaking:
            self._set_state(AssistantState.LISTENING, "tts_done_user_speaking")
        else:
            self._set_state(AssistantState.IDLE, "tts_done")
        await self._maybe_play_pending_reply("tts_finished")

    async def _on_replan_requested(self, event: Event) -> None:
        reason = event.payload.get("reason", "unknown")
        self.context.last_replan_reason = reason
        logger.info("[Replan requested] turn=%s reason=%s", event.turn_id, reason)
        self._set_state(AssistantState.REPLANNING, reason)

    async def _on_input_finished(self, event: Event) -> None:
        self._input_finished = True
        self._input_finished_ts = asyncio.get_event_loop().time()
        logger.info("[INPUT FINISHED] source=%s", event.payload.get("source", "unknown"))
