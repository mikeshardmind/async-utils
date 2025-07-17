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

import asyncio
import random
import time

from async_utils._simple_lock import AsyncLock  # noqa: PLC2701
from async_utils.bg_loop import threaded_loop


async def check(lock: AsyncLock):
    async with lock:
        v = random.random()
        s = time.monotonic()
        await asyncio.sleep(v)
        e = time.monotonic()
        print(s, v, e, flush=True)  # noqa: T201


async def amain():
    lock = AsyncLock()
    with (
        threaded_loop(use_eager_task_factory=False) as tl1,
        threaded_loop(use_eager_task_factory=False) as tl2,
        threaded_loop() as tl3,
        threaded_loop() as tl4,
    ):
        tsks = {loop.run(check(lock)) for loop in (tl1, tl2, tl3, tl4) for _ in range(10)}
        await asyncio.gather(*tsks)


if __name__ == "__main__":
    asyncio.run(amain())
