from pydantic import BaseModel
from typing import Literal, Optional


class InterruptRequest(BaseModel):
    partial_text: str
    assistant_speaking: bool
    playback_stage: Optional[str] = None
    asr_confidence: Optional[float] = None


class InterruptDecision(BaseModel):
    action: Literal["ignore", "duck", "pause", "takeover"]
    reason: str
    should_cancel_tts: bool = False


def classify_interrupt(req: InterruptRequest) -> InterruptDecision:
    text = req.partial_text.strip().lower()

    if not req.assistant_speaking:
        return InterruptDecision(
            action="ignore",
            reason="assistant_not_speaking",
            should_cancel_tts=False,
        )

    strong_takeover_phrases = [
        "stop",
        "wait",
        "hold on",
        "hang on",
        "等一下",
        "停一下",
        "不是",
        "先别说",
        "我想问",
        "等等",
    ]

    backchannel_phrases = [
        "嗯",
        "哦",
        "好",
        "ok",
        "okay",
        "yeah",
        "uh huh",
        "继续",
    ]

    if any(p in text for p in strong_takeover_phrases):
        return InterruptDecision(
            action="takeover",
            reason="strong_interrupt_phrase",
            should_cancel_tts=True,
        )

    if text in backchannel_phrases or len(text) <= 2:
        return InterruptDecision(
            action="duck",
            reason="possible_backchannel",
            should_cancel_tts=False,
        )

    return InterruptDecision(
        action="pause",
        reason="uncertain_interrupt",
        should_cancel_tts=False,
    )