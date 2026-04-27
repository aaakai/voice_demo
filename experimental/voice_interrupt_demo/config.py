from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    session_id: str = "demo-session"
    mode: str = "mock"
    scenario: str = "all"
    floor_policy_poll_ms: int = 100
    user_pause_ms: int = 520
    soft_take_floor_pause_ms: int = 450
    hard_take_floor_pause_ms: int = 350
    clarify_pause_ms: int = 420
    backchannel_pause_min_ms: int = 450
    backchannel_pause_max_ms: int = 1200
    backchannel_min_confidence: float = 0.45
    soft_take_floor_min_confidence: float = 0.72
    hard_take_floor_min_confidence: float = 0.82
    proactive_cooldown_ms: int = 2400
    barge_in_text_min_len: int = 2
    assistant_too_long_ms: int = 4200
    tts_chars_per_second: float = 7.0
    post_input_grace_seconds: float = 5.0
