from __future__ import annotations

from core.context import SharedContext
from core.decisions import DialogueDraft
from dialogue.dialogue_interface import DialogueEngine
from dialogue.response_drafter import ResponseDrafter


class MockLLM(DialogueEngine):
    def __init__(self) -> None:
        self.drafter = ResponseDrafter()

    async def generate_draft(self, partial_text: str, context: SharedContext) -> DialogueDraft:
        return self.drafter.draft_from_partial(partial_text)

    async def generate_final(self, final_text: str, context: SharedContext) -> str:
        return self.drafter.final_reply(final_text, context.current_draft)
