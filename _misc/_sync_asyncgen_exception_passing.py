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
from collections.abc import Generator

from async_utils.gen_transform import sync_to_async_gen


class TestExc:
    def __init__(self) -> None:
        self.exc_caught: bool = False

    def __enter__(self) -> None:
        pass

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        if exc_value is not None:
            self.exc_caught = True
        return True


def bg_work() -> Generator[int]:
    ctx = TestExc()

    with ctx:
        yield from range(10)

    if not ctx.exc_caught:
        raise RuntimeError


async def test() -> None:
    try:
        async with sync_to_async_gen(bg_work) as g:
            async for _val in g:
                raise ValueError  # noqa: TRY301
    except ValueError:
        pass


if __name__ == "__main__":
    asyncio.run(test())
