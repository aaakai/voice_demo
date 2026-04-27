from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from config import Settings
from core.context import SharedContext
from core.events import Event, EventFactory, EventType
from core.decisions import FloorAction
from interrupt.floor_taking_policy import FloorTakingPolicy
from utils.logger import get_logger

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
        self.policy = FloorTakingPolicy(settings)
        self._task: asyncio.Task[None] | None = None
        self._last_decision_key: str = ""

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
        poll_s = self.settings.floor_policy_poll_ms / 1000
        while True:
            await asyncio.sleep(poll_s)
            await self._evaluate(emit)

    async def _evaluate(self, emit: EmitFn) -> None:
        turn_id = self.context.current_turn_id
        if not turn_id:
            return

        decision = self.policy.evaluate(self.context)
        self.context.last_floor_decision = decision

        if decision.action == FloorAction.NO_INTERRUPT:
            return

        decision_key = f"{turn_id}:{decision.action}:{decision.reason}:{decision.candidate_type}"
        if decision_key == self._last_decision_key:
            return
        self._last_decision_key = decision_key

        logger.info(
            "[Floor-taking decision emitted] turn=%s decision=%s",
            turn_id,
            decision.to_dict(),
        )
        await emit(
            self.event_factory.make(
                EventType.FLOOR_DECISION_EMITTED,
                turn_id,
                {"decision": decision.to_dict()},
            )
        )
