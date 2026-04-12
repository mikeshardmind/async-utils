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

__lazy_modules__: list[str] = ["asyncio"]

import asyncio
from types import TracebackType

from . import _merge_gens as mg
from . import _typings as t

__all__ = ["batch_merge_gens", "merge_gens"]

type ExceptionBehavior = t.Literal["raise", "delay", "suppress"]

T = t.TypeVar("T")


class MergedGenWrapper(t.Generic[T]):
    """This class is not meant to be manually constructed.
    It provides an *optional* async contextmanager interface wrapping
    async generators used by merge_gens and batch_merge_gens

    It is *generally* safe to not use the async context manager so long as
    the generators being merged are themselves implemented correctly.

    This offers a deterministic cleanup location rather than relying on
    asyncgen hooks scheduling generator close
    to the event loop implicitly upon destruction

    This satisfies both collections.abc.AsyncGenerator and contextlib.AbstractAsyncContextManager
    """

    def __init__(
        self, our_gen: t.AsyncGenerator[T], *other_gens: t.AsyncGenerator[t.Any], suppress_exceptions: bool = False
    ) -> None:
        self._our_gen = our_gen
        self._other_gens = other_gens
        self._suppress_exceptions = suppress_exceptions

    def asend(self, value: None) -> t.Coroutine[t.Any, t.Any, T]:
        return self._our_gen.asend(value)

    @t.overload
    def athrow(
        self, typ: type[BaseException], val: BaseException | object = None, tb: TracebackType | None = None, /
    ) -> t.Coroutine[t.Any, t.Any, T]: ...
    @t.overload
    def athrow(
        self, typ: BaseException, val: None = None, tb: TracebackType | None = None, /
    ) -> t.Coroutine[t.Any, t.Any, T]: ...
    def athrow(
        self,
        typ: t.Any,
        val: t.Any = None,
        tb: t.Any = None,
    ) -> t.Coroutine[t.Any, t.Any, T]:
        return self._our_gen.athrow(typ, val, tb)

    def aclose(self) -> t.Coroutine[t.Any, t.Any, None]:
        return self._our_gen.aclose()

    def __anext__(self) -> t.Coroutine[t.Any, t.Any, T]:
        return self._our_gen.__anext__()

    def __aiter__(self) -> t.Self:
        return self

    async def __aenter__(self) -> t.Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        res = await asyncio.gather(*(g.aclose() for g in self._other_gens), return_exceptions=True)
        our_res = asyncio.create_task(self._our_gen.aclose())
        await our_res

        if not self._suppress_exceptions:
            excs = [t for t in res if t]
            if not our_res.cancelled() and (exc := our_res.exception()):
                excs.append(exc)

            if excs:
                msg = "While closing merged async generators:"
                raise BaseExceptionGroup(msg, excs) from exc_value


def merge_gens[T](
    *gens: t.AsyncGenerator[T],
    exception_behavior: ExceptionBehavior = "raise",
) -> MergedGenWrapper[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised, the behavior for if/when these exceptions are reraised is
    based on the exception_behavior parameter.

    raise: Reraised interrupting further iteration, after yielding the values that are already available.
    delay: Exceptions are stored, and raised after all generators are other generators are exhausted or also in an error state
    suppress: Exceptions are supressed

    The behavior above only applies to exceptions raised by the generators,
    not the entire context if used as a context manager.

    AsyncGenerators passed into this function should not be reused.
    """
    if exception_behavior == "raise":
        return MergedGenWrapper(mg.merge_gens(*gens), *gens)
    if exception_behavior == "delay":
        return MergedGenWrapper(mg.merge_gens_delaying_exceptions(*gens), *gens)
    if exception_behavior == "suppress":
        return MergedGenWrapper(mg.merge_gens_suppressing_exceptions(*gens), *gens, suppress_exceptions=True)

    msg = "Invalid choice of exception_behavior, expected one of 'raise', 'delay' or 'suppress'"
    raise ValueError(msg)


def batch_merge_gens[T](
    *gens: t.AsyncGenerator[T],
    exception_behavior: ExceptionBehavior = "raise",
) -> MergedGenWrapper[list[T]]:
    """Creates an async generator which yields batches of values as available from multiple.

    If any exceptions are raised, the behavior for if/when these exceptions are reraised is
    based on the exception_behavior parameter.

    raise: Reraised interrupting further iteration, after yielding the values that are already available.
    delay: Exceptions are stored, and raised after all generators are other generators are exhausted or also in an error state
    suppress: Exceptions are supressed

    AsyncGenerators passed into this function should not be reused.
    """
    if exception_behavior == "raise":
        return MergedGenWrapper(mg.batch_merge_gens(*gens), *gens)
    if exception_behavior == "delay":
        return MergedGenWrapper(mg.batch_merge_gens_delaying_exceptions(*gens), *gens)
    if exception_behavior == "suppress":
        return MergedGenWrapper(mg.batch_merge_gens_suppressing_exceptions(*gens), *gens, suppress_exceptions=True)

    msg = "Invalid choice of exception_behavior, expected one of 'raise', 'delay' or 'suppress'"
    raise ValueError(msg)
