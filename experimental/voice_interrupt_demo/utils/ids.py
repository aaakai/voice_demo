from __future__ import annotations

import itertools


_counter = itertools.count(1)


def next_turn_id(prefix: str = "turn") -> str:
    return f"{prefix}-{next(_counter)}"
