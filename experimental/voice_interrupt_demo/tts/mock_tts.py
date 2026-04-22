from __future__ import annotations

import asyncio

from utils.logger import get_logger

logger = get_logger("mock_tts")


class MockTTS:
    def __init__(self, chars_per_second: float = 8.0) -> None:
        self.chars_per_second = max(chars_per_second, 1.0)

    async def speak(self, text: str, stop_event: asyncio.Event) -> None:
        text = text.strip()
        if not text:
            return

        logger.info("[TTS START] text=%s", text)
        chunks = self._chunk_text(text)
        for idx, chunk in enumerate(chunks):
            if stop_event.is_set():
                logger.info("[TTS STOPPED] before_chunk=%s", idx)
                return
            logger.info("[TTS CHUNK] %s", chunk)
            await asyncio.sleep(max(len(chunk) / self.chars_per_second, 0.12))
        logger.info("[TTS DONE] text_len=%s", len(text))

    def _chunk_text(self, text: str) -> list[str]:
        seps = "，。！？；,!?;"
        buff = ""
        out: list[str] = []
        for ch in text:
            buff += ch
            if ch in seps or len(buff) >= 16:
                out.append(buff)
                buff = ""
        if buff:
            out.append(buff)
        return out
