import os
import json
from typing import Iterator
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_PLANNER_MODEL = os.getenv("OPENROUTER_PLANNER_MODEL", OPENROUTER_MODEL)


def build_prompt(history, user_input: str) -> str:
    lines = [
        "You are a real-time voice assistant.",
        "Reply in Chinese.",
        "Keep replies short and natural.",
        "Prefer 3 to 5 short sentences.",
        "Be interruption-aware.",
        "",
    ]

    for msg in history[-6:]:
        lines.append(f"{msg.role}: {msg.text}")

    lines.append(f"user: {user_input}")
    lines.append("assistant:")
    return "\n".join(lines)


def generate_raw(prompt: str) -> str:
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["response"].strip()


def generate_reply(history, user_input: str) -> str:
    prompt = build_prompt(history, user_input)
    return generate_raw(prompt)


def generate_raw_openrouter(prompt: str, model: str | None = None) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    req_model = model or OPENROUTER_MODEL
    payload = {
        "model": req_model,
        "messages": [
            {
                "role": "system",
                "content": "You are a precise assistant. Return concise output.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
    }

    print("openrouter non-stream request started:", {"model": req_model})
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(
                f"openrouter non-stream error: status={resp.status_code} body={resp.text}"
            )
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return (content or "").strip()
    except requests.RequestException as exc:
        raise RuntimeError(f"openrouter non-stream request failed: {exc}") from exc


def _build_openrouter_messages(history, user_input: str, mode: str = "chat") -> list[dict]:
    if mode == "storytelling":
        system_content = (
            "你是一个实时语音讲述助手，当前处于 storytelling 模式。"
            "不要先说“好的/那我开始讲”等确认句，直接进入故事内容。"
            "讲述要口语化、有画面感、推进自然，适合分段流式播报。"
            "单次输出控制在中等长度，避免一大段。"
        )
    else:
        system_content = (
            "你是一个实时语音助手。"
            "请用中文简洁回答，口语化，自然，适合语音播报。"
        )

    messages: list[dict] = [
        {
            "role": "system",
            "content": system_content,
        }
    ]

    for msg in history[-8:]:
        messages.append({"role": msg.role, "content": msg.text})

    messages.append({"role": "user", "content": user_input})
    return messages


def stream_generate_reply(history, user_input: str, mode: str = "chat") -> Iterator[str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    model = os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL)
    payload = {
        "model": model,
        "messages": _build_openrouter_messages(history, user_input, mode=mode),
        "stream": True,
    }

    print("openrouter request started:", {"model": model})

    try:
        with requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=True,
            timeout=(15, 300),
        ) as resp:
            if not resp.ok:
                err_text = resp.text
                raise RuntimeError(
                    f"openrouter pre-stream error: status={resp.status_code} body={err_text}"
                )

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue

                line = raw_line.strip()
                if not line:
                    continue

                # Ignore SSE comments, e.g. ": OPENROUTER PROCESSING"
                if line.startswith(":"):
                    continue

                if not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if not data_str:
                    continue

                if data_str == "[DONE]":
                    print("openrouter stream done")
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    # Ignore malformed line; keep stream alive
                    print("openrouter stream json parse skipped")
                    continue

                if isinstance(data, dict) and data.get("error"):
                    print("openrouter mid-stream error:", data.get("error"))
                    break

                try:
                    delta = data["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, AttributeError, TypeError):
                    delta = ""

                if delta:
                    print("openrouter stream chunk received:", len(delta))
                    yield delta
    except requests.RequestException as exc:
        raise RuntimeError(f"openrouter stream request failed: {exc}") from exc
