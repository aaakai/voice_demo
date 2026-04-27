from __future__ import annotations

from scenarios.base import ScenarioStep, final, partial, start, stop


def scenario() -> list[ScenarioStep]:
    return [
        start(200, "s4-clarify"),
        partial(220, "s4-clarify", "我想问天气"),
        # Missing city and time; policy should proactively ask for slots.
        partial(1000, "s4-clarify", "我想问天气大概怎么样"),
        final(520, "s4-clarify", "我想问天气大概怎么样"),
        stop(80, "s4-clarify"),
    ]
