import json
from typing import Any, Iterator

from app.services.llm_service import (
    OPENROUTER_PLANNER_MODEL,
    generate_raw,
    generate_raw_openrouter,
    generate_reply,
    stream_generate_reply,
)
from app.tools.registry import TOOLS

ALLOWED_TOOL_NAMES = {"get_time", "get_weather_mock"}


def _build_planner_prompt(history, user_input: str) -> str:
    history_lines = []
    for msg in history[-6:]:
        history_lines.append(f"{msg.role}: {msg.text}")

    history_text = "\n".join(history_lines) if history_lines else "(empty)"

    return (
        "你是一个语音助手的规划器。\n"
        "你的任务：判断用户输入是直接回答，还是需要调用工具。\n"
        "你只能输出一个 JSON 对象，不要输出任何额外文本。\n"
        "\n"
        "可用工具：\n"
        "1) get_time()\n"
        "2) get_weather_mock(city: str)\n"
        "\n"
        "输出格式只能是以下两种之一：\n"
        "{\"type\":\"direct_answer\",\"reply\":\"...\"}\n"
        "{\"type\":\"tool_call\",\"tool_name\":\"get_time或get_weather_mock\",\"args\":{...}}\n"
        "\n"
        "规则：\n"
        "- 普通闲聊、常识问答，返回 direct_answer。\n"
        "- 问时间，优先 get_time。\n"
        "- 问天气，优先 get_weather_mock，并从用户输入提取 city。\n"
        "- 如果 city 不明确，可设为 \"本地\"。\n"
        "- reply 要简短、中文口语化。\n"
        "\n"
        f"历史对话：\n{history_text}\n"
        f"用户输入：{user_input}\n"
    )


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]

        if escaped:
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _parse_plan_json(raw_text: str) -> dict[str, Any] | None:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return None

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    candidate = _extract_first_json_object(raw_text)
    if not candidate:
        return None

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def plan_agent_action(history, user_input: str) -> dict[str, Any]:
    planner_prompt = _build_planner_prompt(history, user_input)
    try:
        raw_plan = generate_raw_openrouter(
            planner_prompt,
            model=OPENROUTER_PLANNER_MODEL,
        )
    except Exception as exc:  # noqa: BLE001
        print("agent planner openrouter fallback:", exc)
        try:
            # keep local fallback to avoid planner hard-failure
            raw_plan = generate_raw(planner_prompt)
        except Exception as inner_exc:  # noqa: BLE001
            print("agent planner ollama fallback failed:", inner_exc)
            return {"type": "direct_answer", "reply": ""}

    parsed = _parse_plan_json(raw_plan)

    if not isinstance(parsed, dict):
        return {"type": "direct_answer", "reply": ""}

    plan_type = parsed.get("type")

    if plan_type == "direct_answer":
        reply = parsed.get("reply", "")
        return {
            "type": "direct_answer",
            "reply": reply if isinstance(reply, str) else "",
        }

    if plan_type == "tool_call":
        tool_name = parsed.get("tool_name")
        args = parsed.get("args", {})

        if tool_name not in ALLOWED_TOOL_NAMES:
            return {"type": "direct_answer", "reply": ""}

        if not isinstance(args, dict):
            args = {}

        return {
            "type": "tool_call",
            "tool_name": tool_name,
            "args": args,
        }

    return {"type": "direct_answer", "reply": ""}


def generate_agent_reply(history, user_input: str) -> str:
    plan = plan_agent_action(history, user_input)
    print("agent_plan:", plan)

    if plan.get("type") == "direct_answer":
        reply = (plan.get("reply") or "").strip()
        if reply:
            return reply
        return generate_reply(history, user_input)

    tool_name = plan.get("tool_name", "")
    args = plan.get("args", {})

    tool = TOOLS.get(tool_name)
    if not tool:
        return generate_reply(history, user_input)

    try:
        if tool_name == "get_time":
            tool_result = tool()
        elif tool_name == "get_weather_mock":
            tool_result = tool(city=str(args.get("city", "本地")))
        else:
            return generate_reply(history, user_input)
    except Exception as exc:  # noqa: BLE001
        tool_result = f"工具执行失败: {exc}"

    print("tool_result:", tool_result)

    augmented_input = (
        f"用户问题：{user_input}\n"
        f"工具：{tool_name}\n"
        f"工具参数：{json.dumps(args, ensure_ascii=False)}\n"
        f"工具结果：{tool_result}\n"
        "请用简短、自然、适合语音播报的中文回答用户。"
    )

    return generate_reply(history, augmented_input)


def generate_agent_reply_stream(history, user_input: str, mode: str = "chat") -> Iterator[str]:
    if mode == "storytelling":
        story_input = (
            f"{user_input}\n"
            "要求：直接进入讲述内容，不要先说“好的我开始讲”。"
            "请按自然段推进剧情，适合语音连续播报。"
        )
        yield from stream_generate_reply(history, story_input, mode="storytelling")
        return

    plan = plan_agent_action(history, user_input)
    print("agent_plan:", plan)

    if plan.get("type") == "direct_answer":
        reply = (plan.get("reply") or "").strip()
        if reply:
            yield reply
            return
        yield from stream_generate_reply(history, user_input, mode=mode)
        return

    tool_name = plan.get("tool_name", "")
    args = plan.get("args", {})

    tool = TOOLS.get(tool_name)
    if not tool:
        yield from stream_generate_reply(history, user_input, mode=mode)
        return

    try:
        if tool_name == "get_time":
            tool_result = tool()
        elif tool_name == "get_weather_mock":
            tool_result = tool(city=str(args.get("city", "本地")))
        else:
            yield from stream_generate_reply(history, user_input, mode=mode)
            return
    except Exception as exc:  # noqa: BLE001
        tool_result = f"工具执行失败: {exc}"

    print("tool_result:", tool_result)

    augmented_input = (
        f"用户问题：{user_input}\n"
        f"工具：{tool_name}\n"
        f"工具参数：{json.dumps(args, ensure_ascii=False)}\n"
        f"工具结果：{tool_result}\n"
        "请用简短、自然、适合语音播报的中文回答用户。"
    )
    yield from stream_generate_reply(history, augmented_input, mode=mode)
