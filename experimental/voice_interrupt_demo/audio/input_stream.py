from __future__ import annotations

import asyncio

from asr.asr_interface import ASRProvider, EmitFn
from utils.logger import get_logger

logger = get_logger("input")


class InputStreamController:
    """Controls the selected input source (mock by default)."""

    def __init__(self, provider: ASRProvider) -> None:
        self.provider = provider
        self._task: asyncio.Task[None] | None = None

    async def start(self, emit: EmitFn) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self.provider.run(emit), name="input-stream")
        logger.info("[INPUT] started")

    async def wait_finished(self) -> None:
        if not self._task:
            return
        await self._task

    async def stop(self) -> None:
        if not self._task:
            return
        if not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[INPUT] stopped")
