from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    session_id: str = "demo-session"
    mode: str = "mock"
    scenario: str = "all"
    interrupt_poll_ms: int = 120
    proactive_pause_min_ms: int = 450
    proactive_pause_max_ms: int = 1300
    proactive_text_min_len: int = 6
    proactive_cooldown_ms: int = 2800
    barge_in_text_min_len: int = 2
    tts_chars_per_second: float = 8.0
    post_input_grace_seconds: float = 8.0
