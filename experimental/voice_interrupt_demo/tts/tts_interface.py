from __future__ import annotations

from typing import Protocol


class TTSInterface(Protocol):
    async def speak(self, text: str, stop_event) -> None:
        ...
