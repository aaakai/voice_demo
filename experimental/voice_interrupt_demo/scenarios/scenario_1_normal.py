from __future__ import annotations

from scenarios.base import ScenarioStep, final, partial, start, stop


def scenario() -> list[ScenarioStep]:
    return [
        start(200, "s1-normal"),
        partial(220, "s1-normal", "请你做个"),
        partial(260, "s1-normal", "请你做个自我介绍"),
        final(360, "s1-normal", "请你做个自我介绍"),
        stop(80, "s1-normal"),
    ]
