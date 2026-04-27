from __future__ import annotations

from core.decisions import DialogueDraft


CORRECTION_WORDS = ("不是", "不对", "等一下", "你先停", "先停", "错了", "纠正")
CITY_WORDS = ("北京", "上海", "广州", "深圳", "杭州")
TIME_WORDS = ("今天", "明天", "后天", "周末")


class ResponseDrafter:
    def draft_from_partial(self, text: str) -> DialogueDraft:
        t = text.strip()
        if not t:
            return DialogueDraft()

        is_correction = any(word in t for word in CORRECTION_WORDS)
        if is_correction:
            return DialogueDraft(
                intent_hypothesis="user_correction",
                intent_confidence=0.9,
                short_reply_candidate="好，我先停一下，刚才那个理解可能不对。",
                clarification_candidate="你纠正的是地点、时间，还是我刚才的结论？",
                rough_full_reply_candidate="我会按你最新纠正的信息重新回答。",
                missing_slots=(),
                is_correction=True,
            )

        if "天气" in t:
            missing: list[str] = []
            has_city = any(city in t for city in CITY_WORDS)
            has_time = any(time_word in t for time_word in TIME_WORDS)
            if not has_city:
                missing.append("city")
            if not has_time:
                missing.append("time")
            confidence = 0.84 if not missing else 0.62
            city = next((city for city in CITY_WORDS if city in t), "这个城市")
            time_word = next((word for word in TIME_WORDS if word in t), "对应时间")
            return DialogueDraft(
                intent_hypothesis="weather_query",
                intent_confidence=confidence,
                short_reply_candidate=f"{city}{time_word}的天气我可以直接帮你看。",
                clarification_candidate=self._weather_clarification(missing),
                rough_full_reply_candidate=f"{city}{time_word}大概率天气不错，我会补充温度和出行建议。",
                missing_slots=tuple(missing),
            )

        if any(word in t for word in ("怎么", "如何", "实现", "架构", "并行", "系统")):
            return DialogueDraft(
                intent_hypothesis="architecture_explanation",
                intent_confidence=0.78 if len(t) >= 10 else 0.55,
                short_reply_candidate="可以，我先直接说结论。",
                clarification_candidate="你想听整体架构，还是先看打断链路？",
                rough_full_reply_candidate="这个系统应该把主回复链路和抢话决策链路拆开，让它们通过共享上下文并行工作。",
            )

        if any(word in t for word in ("自我介绍", "你是谁", "介绍一下")):
            return DialogueDraft(
                intent_hypothesis="assistant_intro",
                intent_confidence=0.82,
                short_reply_candidate="好，我明白了，你想让我介绍自己。",
                rough_full_reply_candidate="我是一个用于验证实时抢话和可被打断能力的语音助手 demo。",
            )

        return DialogueDraft(
            intent_hypothesis="general_query",
            intent_confidence=min(0.35 + len(t) / 40, 0.68),
            short_reply_candidate="嗯，我大概明白你的方向了。",
            clarification_candidate="你希望我先回答结论，还是展开解释？",
            rough_full_reply_candidate=f"我理解你的问题和这段内容有关：{t}",
        )

    def final_reply(self, text: str, draft: DialogueDraft) -> str:
        t = text.strip()
        if draft.intent_hypothesis == "weather_query":
            city = next((city for city in CITY_WORDS if city in t), "你说的城市")
            time_word = next((word for word in TIME_WORDS if word in t), "那个时间")
            return f"{city}{time_word}我先按 mock 结果回答：天气偏晴，适合出门。我会建议你再确认一下实时天气。"
        if draft.intent_hypothesis == "architecture_explanation":
            return "结论是：主回复链路负责理解和生成候选，抢话链路独立评估 partial、停顿和纠正词。Orchestrator 只负责批准话轮切换和停止播放。"
        if draft.intent_hypothesis == "assistant_intro":
            return "我是一个实验型 voice assistant demo，重点不是模型多聪明，而是验证我能在 partial 阶段草拟、主动抢话，并且被用户打断后立刻重规划。"
        if draft.intent_hypothesis == "user_correction":
            return "收到，我会以你刚才纠正的内容为准，停止沿用之前的理解，然后重新组织回答。"
        return f"收到，我按你的完整输入来回答：{t}"

    def _weather_clarification(self, missing: list[str]) -> str:
        if missing == ["city", "time"]:
            return "你是想问哪个城市、今天还是明天？"
        if missing == ["city"]:
            return "你是想问北京还是上海，或者其他城市？"
        if missing == ["time"]:
            return "你问的是今天还是明天？"
        return "我先确认一下，你是在问天气对吗？"
