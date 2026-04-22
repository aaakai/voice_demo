from __future__ import annotations


def pause_in_window(pause_ms: int, min_ms: int, max_ms: int) -> bool:
    return min_ms <= pause_ms <= max_ms


def likely_filler(text: str) -> bool:
    t = text.strip()
    return t in {"嗯", "啊", "哦", "呃", "喂"}
