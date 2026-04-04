from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import base64
import json
import os
import requests

from app.interrupt.classifier import InterruptRequest, classify_interrupt
from app.memory.session_state import SessionState
from app.services.agent_service import generate_agent_reply_stream_with_meta
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


class StreamReplyAudioRequest(BaseModel):
    session_id: str
    user_text: str
    mode: str = "chat"


class RealtimeSessionRequest(BaseModel):
    session_id: str | None = None


class TTSProxyRequest(BaseModel):
    text: str


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
        text_stream, reply_meta = generate_agent_reply_stream_with_meta(
            session.history,
            user_text,
            mode=mode,
        )
        is_canonical = reply_meta.get("source") == "canonical_reply"
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
            if is_canonical:
                print("[reply chunk from canonical reply]", {"turn_id": turn_id, "text": chunk})
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


def _build_tts_payload(text: str) -> dict:
    return {
        "target_text": text,
        "prompt_id": [],
        "target_spk": "[S1]",
        "max_generate_length": 2000,
        "temperature": 1,
        "cfg_value": 2,
    }


def _open_tts_stream(text: str):
    tts_url = "http://43.166.165.224:8000/generate"
    payload = _build_tts_payload(text)
    return requests.post(
        tts_url,
        json=payload,
        stream=True,
        timeout=(10, 300),
    )


def stream_generated_reply_audio(
    session: SessionState,
    user_text: str,
    turn_id: str,
    mode: str = "chat",
):
    print("[stream_reply_audio start]", {"turn_id": turn_id, "mode": mode})
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
        text_stream, reply_meta = generate_agent_reply_stream_with_meta(
            session.history,
            user_text,
            mode=mode,
        )
        is_canonical = reply_meta.get("source") == "canonical_reply"
        for text_chunk in split_stream_for_tts(
            text_stream,
            max_len=18,
            soft_limit=10,
            hard_limit=24,
            min_chunk_len=3,
        ):
            if session.current_turn_id != turn_id:
                print("[stream_reply_audio cancelled]", {"turn_id": turn_id, "stage": "before_text"})
                yield json.dumps(
                    {
                        "type": "cancelled",
                        "turn_id": turn_id,
                    },
                    ensure_ascii=False,
                ) + "\n"
                return

            full_text += text_chunk
            if is_canonical:
                print("[reply chunk from canonical reply]", {"turn_id": turn_id, "text": text_chunk})
            print("[llm text chunk]", {"turn_id": turn_id, "len": len(text_chunk), "text": text_chunk})
            yield json.dumps(
                {
                    "type": "text_chunk",
                    "turn_id": turn_id,
                    "text": text_chunk,
                },
                ensure_ascii=False,
            ) + "\n"

            print("[tts request start]", {"turn_id": turn_id, "text_len": len(text_chunk)})
            upstream = None
            try:
                upstream = _open_tts_stream(text_chunk)
            except requests.RequestException as exc:
                print("[stream_reply_audio tts request error]", exc)
                continue

            if not upstream.ok:
                err_text = upstream.text
                upstream.close()
                print(
                    "[stream_reply_audio tts upstream error]",
                    {"status": upstream.status_code, "body": err_text},
                )
                continue

            try:
                for pcm in upstream.iter_content(chunk_size=4096):
                    if not pcm:
                        continue
                    if session.current_turn_id != turn_id:
                        print(
                            "[stream_reply_audio cancelled]",
                            {"turn_id": turn_id, "stage": "tts_stream"},
                        )
                        yield json.dumps(
                            {
                                "type": "cancelled",
                                "turn_id": turn_id,
                            },
                            ensure_ascii=False,
                        ) + "\n"
                        return

                    print("[tts pcm chunk bytes]", {"turn_id": turn_id, "bytes": len(pcm)})
                    yield json.dumps(
                        {
                            "type": "audio_chunk",
                            "turn_id": turn_id,
                            "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                        },
                        ensure_ascii=False,
                    ) + "\n"
            except requests.RequestException as exc:
                print("[stream_reply_audio tts stream error]", exc)
            finally:
                upstream.close()
    except Exception as exc:  # noqa: BLE001
        print("stream_generated_reply_audio error:", exc)
        fallback = "抱歉，刚刚网络有点波动，请再说一次。"
        full_text = fallback
        if session.current_turn_id == turn_id:
            yield json.dumps(
                {
                    "type": "text_chunk",
                    "turn_id": turn_id,
                    "text": fallback,
                },
                ensure_ascii=False,
            ) + "\n"

    if session.current_turn_id != turn_id:
        print("[stream_reply_audio cancelled]", {"turn_id": turn_id, "stage": "before_done"})
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

    print("[stream_reply_audio done]", {"turn_id": turn_id, "full_text_len": len(full_text)})
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


@app.post("/stream_reply_audio")
def stream_reply_audio(req: StreamReplyAudioRequest):
    session = sessions.setdefault(
        req.session_id,
        SessionState(session_id=req.session_id),
    )

    session.state = "thinking"
    turn_id = session.new_turn_id()

    return StreamingResponse(
        stream_generated_reply_audio(session, req.user_text, turn_id, mode=req.mode),
        media_type="application/x-ndjson",
    )


@app.post("/tts_proxy")
def tts_proxy(req: TTSProxyRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    payload = _build_tts_payload(text)
    tts_url = "http://43.166.165.224:8000/generate"
    print("tts proxy request start:", {"text_len": len(text)})

    try:
        upstream = requests.post(
            tts_url,
            json=payload,
            stream=True,
            timeout=(10, 300),
        )
    except requests.RequestException as exc:
        print("tts proxy error:", exc)
        raise HTTPException(status_code=502, detail=f"tts proxy request failed: {exc}") from exc

    if not upstream.ok:
        err_text = upstream.text
        upstream.close()
        print("tts proxy error:", {"status": upstream.status_code, "body": err_text})
        raise HTTPException(
            status_code=502,
            detail=f"tts upstream failed: status={upstream.status_code} body={err_text}",
        )

    def pcm_iter():
        print("tts proxy streaming response started")
        try:
            for chunk in upstream.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        except requests.RequestException as exc:
            print("tts proxy error:", exc)
        finally:
            upstream.close()

    return StreamingResponse(
        pcm_iter(),
        media_type="audio/L16;rate=24000;channels=1",
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
