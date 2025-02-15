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
