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

"""Type assertions for the more involed type transformations in the library."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Coroutine, Generator
from typing import Any, assert_type

from async_utils.corofunc_cache import lrucorocache
from async_utils.gen_transform import sync_to_async_gen_noctx
from async_utils.task_cache import lrutaskcache


@lrutaskcache(ttl=60, maxsize=512)
async def t1(a: int, b: str, *, x: bytes) -> str: ...


assert_type(t1(1, "a", x=b""), asyncio.Task[str])


@lrucorocache(ttl=60, maxsize=512)
async def t2(a: int, b: str, *, x: bytes) -> str: ...


_ = assert_type(t2(1, "a", x=b""), Coroutine[Any, Any, str])


def gen() -> Generator[int]:
    yield from range(10)


_ = assert_type(sync_to_async_gen_noctx(gen), AsyncGenerator[int])
