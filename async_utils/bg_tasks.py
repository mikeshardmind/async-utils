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
from collections.abc import Coroutine
from contextvars import Context
from typing import Any, Self, TypeVar

_T = TypeVar("_T")
type _CoroutineLike[_T] = Coroutine[Any, Any, _T]


__all__ = ["BGTasks"]


class BGTasks:
    """An intentionally dumber task group"""

    def __init__(self, exit_timeout: float | None) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._exit_timeout: float | None = exit_timeout

    def create_task(
        self,
        coro: _CoroutineLike[_T],
        *,
        name: str | None = None,
        context: Context | None = None,
    ) -> Any:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def __aenter__(self: Self) -> Self:
        return self

    async def __aexit__(self, *_dont_care: Any):
        while tsks := self._tasks.copy():
            _done, _pending = await asyncio.wait(
                tsks, timeout=self._exit_timeout
            )
            for task in _pending:
                task.cancel()
            await asyncio.sleep(0)
