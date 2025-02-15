from __future__ import annotations

import asyncio
import inspect

from src.async_utils.task_cache import taskcache


@taskcache(None)
async def echo(x: int) -> None:
    print(x)  # noqa: T201


async def runner(v: int):
    [await echo(i) for i in range(v)]


if __name__ == "__main__":
    print(echo.__signature__)  # pyright: ignore[reportFunctionMemberAccess] # noqa: T201
    print(inspect.signature(echo))  # noqa: T201
    print(echo.__signature__)  # pyright: ignore[reportFunctionMemberAccess] # noqa: T201
    asyncio.run(runner(10))
    asyncio.run(runner(20))
