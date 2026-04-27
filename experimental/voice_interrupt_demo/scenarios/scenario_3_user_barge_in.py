from __future__ import annotations

from scenarios.base import ScenarioStep, final, partial, start, stop


def scenario() -> list[ScenarioStep]:
    return [
        start(180, "s3-first"),
        partial(180, "s3-first", "请你详细讲讲这个系统"),
        final(220, "s3-first", "请你详细讲讲这个系统"),
        stop(80, "s3-first"),
        # Starts while the mock TTS is still speaking.
        start(900, "s3-barge"),
        partial(120, "s3-barge", "等等"),
        partial(180, "s3-barge", "等等我换个问题"),
        final(220, "s3-barge", "等等我换个问题，怎么快速接入真实语音"),
        stop(80, "s3-barge"),
    ]
