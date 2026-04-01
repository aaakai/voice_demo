import re
from typing import Iterable, Iterator, List


def split_text_for_tts(text: str, max_len: int = 24) -> List[str]:
    """
    Split text into short TTS-friendly chunks.
    Priority:
    1. Chinese/English punctuation
    2. Length fallback
    """
    text = (text or "").strip()
    if not text:
        return []

    # 先按中英文标点切
    parts = re.split(r"([，。！？；：,.!?;:])", text)

    merged: List[str] = []
    buf = ""

    for part in parts:
        if not part:
            continue

        # 标点直接拼回前一句
        if re.fullmatch(r"[，。！？；：,.!?;:]", part):
            buf += part
            if buf.strip():
                merged.append(buf.strip())
            buf = ""
            continue

        # 普通文本
        if len(buf) + len(part) <= max_len:
            buf += part
        else:
            if buf.strip():
                merged.append(buf.strip())

            # 如果单段本身太长，再按长度硬切
            while len(part) > max_len:
                merged.append(part[:max_len].strip())
                part = part[max_len:]

            buf = part

    if buf.strip():
        merged.append(buf.strip())

    return [x for x in merged if x]


def split_stream_for_tts(
    text_stream: Iterable[str],
    max_len: int = 18,
    soft_limit: int = 12,
    hard_limit: int = 28,
    min_chunk_len: int = 4,
) -> Iterator[str]:
    """
    Convert token stream to TTS-friendly chunks.
    Priority:
    1. Strong punctuation: 。！？!?\\n
    2. Weak punctuation: ，、,；;：
    3. Length fallback when no punctuation arrives for a while
    """
    buffer = ""
    strong_punc = set("。！？!?\n")
    weak_punc = set("，、,；;：:")

    for piece in text_stream:
        if not piece:
            continue
        buffer += piece

        while buffer:
            cut_idx = None

            # 1) Strong punctuation: cut as soon as phrase not too tiny
            for idx, ch in enumerate(buffer):
                if ch in strong_punc:
                    candidate = idx + 1
                    if candidate >= min_chunk_len:
                        cut_idx = candidate
                    else:
                        cut_idx = min(max_len, len(buffer))
                    break

            # 2) Weak punctuation: prefer shorter phrase-like chunks
            if cut_idx is None:
                for idx, ch in enumerate(buffer):
                    if ch in weak_punc:
                        candidate = idx + 1
                        if candidate >= min_chunk_len and (
                            candidate >= soft_limit or len(buffer) >= soft_limit
                        ):
                            cut_idx = candidate
                            break

            # 3) Length fallback
            if cut_idx is None:
                if len(buffer) >= hard_limit:
                    cut_idx = max_len
                elif len(buffer) >= soft_limit:
                    cut_idx = soft_limit

            if cut_idx is not None and cut_idx > 0:
                chunk = buffer[:cut_idx].strip()
                buffer = buffer[cut_idx:]
                if chunk:
                    yield chunk
                continue

            break

    tail = buffer.strip()
    while tail:
        if len(tail) <= max_len:
            yield tail
            break
        yield tail[:max_len].strip()
        tail = tail[max_len:].strip()
