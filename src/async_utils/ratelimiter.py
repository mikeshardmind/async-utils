#   Copyright 2020-present Michael Hall
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


from __future__ import annotations

import asyncio
import time
from collections import deque
from threading import RLock

from . import _typings as t

__all__ = ("RateLimiter",)


class RateLimiter:
    """Asyncio-specific internal application ratelimiter.

    This is an asyncio specific ratelimit implementation which does not
    account for various networking effects / responses and
    should only be used for internal limiting.

    This is thread-safe and re-entrant.

    Parameters
    ----------
    ratelimit: int
        The number of things to allow (see period)
    period: float
        The amount of time in seconds for which the ratelimit is allowed
        (ratelimit per period seconds)
    granularity: float
        The amount of time in seconds to wake waiting tasks if the period has
        expired.
    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, rate_limit: int, period: float, granularity: float) -> None:
        self.rate_limit: int = rate_limit
        self.period: float = period
        self.granularity: float = granularity
        self._monotonics: deque[float] = deque()
        self._lock = RLock()

    async def __aenter__(self) -> None:
        with self._lock:
            while len(self._monotonics) >= self.rate_limit:
                try:
                    self._lock.release()
                    await asyncio.sleep(self.granularity, True)
                finally:
                    self._lock.acquire()

            now = time.monotonic()
            with self._lock:
                while self._monotonics and (now - self._monotonics[0] > self.period):
                    self._monotonics.popleft()

        with self._lock:
            self._monotonics.append(time.monotonic())

    async def __aexit__(self, *_dont_care: object) -> None:
        pass
