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

from . import _typings as t

type _CoroutineLike[T] = Coroutine[t.Any, t.Any, T]


__all__ = ["BGTasks"]


class BGTasks:
    """An intentionally dumber task group.

    Parameters
    ----------
    exit_timeout: int | None
        Optionally, the number of seconds to wait before timing out tasks.
        In applications that care about graceful shutdown, this should
        usually not be set. When not providedd, the context manager
        will not exit until all tasks have ended.

    """

    def __init__(self, exit_timeout: float | None) -> None:
        self._tasks: set[asyncio.Task[object]] = set()
        self._etime: float | None = exit_timeout

    def create_task[T](
        self,
        coro: _CoroutineLike[T],
        *,
        name: str | None = None,
        context: Context | None = None,
    ) -> asyncio.Task[T]:
        """Create a task bound managed by this context manager.

        Returns
        -------
        asyncio.Task: The task that was created.
        """
        t = asyncio.create_task(coro, name=name, context=context)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def __aenter__(self: t.Self) -> t.Self:
        return self

    async def __aexit__(self, *_dont_care: object) -> None:
        while tsks := self._tasks.copy():
            _done, pending = await asyncio.wait(tsks, timeout=self._etime)
            for task in pending:
                task.cancel()
            await asyncio.sleep(0)
