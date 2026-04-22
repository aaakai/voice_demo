from __future__ import annotations

from typing import Awaitable, Callable, Protocol

from core.events import Event

EmitFn = Callable[[Event], Awaitable[None]]


class ASRProvider(Protocol):
    async def run(self, emit: EmitFn) -> None:
        ...
