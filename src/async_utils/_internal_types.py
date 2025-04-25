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

# This used to include CPython code, some minor performance losses have been
# taken to not tightly include upstream code


from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine

from . import _typings as t

type CoroFunc[**P, R] = Callable[P, Coroutine[t.Any, t.Any, R]]
type CoroLike[**P, R] = Callable[P, Awaitable[R]]
type TaskFunc[**P, R] = Callable[P, asyncio.Task[R]]
type TaskCoroFunc[**P, R] = CoroFunc[P, R] | TaskFunc[P, R]

type _CT_RET = tuple[tuple[t.Any, ...], dict[str, t.Any]]
#: Note CacheTransformers recieve a tuple (args) and dict(kwargs)
#: rather than a ParamSpec of the decorated function.
#: Warning: Mutations will impact callsite, return new objects as needed.
type CacheTransformer = Callable[[tuple[t.Any, ...], dict[str, t.Any]], _CT_RET]


_proto_cache: t.Any = {}

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Protocol

    class CoroCacheDeco(Protocol):
        def __call__[**P, R](self, c: CoroLike[P, R], /) -> CoroFunc[P, R]: ...

    class TaskCacheDeco(Protocol):
        def __call__[**P, R](self, c: TaskCoroFunc[P, R], /) -> TaskFunc[P, R]: ...


else:

    def __getattr__(name: str):
        if name in {"CoroCacheDeco", "TaskCacheDeco"}:
            if p := _proto_cache.get(name):
                return p

            if name == "CoroCacheDeco":
                from typing import Protocol

                class CoroCacheDeco(Protocol):
                    def __call__[**P, R](
                        self, c: CoroLike[P, R], /
                    ) -> CoroFunc[P, R]: ...

                _proto_cache[name] = CoroCacheDeco
                return CoroCacheDeco

            if name == "TaskCacheDeco":
                from typing import Protocol

                class TaskCacheDeco(Protocol):
                    def __call__[**P, R](
                        self, c: TaskCoroFunc[P, R], /
                    ) -> TaskFunc[P, R]: ...

                _proto_cache[name] = TaskCacheDeco
                return TaskCacheDeco

        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)


__all__ = (
    "CacheTransformer",
    "CoroCacheDeco",
    "CoroFunc",
    "CoroLike",
    "TaskCacheDeco",
    "TaskCoroFunc",
    "TaskFunc",
)
