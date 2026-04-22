from __future__ import annotations

from typing import Protocol

from core.context import SharedContext


class DialogueEngine(Protocol):
    async def generate_draft(self, partial_text: str, context: SharedContext) -> str:
        ...

    async def generate_final(self, final_text: str, context: SharedContext) -> str:
        ...
