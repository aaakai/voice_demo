from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable

from config import Settings
from core.context import SharedContext
from core.events import Event, EventFactory, EventType
from interrupt.policies import BACKCHANNEL_CANDIDATES, should_offer_backchannel, should_request_barge_in
from utils.logger import get_logger
from utils.timers import elapsed_ms, now_ts

logger = get_logger("interrupt")
EmitFn = Callable[[Event], Awaitable[None]]


class InterruptWorker:
    def __init__(
        self,
        context: SharedContext,
        settings: Settings,
        event_factory: EventFactory,
    ) -> None:
        self.context = context
        self.settings = settings
        self.event_factory = event_factory
        self._task: asyncio.Task[None] | None = None
        self._last_barge_in_turn_id: str = ""

    async def start(self, emit: EmitFn) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(emit), name="interrupt-worker")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self, emit: EmitFn) -> None:
        poll_s = self.settings.interrupt_poll_ms / 1000
        while True:
            await asyncio.sleep(poll_s)
            await self._evaluate(emit)

    async def _evaluate(self, emit: EmitFn) -> None:
        turn_id = self.context.current_turn_id
        if not turn_id:
            return

        if should_request_barge_in(self.context, self.settings.barge_in_text_min_len):
            if self._last_barge_in_turn_id != turn_id:
                self._last_barge_in_turn_id = turn_id
                logger.info("[Interrupt trigger] reason=user_barge_in turn=%s", turn_id)
                await emit(
                    self.event_factory.make(
                        EventType.INTERRUPT_REQUESTED,
                        turn_id,
                        {"reason": "user_barge_in"},
                    )
                )
            return

        if self.context.last_partial_ts <= 0:
            return

        pause_ms = elapsed_ms(self.context.last_partial_ts)
        if not should_offer_backchannel(
            self.context,
            pause_ms=pause_ms,
            text_len_min=self.settings.proactive_text_min_len,
            pause_min_ms=self.settings.proactive_pause_min_ms,
            pause_max_ms=self.settings.proactive_pause_max_ms,
        ):
            return

        if turn_id in self.context.seen_backchannel_turns:
            return

        backchannel = random.choice(BACKCHANNEL_CANDIDATES)
        self.context.seen_backchannel_turns.add(turn_id)
        self.context.proactive_cooldown_until = now_ts() + (self.settings.proactive_cooldown_ms / 1000)
        logger.info(
            "[Interrupt approved] action=backchannel turn=%s pause_ms=%s text=%s",
            turn_id,
            pause_ms,
            self.context.latest_partial,
        )
        await emit(
            self.event_factory.make(
                EventType.INTERRUPT_APPROVED,
                turn_id,
                {
                    "action": "backchannel",
                    "reply": backchannel,
                    "reason": "user_pause_detected",
                    "pause_ms": str(pause_ms),
                },
            )
        )
