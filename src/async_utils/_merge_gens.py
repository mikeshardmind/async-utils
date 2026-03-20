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
from collections.abc import AsyncGenerator


async def merge_gens[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    all_done: set[AsyncGenerator[T]] = set()
    cancelled: bool = False
    futs = {asyncio.ensure_future(anext(g, g)) for g in gens if g not in all_done}

    try:
        while futs:
            done, pending = await asyncio.wait(futs, return_when=asyncio.FIRST_COMPLETED)
            exceptions: list[Exception] = []
            base_exceptions: list[BaseException] = []

            for f in done:
                if (not cancelled) and f.cancelled():
                    cancelled = True
                    for p in pending:
                        p.cancel()
                elif exc := f.exception():
                    if isinstance(exc, BaseException):
                        base_exceptions.append(exc)
                    else:
                        exceptions.append(exc)
                else:
                    v = f.result()
                    if v in gens:
                        all_done.add(v)  # pyright: ignore[reportArgumentType]
                    else:
                        yield v  # pyright: ignore[reportReturnType]
            futs = {asyncio.ensure_future(anext(g, g)) for g in gens if g not in all_done}
    finally:
        for f in futs:
            if not f.done():
                f.cancel()
        for g in gens:
            await asyncio.gather(g.aclose(), return_exceptions=True)
