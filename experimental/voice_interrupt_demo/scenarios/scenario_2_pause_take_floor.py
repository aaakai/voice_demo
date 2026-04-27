from __future__ import annotations

from scenarios.base import ScenarioStep, final, partial, start, stop


def scenario() -> list[ScenarioStep]:
    return [
        start(200, "s2-pause"),
        partial(220, "s2-pause", "我想问一下"),
        partial(260, "s2-pause", "我想问一下北京明天的天气"),
        # The pause after this partial gives the floor-taking policy room to act.
        partial(1200, "s2-pause", "我想问一下北京明天的天气还有出门建议"),
        final(420, "s2-pause", "我想问一下北京明天的天气还有出门建议"),
        stop(80, "s2-pause"),
    ]
