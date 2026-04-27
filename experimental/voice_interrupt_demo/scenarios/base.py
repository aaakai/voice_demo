from __future__ import annotations

from dataclasses import dataclass

from core.events import EventType


@dataclass(slots=True)
class ScenarioStep:
    delay_ms: int
    event_type: EventType
    turn_id: str
    text: str = ""


def start(delay_ms: int, turn_id: str) -> ScenarioStep:
    return ScenarioStep(delay_ms, EventType.USER_SPEECH_STARTED, turn_id)


def stop(delay_ms: int, turn_id: str) -> ScenarioStep:
    return ScenarioStep(delay_ms, EventType.USER_SPEECH_STOPPED, turn_id)


def partial(delay_ms: int, turn_id: str, text: str) -> ScenarioStep:
    return ScenarioStep(delay_ms, EventType.PARTIAL_TRANSCRIPT, turn_id, text)


def final(delay_ms: int, turn_id: str, text: str) -> ScenarioStep:
    return ScenarioStep(delay_ms, EventType.FINAL_TRANSCRIPT, turn_id, text)
