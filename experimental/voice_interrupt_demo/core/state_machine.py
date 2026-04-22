from __future__ import annotations

from enum import StrEnum

from utils.logger import get_logger

logger = get_logger("state")


class AssistantState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    REPLANNING = "replanning"


class StateMachine:
    def __init__(self) -> None:
        self.current: AssistantState = AssistantState.IDLE

    def transition(self, new_state: AssistantState, reason: str) -> None:
        if new_state == self.current:
            return
        old = self.current
        self.current = new_state
        logger.info("[STATE] %s -> %s | reason=%s", old, new_state, reason)
