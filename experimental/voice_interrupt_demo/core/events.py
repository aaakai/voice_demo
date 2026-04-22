from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from utils.timers import now_ts


class EventType(StrEnum):
    USER_SPEECH_STARTED = "user_speech_started"
    USER_SPEECH_STOPPED = "user_speech_stopped"
    PARTIAL_TRANSCRIPT = "partial_transcript"
    FINAL_TRANSCRIPT = "final_transcript"
    RESPONSE_DRAFT_UPDATED = "response_draft_updated"
    RESPONSE_READY = "response_ready"
    INTERRUPT_REQUESTED = "interrupt_requested"
    INTERRUPT_APPROVED = "interrupt_approved"
    STOP_TTS = "stop_tts"
    TTS_STARTED = "tts_started"
    TTS_FINISHED = "tts_finished"
    REPLAN_REQUESTED = "replan_requested"
    INPUT_FINISHED = "input_finished"


@dataclass(slots=True)
class Event:
    type: str
    session_id: str
    turn_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=now_ts)


class EventFactory:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def make(self, event_type: str, turn_id: str, payload: dict[str, Any] | None = None) -> Event:
        return Event(
            type=event_type,
            session_id=self.session_id,
            turn_id=turn_id,
            payload=payload or {},
        )
