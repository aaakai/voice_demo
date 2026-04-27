from __future__ import annotations

import asyncio
from dataclasses import replace

from asr.asr_interface import EmitFn
from core.events import EventFactory, EventType
from scenarios import SCENARIOS
from scenarios.base import ScenarioStep
from utils.logger import get_logger

logger = get_logger("mock_asr")


class MockStreamingASR:
    def __init__(self, event_factory: EventFactory, scenario_name: str = "all") -> None:
        self.event_factory = event_factory
        self.scenario_name = scenario_name.lower()

    async def run(self, emit: EmitFn) -> None:
        logger.info("[ASR] start mock streaming scenario=%s", self.scenario_name)
        for step in self._build_script():
            await asyncio.sleep(step.delay_ms / 1000)
            payload = {"text": step.text} if step.text else {}
            await emit(self.event_factory.make(step.event_type, step.turn_id, payload))

        await asyncio.sleep(0.2)
        await emit(self.event_factory.make(EventType.INPUT_FINISHED, "system", {"source": "mock_asr"}))
        logger.info("[ASR] mock streaming scenario completed")

    def _build_script(self) -> list[ScenarioStep]:
        if self.scenario_name == "all":
            out: list[ScenarioStep] = []
            for index, name in enumerate(("1", "2", "3", "4", "5")):
                steps = SCENARIOS[name]()
                if index > 0 and steps:
                    steps[0] = replace(steps[0], delay_ms=steps[0].delay_ms + 7000)
                out.extend(steps)
            return out
        scenario_factory = SCENARIOS.get(self.scenario_name)
        if not scenario_factory:
            known = ", ".join(sorted(SCENARIOS))
            raise ValueError(f"Unknown scenario '{self.scenario_name}'. Known: {known}, all")
        return scenario_factory()
