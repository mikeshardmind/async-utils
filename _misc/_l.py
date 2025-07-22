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
from contextlib import ExitStack

from async_utils._simple_lock import AsyncLock  # noqa: PLC2701
from async_utils.bg_loop import threaded_loop

min_res = time.get_clock_info("monotonic").resolution


async def check(lock: AsyncLock, start: int) -> tuple[int, int]:
    async with lock:
        v = max(random.random() / 1e10, min_res)
        s = time.monotonic_ns()
        await asyncio.sleep(v)
        e = time.monotonic_ns()
        await asyncio.sleep(min_res)
        return (s - start, e - start)


async def amain():
    lock = AsyncLock()
    with ExitStack() as ex:
        loops = [
            ex.enter_context(threaded_loop(use_eager_task_factory=x))
            for _ in range(10)
            for x in (True, False)
        ]
        start = time.monotonic_ns()
        tsks = {loop.run(check(lock, start)) for loop in loops for _ in range(10)}
        results = await asyncio.gather(*tsks)
        results.sort()
        print(*(f"{s} {e}" for s, e in results), sep="\n", flush=True)  # noqa: T201


if __name__ == "__main__":
    asyncio.run(amain())
