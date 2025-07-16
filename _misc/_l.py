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
    with threaded_loop() as tl1, threaded_loop() as tl2:
        tsks = {loop.run(check(lock)) for loop in (tl1, tl2) for _ in range(10)}
        await asyncio.gather(*tsks)


if __name__ == "__main__":
    asyncio.run(amain())
