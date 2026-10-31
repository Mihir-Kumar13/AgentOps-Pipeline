"""Optional client-side pacing shared by the real providers.

Set LLM_MAX_RPM (for example 12 under a 15/min free-tier quota) to space out calls.
The wait is part of measured latency, so leave it unset for runs whose latency
numbers matter.
"""

import os
import time


class Pacer:
    def __init__(self, rpm: float | None = None):
        if rpm is None:
            rpm = float(os.getenv("LLM_MAX_RPM") or 0)
        self.min_interval_s = 60.0 / rpm if rpm > 0 else 0.0
        self._last_call = float("-inf")

    def wait(self) -> None:
        delay = self._last_call + self.min_interval_s - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last_call = time.monotonic()
