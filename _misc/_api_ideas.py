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

# Quick scratch to demo a possibly better API for matching stdlib

import asyncio
from collections.abc import AsyncGenerator

from async_utils import _typings as t
from async_utils._merge_gens import (  # noqa: PLC2701
    batch_merge_gens,
    batch_merge_gens_delaying_exceptions,
    batch_merge_gens_suppressing_exceptions,
    merge_gens,
    merge_gens_delaying_exceptions,
    merge_gens_suppressing_exceptions,
)

TYPE_CHECKING = False
if TYPE_CHECKING:
    import typing
    from typing import Generic as Gen

    T = typing.TypeVar("T")
else:
    T = object

    class Gen:
        def __class_getitem__(*args: object) -> t.Any:
            return object


class MergeGens(Gen[T]):
    def __init__(
        self,
        *gens: AsyncGenerator[T],
        exceptions: t.Literal["suppress", "delay_raise", "raise"] = "raise",
    ) -> None:
        self._gens: tuple[AsyncGenerator[T], ...] = gens
        match exceptions:
            case "suppress":
                self._f = merge_gens_suppressing_exceptions
            case "delay_raise":
                self._f = merge_gens_delaying_exceptions
            case "raise":
                self._f = merge_gens

    async def __aenter__(self) -> AsyncGenerator[T]:
        return self._f(*self._gens)

    async def __aexit__(self, *_dont_care: object) -> None:
        res = await asyncio.gather(*(g.aclose() for g in self._gens), return_exceptions=True)
        excs = [t for t in res if t]
        if excs:
            msg = "While closing merged async generators:"
            raise BaseExceptionGroup(msg, excs)


class BatchMergeGens(Gen[T]):
    def __init__(
        self,
        *gens: AsyncGenerator[T],
        exceptions: t.Literal["suppress", "delay_raise", "raise"] = "raise",
    ) -> None:
        self._gens: tuple[AsyncGenerator[T], ...] = gens
        match exceptions:
            case "suppress":
                self._f = batch_merge_gens_suppressing_exceptions
            case "delay_raise":
                self._f = batch_merge_gens_delaying_exceptions
            case "raise":
                self._f = batch_merge_gens

    async def __aenter__(self) -> AsyncGenerator[list[T]]:
        return self._f(*self._gens)

    async def __aexit__(self, *_dont_care: object) -> None:
        res = await asyncio.gather(*(g.aclose() for g in self._gens), return_exceptions=True)
        excs = [t for t in res if t]
        if excs:
            msg = "While closing merged async generators:"
            raise BaseExceptionGroup(msg, excs)
