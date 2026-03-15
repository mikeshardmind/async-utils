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
from collections.abc import Awaitable, Iterable

from . import _typings as t


class AsCompletedIterator[T]:
    """This is *similar to* the implementation in asyncio,
    but with some minor differences to suit specific use
    """

    def __init__(self, futs: Iterable[asyncio.Future[T]]) -> None:
        self._done: asyncio.Queue[asyncio.Future[T]] = asyncio.Queue()
        self._timeout_handle = None
        self._todo: set[asyncio.Future[T]] = set(futs)
        self._todo_left = len(self._todo)
        for f in self._todo:
            f.add_done_callback(self._todo.discard)
            f.add_done_callback(self._done.put_nowait)

    def __aiter__(self) -> t.Self:
        return self

    def __iter__(self) -> t.Self:
        return self

    async def __anext__(self) -> T:
        if not self._todo_left:
            raise StopAsyncIteration
        self._todo_left -= 1
        return await (await self._done.get())

    def __next__(self) -> Awaitable[T]:
        if not self._todo_left:
            raise StopIteration
        self._todo_left -= 1
        return asyncio.ensure_future(self._next_as_future())

    async def _next_as_future(self) -> T:
        return (await self._done.get()).result()
