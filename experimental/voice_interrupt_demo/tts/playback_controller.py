from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from core.events import Event, EventFactory, EventType
from tts.tts_interface import TTSInterface
from utils.logger import get_logger

logger = get_logger("playback")
EmitFn = Callable[[Event], Awaitable[None]]


class PlaybackController:
    def __init__(self, tts: TTSInterface, event_factory: EventFactory) -> None:
        self.tts = tts
        self.event_factory = event_factory
        self._current_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._current_turn_id: str = ""

    @property
    def current_turn_id(self) -> str:
        return self._current_turn_id

    def is_playing(self) -> bool:
        return bool(self._current_task and not self._current_task.done())

    async def play(self, turn_id: str, text: str, emit: EmitFn) -> None:
        await self.stop("preempt", emit)
        self._stop_event = asyncio.Event()
        self._current_turn_id = turn_id
        self._current_task = asyncio.create_task(
            self._run(turn_id, text, emit),
            name=f"playback-{turn_id}",
        )

    async def stop(self, reason: str, emit: EmitFn) -> None:
        if not self.is_playing():
            return
        turn_id = self._current_turn_id
        self._stop_event.set()
        task = self._current_task
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("[PCM STOP] turn=%s reason=%s", turn_id, reason)

    async def _run(self, turn_id: str, text: str, emit: EmitFn) -> None:
        await emit(self.event_factory.make(EventType.TTS_STARTED, turn_id, {"text": text}))
        interrupted = False
        try:
            await self.tts.speak(text, self._stop_event)
            interrupted = self._stop_event.is_set()
        except Exception as exc:  # pragma: no cover - demo fallback
            interrupted = True
            logger.exception("[TTS ERROR] turn=%s err=%s", turn_id, exc)
        finally:
            await emit(
                self.event_factory.make(
                    EventType.TTS_FINISHED,
                    turn_id,
                    {"interrupted": interrupted, "text": text},
                )
            )
            self._current_turn_id = ""
            self._current_task = None
