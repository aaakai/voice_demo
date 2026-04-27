from __future__ import annotations

import argparse
import asyncio
import logging

from asr.mock_streaming_asr import MockStreamingASR
from audio.input_stream import InputStreamController
from config import Settings
from core.context import SharedContext
from core.events import EventFactory
from core.orchestrator import Orchestrator
from dialogue.dialogue_worker import DialogueWorker
from dialogue.mock_llm import MockLLM
from interrupt.interrupt_worker import InterruptWorker
from tts.mock_tts import MockTTS
from tts.playback_controller import PlaybackController
from utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Voice interrupt demo (mock)")
    parser.add_argument("--mode", default="mock", choices=["mock"], help="Input mode")
    parser.add_argument("--scenario", default="all", help="1/2/3/4/5/all or named scenario")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()
    level = getattr(logging, args.log_level.upper(), logging.INFO)
    setup_logging(level=level)

    settings = Settings(mode=args.mode, scenario=args.scenario)
    context = SharedContext(session_id=settings.session_id)
    event_factory = EventFactory(session_id=settings.session_id)

    asr_provider = MockStreamingASR(event_factory=event_factory, scenario_name=settings.scenario)
    input_stream = InputStreamController(asr_provider)

    dialogue_worker = DialogueWorker(
        context=context,
        event_factory=event_factory,
        engine=MockLLM(),
    )
    interrupt_worker = InterruptWorker(
        context=context,
        settings=settings,
        event_factory=event_factory,
    )
    playback = PlaybackController(
        tts=MockTTS(chars_per_second=settings.tts_chars_per_second),
        event_factory=event_factory,
    )

    orchestrator = Orchestrator(
        settings=settings,
        context=context,
        event_factory=event_factory,
        input_stream=input_stream,
        dialogue_worker=dialogue_worker,
        interrupt_worker=interrupt_worker,
        playback=playback,
    )
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main_async())
