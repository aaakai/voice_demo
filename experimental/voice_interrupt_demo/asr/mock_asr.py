from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from asr.asr_interface import EmitFn
from core.events import EventFactory, EventType
from utils.logger import get_logger

logger = get_logger("mock_asr")


@dataclass(slots=True)
class ScriptStep:
    delay_ms: int
    event_type: EventType
    turn_id: str
    payload: dict[str, str]


class MockASRProvider:
    def __init__(self, event_factory: EventFactory, scenario: str = "all") -> None:
        self.event_factory = event_factory
        self.scenario = scenario.lower()

    async def run(self, emit: EmitFn) -> None:
        logger.info("[ASR] start mock scenario=%s", self.scenario)
        for step in self._build_script(self.scenario):
            await asyncio.sleep(step.delay_ms / 1000)
            event = self.event_factory.make(step.event_type, step.turn_id, step.payload)
            await emit(event)

        await asyncio.sleep(0.2)
        await emit(self.event_factory.make(EventType.INPUT_FINISHED, "system", {"source": "mock_asr"}))
        logger.info("[ASR] mock scenario completed")

    def _build_script(self, scenario: str) -> Iterable[ScriptStep]:
        a = [
            ScriptStep(200, EventType.USER_SPEECH_STARTED, "turn-a", {}),
            ScriptStep(180, EventType.PARTIAL_TRANSCRIPT, "turn-a", {"text": "请你做个"}),
            ScriptStep(200, EventType.PARTIAL_TRANSCRIPT, "turn-a", {"text": "请你做个自我介绍"}),
            ScriptStep(220, EventType.FINAL_TRANSCRIPT, "turn-a", {"text": "请你做个自我介绍"}),
            ScriptStep(80, EventType.USER_SPEECH_STOPPED, "turn-a", {}),
        ]

        b = [
            ScriptStep(300, EventType.USER_SPEECH_STARTED, "turn-b", {}),
            ScriptStep(180, EventType.PARTIAL_TRANSCRIPT, "turn-b", {"text": "我想了解一下"}),
            ScriptStep(900, EventType.PARTIAL_TRANSCRIPT, "turn-b", {"text": "我想了解一下这个系统怎么做到并行"}),
            ScriptStep(380, EventType.PARTIAL_TRANSCRIPT, "turn-b", {"text": "我想了解一下这个系统怎么做到并行处理语音"}),
            ScriptStep(260, EventType.FINAL_TRANSCRIPT, "turn-b", {"text": "我想了解一下这个系统怎么做到并行处理语音"}),
            ScriptStep(100, EventType.USER_SPEECH_STOPPED, "turn-b", {}),
        ]

        c = [
            ScriptStep(400, EventType.USER_SPEECH_STARTED, "turn-c", {}),
            ScriptStep(180, EventType.PARTIAL_TRANSCRIPT, "turn-c", {"text": "请你详细讲讲"}),
            ScriptStep(180, EventType.FINAL_TRANSCRIPT, "turn-c", {"text": "请你详细讲讲这个系统"}),
            ScriptStep(60, EventType.USER_SPEECH_STOPPED, "turn-c", {}),
            ScriptStep(680, EventType.USER_SPEECH_STARTED, "turn-c2", {}),
            ScriptStep(140, EventType.PARTIAL_TRANSCRIPT, "turn-c2", {"text": "等等我换个问题"}),
            ScriptStep(220, EventType.FINAL_TRANSCRIPT, "turn-c2", {"text": "等等我换个问题，怎么快速接入"}),
            ScriptStep(80, EventType.USER_SPEECH_STOPPED, "turn-c2", {}),
        ]

        if scenario == "a":
            return a
        if scenario == "b":
            return b
        if scenario == "c":
            return c
        bridge_1 = [ScriptStep(2100, EventType.USER_SPEECH_STARTED, "turn-b", {})]
        bridge_2 = [ScriptStep(2000, EventType.USER_SPEECH_STARTED, "turn-c", {})]
        b_without_start = [step for step in b if step.event_type != EventType.USER_SPEECH_STARTED]
        c_without_start = [step for step in c if step.turn_id != "turn-c" or step.event_type != EventType.USER_SPEECH_STARTED]
        return [*a, *bridge_1, *b_without_start, *bridge_2, *c_without_start]
