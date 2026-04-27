from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from core.context import SharedContext
from core.events import Event, EventFactory, EventType
from dialogue.dialogue_interface import DialogueEngine
from utils.logger import get_logger

logger = get_logger("dialogue")
EmitFn = Callable[[Event], Awaitable[None]]


@dataclass(slots=True)
class DialogueInput:
    kind: str  # partial|final
    turn_id: str
    text: str


class DialogueWorker:
    def __init__(
        self,
        context: SharedContext,
        event_factory: EventFactory,
        engine: DialogueEngine,
    ) -> None:
        self.context = context
        self.event_factory = event_factory
        self.engine = engine
        self.queue: asyncio.Queue[DialogueInput] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self, emit: EmitFn) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(emit), name="dialogue-worker")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def submit_partial(self, turn_id: str, text: str) -> None:
        await self.queue.put(DialogueInput(kind="partial", turn_id=turn_id, text=text))

    async def submit_final(self, turn_id: str, text: str) -> None:
        await self.queue.put(DialogueInput(kind="final", turn_id=turn_id, text=text))

    async def _run(self, emit: EmitFn) -> None:
        while True:
            item = await self.queue.get()
            if item.kind == "partial":
                await self._handle_partial(item, emit)
            else:
                await self._handle_final(item, emit)

    async def _handle_partial(self, item: DialogueInput, emit: EmitFn) -> None:
        draft = await self.engine.generate_draft(item.text, self.context)
        if not draft.intent_hypothesis:
            return
        logger.info(
            "[Intent hypothesis updated] turn=%s intent=%s confidence=%.2f missing=%s",
            item.turn_id,
            draft.intent_hypothesis,
            draft.intent_confidence,
            ",".join(draft.missing_slots) or "-",
        )
        logger.info(
            "[Dialogue draft updated] turn=%s short=%s clarify=%s rough_full=%s",
            item.turn_id,
            draft.short_reply_candidate,
            draft.clarification_candidate,
            draft.rough_full_reply_candidate,
        )
        event = self.event_factory.make(
            EventType.DIALOGUE_DRAFT_UPDATED,
            item.turn_id,
            {"draft": draft.to_dict()},
        )
        await emit(event)

    async def _handle_final(self, item: DialogueInput, emit: EmitFn) -> None:
        logger.info("[Dialogue final request] turn=%s text=%s", item.turn_id, item.text)
        reply = await self.engine.generate_final(item.text, self.context)
        logger.info("[Dialogue final reply] turn=%s reply=%s", item.turn_id, reply)
        event = self.event_factory.make(
            EventType.RESPONSE_READY,
            item.turn_id,
            {"reply": reply},
        )
        await emit(event)
