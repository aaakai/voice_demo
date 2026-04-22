from __future__ import annotations

from core.context import SharedContext


BACKCHANNEL_CANDIDATES = ("嗯，我在听。", "好的，你继续。", "明白，接着说。")


def should_request_barge_in(context: SharedContext, min_len: int) -> bool:
    if context.active_tts_turn_id.endswith("-bc"):
        return False
    return (
        context.assistant_speaking
        and context.user_speaking
        and len(context.latest_partial.strip()) >= min_len
    )


def should_offer_backchannel(
    context: SharedContext,
    pause_ms: int,
    text_len_min: int,
    pause_min_ms: int,
    pause_max_ms: int,
) -> bool:
    text = context.latest_partial.strip()
    if context.assistant_speaking:
        return False
    if not context.user_speaking:
        return False
    if context.cooldown_active():
        return False
    if len(text) < text_len_min:
        return False
    return pause_min_ms <= pause_ms <= pause_max_ms
