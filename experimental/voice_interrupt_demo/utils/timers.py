from __future__ import annotations

import time


def now_ts() -> float:
    return time.time()


def now_ms() -> int:
    return int(time.time() * 1000)


def elapsed_ms(since_ts: float) -> int:
    return int((time.time() - since_ts) * 1000)
