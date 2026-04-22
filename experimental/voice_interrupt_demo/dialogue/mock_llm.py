from __future__ import annotations

import asyncio

from core.context import SharedContext
from dialogue.dialogue_interface import DialogueEngine


class MockLLM(DialogueEngine):
    async def generate_draft(self, partial_text: str, context: SharedContext) -> str:
        await asyncio.sleep(0.05)
        partial = partial_text.strip()
        if len(partial) < 4:
            return ""
        return f"我在听，你可能想问：{partial[:16]}"

    async def generate_final(self, final_text: str, context: SharedContext) -> str:
        await asyncio.sleep(0.15)
        text = final_text.strip()
        if "自我介绍" in text:
            return "你好，我是一个用于验证主动打断架构的语音助手 demo。我支持并行草拟回复、打断判断，以及被用户插话时立刻停播重规划。"
        if "并行" in text or "系统" in text:
            return "这个 demo 的核心是事件驱动状态机。主回复链路负责理解和生成内容，打断链路并行监控语音状态，一旦检测到插话就立即发出停播和重规划信号。"
        if "怎么快速接入" in text or "接入" in text:
            return "你可以先用 mock ASR 跑通全链路，再把 ASR、LLM、TTS 分别替换成真实服务。因为模块边界已经隔离，替换成本会比较低。"
        return f"收到，你说的是：{text}。我会先基于 partial 草拟，再在 final 到达后给你完整回复。"
