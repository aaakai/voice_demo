from __future__ import annotations

from scenarios.base import ScenarioStep, final, partial, start, stop


def scenario() -> list[ScenarioStep]:
    return [
        start(200, "s5-correct"),
        partial(180, "s5-correct", "不是北京"),
        partial(560, "s5-correct", "不是北京，不对，是上海明天的天气"),
        final(420, "s5-correct", "不是北京，不对，是上海明天的天气"),
        stop(80, "s5-correct"),
    ]
