from __future__ import annotations

import random
import time


def random_delay(min_seconds: float, max_seconds: float) -> None:
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
