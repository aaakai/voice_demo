from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import os
import requests

from app.interrupt.classifier import InterruptRequest, classify_interrupt
from app.memory.session_state import SessionState
from app.services.agent_service import generate_agent_reply_stream
from app.services.streaming_service import split_stream_for_tts

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions: dict[str, SessionState] = {}


class VoiceBrainRequest(BaseModel):
    session_id: str
    partial_text: str
    assistant_speaking: bool
    playback_stage: str = "idle"


class StreamReplyRequest(BaseModel):
    session_id: str
    user_text: str
    mode: str = "chat"


class RealtimeSessionRequest(BaseModel):
    session_id: str | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/decide")
def decide(req: VoiceBrainRequest) -> dict:
    session = sessions.setdefault(
        req.session_id,
        SessionState(session_id=req.session_id),
    )

    decision = classify_interrupt(
        InterruptRequest(
            partial_text=req.partial_text,
            assistant_speaking=req.assistant_speaking,
            playback_stage=req.playback_stage,
        )
    )

    should_generate = False

    if decision.action == "takeover":
        should_generate = True
    elif decision.action == "pause":
        should_generate = True
    elif not req.assistant_speaking:
        should_generate = True

    session.last_interrupt_action = decision.action
    session.playback_stage = req.playback_stage
    session.assistant_speaking = req.assistant_speaking

    if req.assistant_speaking:
        session.state = "speaking"
    else:
        session.state = "listening"

    if decision.action == "duck":
        session.state = "speaking"
    elif decision.action == "pause":
        session.state = "listening"
    elif decision.action == "takeover":
        session.state = "interrupted"

    if should_generate:
        session.state = "thinking"

    return {
        "interrupt_action": decision.action,
        "cancel_tts": decision.should_cancel_tts,
        "reason": decision.reason,
        "should_generate": should_generate,
        "response_text": "",
        "state": session.state,
        "current_turn_id": session.current_turn_id,
    }


def stream_generated_reply(session: SessionState, user_text: str, turn_id: str, mode: str = "chat"):
    # 先发一个 start 事件
    yield json.dumps(
        {
            "type": "start",
            "turn_id": turn_id,
        },
        ensure_ascii=False,
    ) + "\n"

    full_text = ""
    session.state = "speaking"
    session.assistant_speaking = True
    session.playback_stage = "tts_streaming"

    try:
        text_stream = generate_agent_reply_stream(session.history, user_text, mode=mode)
        for chunk in split_stream_for_tts(
            text_stream,
            max_len=18,
            soft_limit=12,
            hard_limit=28,
            min_chunk_len=4,
        ):
            # 如果当前 session 的 turn_id 已经变了，说明被新轮次替换，停止旧流
            if session.current_turn_id != turn_id:
                yield json.dumps(
                    {
                        "type": "cancelled",
                        "turn_id": turn_id,
                    },
                    ensure_ascii=False,
                ) + "\n"
                return

            full_text += chunk
            yield json.dumps(
                {
                    "type": "chunk",
                    "turn_id": turn_id,
                    "text": chunk,
                },
                ensure_ascii=False,
            ) + "\n"
    except Exception as exc:  # noqa: BLE001
        print("stream_generated_reply error:", exc)
        fallback = "抱歉，刚刚网络有点波动，请再说一次。"
        full_text = fallback
        if session.current_turn_id == turn_id:
            yield json.dumps(
                {
                    "type": "chunk",
                    "turn_id": turn_id,
                    "text": fallback,
                },
                ensure_ascii=False,
            ) + "\n"

    if session.current_turn_id != turn_id:
        yield json.dumps(
            {
                "type": "cancelled",
                "turn_id": turn_id,
            },
            ensure_ascii=False,
        ) + "\n"
        return

    session.add_user_message(user_text)
    session.add_assistant_message(full_text)
    session.last_assistant_reply = full_text
    session.assistant_speaking = False
    session.playback_stage = "idle"
    session.state = "idle"

    yield json.dumps(
        {
            "type": "done",
            "turn_id": turn_id,
            "full_text": full_text,
        },
        ensure_ascii=False,
    ) + "\n"


@app.post("/stream_reply")
def stream_reply(req: StreamReplyRequest):
    session = sessions.setdefault(
        req.session_id,
        SessionState(session_id=req.session_id),
    )

    session.state = "thinking"
    turn_id = session.new_turn_id()

    return StreamingResponse(
        stream_generated_reply(session, req.user_text, turn_id, mode=req.mode),
        media_type="application/x-ndjson",
    )


@app.post("/realtime/session")
def create_realtime_session(_: RealtimeSessionRequest) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")

    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
    transcription_model = os.getenv(
        "OPENAI_REALTIME_TRANSCRIPTION_MODEL",
        "gpt-4o-mini-transcribe",
    )

    payload = {
        "session": {
            "type": "realtime",
            "model": model,
            "audio": {
                "input": {
                    "turn_detection": {
                        "type": "semantic_vad",
                        "create_response": False,
                        "interrupt_response": False,
                    },
                    "transcription": {"model": transcription_model},
                }
            },
        }
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/realtime/client_secrets",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        print("realtime_session_openai_raw:", data)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"create realtime session failed: {exc}") from exc

    client_secret = data.get("value")
    print("realtime_session_client_secret_extracted:", bool(client_secret))
    if not client_secret:
        raise HTTPException(status_code=502, detail="realtime session missing client_secret")

    return {
        "client_secret": client_secret,
        "model": model,
        "session": data.get("session") or {},
    }
