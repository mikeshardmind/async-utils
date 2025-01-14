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

"""Collection of stuff that *should* be fully native in the future.

but is relying on things that are similarly available in python, for now.
"""

from __future__ import annotations

from . import _typings as t

TYPE_CHECKING = False
# TODO: native impl in zig
# Check this per python version till then
try:
    from _collections import _tuplegetter  # pyright: ignore[reportUnknownVariableType, reportMissingImports]  # noqa: I001, PLC2701
except ImportError:  # fmt: skip
    no_native = True
else:
    no_native = False


if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Generator

    class PriorityWaiter(tuple[int, float, asyncio.Future[None]]):
        __slots__ = ()

        def __new__(
            cls, priority: int, ts: float, future: asyncio.Future[None]
        ) -> t.Self:
            return super().__new__(cls, (priority, ts, future))

        @property
        def priority(self) -> int:
            return self[0]

        @property
        def ts(self) -> float:
            return self[1]

        @property
        def future(self) -> asyncio.Future[None]:
            return self[2]

        @property
        def cancelled(self) -> Callable[[], bool]:
            return self.future.cancelled

        @property
        def done(self) -> Callable[[], bool]:
            return self.future.done

        def __await__(self) -> Generator[t.Any, t.Any, None]:
            return self.future.__await__()

        def __lt__(self, other: t.Any) -> bool:
            if not isinstance(other, PriorityWaiter):
                return NotImplemented
            return self[:2] < other[:2]

else:
    from operator import attrgetter, itemgetter

    sl = itemgetter(0, 1)

    if no_native:

        class PriorityWaiter(tuple):
            __slots__ = ()

            def __new__(
                cls, priority: int, ts: float, future: asyncio.Future[None]
            ) -> t.Self:
                return super().__new__(cls, (priority, ts, future))

            priority = property(itemgetter(0))
            ts = property(itemgetter(1))
            future = property(itemgetter(2))
            cancelled = property(attrgetter("future.cancelled"))
            done = property(attrgetter("future.done"))
            __await__ = property(attrgetter("future.__await__"))

            def __lt__(self, other: object) -> bool:
                if not isinstance(other, PriorityWaiter):
                    return NotImplemented
                return sl(self) < sl(other)

    else:

        class PriorityWaiter(tuple):
            __slots__ = ()

            def __new__(
                cls, priority: int, ts: float, future: asyncio.Future[None]
            ) -> t.Self:
                return super().__new__(cls, (priority, ts, future))

            priority = _tuplegetter(0, "priority")
            ts = _tuplegetter(1, "ts")
            future = _tuplegetter(2, "future")

            cancelled = property(attrgetter("future.cancelled"))
            done = property(attrgetter("future.done"))
            __await__ = property(attrgetter("future.__await__"))

            def __lt__(self, other: object) -> bool:
                if not isinstance(other, PriorityWaiter):
                    return NotImplemented
                return sl(self) < sl(other)
