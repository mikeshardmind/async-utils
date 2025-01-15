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
import concurrent.futures as cf
import logging
import logging.handlers
import queue
import random
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from src.async_utils._qs import Queue  # noqa: PLC2701
from src.async_utils.bg_loop import threaded_loop

log = logging.getLogger()

dt_fmt = "%Y-%m-%d %H:%M:%S"
FMT = logging.Formatter("[%(asctime)s] [%(levelname)-8s}] %(name)s: %(message)s", dt_fmt)


_MSG_PREFIX = "\x1b[30;1m%(asctime)s\x1b[0m "
_MSG_POSTFIX = "%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m %(message)s"


LC = (
    (logging.DEBUG, "\x1b[40;1m"),
    (logging.INFO, "\x1b[34;1m"),
    (logging.WARNING, "\x1b[33;1m"),
    (logging.ERROR, "\x1b[31m"),
    (logging.CRITICAL, "\x1b[41m"),
)

FORMATS = {
    level: logging.Formatter(_MSG_PREFIX + color + _MSG_POSTFIX, "%Y-%m-%d %H:%M:%S")
    for level, color in LC
}


class _AnsiTermFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: PLR6301
        formatter = FORMATS.get(record.levelno)
        if formatter is None:
            formatter = FORMATS[logging.DEBUG]
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"\x1b[31m{text}\x1b[0m"
        output = formatter.format(record)
        record.exc_text = None
        return output


@contextmanager
def _with_logging() -> Generator[None]:
    q: queue.SimpleQueue[Any] = queue.SimpleQueue()
    q_handler = logging.handlers.QueueHandler(q)

    stream_h = logging.StreamHandler()
    stream_h.setFormatter(_AnsiTermFormatter())
    q_listener = logging.handlers.QueueListener(q, stream_h)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(q_handler)

    try:
        q_listener.start()
        yield
    finally:
        q_listener.stop()


async def _aget(q: Queue[int | None]) -> None:
    while (v := await q.async_get()) is not None:
        await asyncio.sleep(v / 10000)
        log.info("get %d", v)


async def _aput(q: Queue[int | None]) -> None:
    for _ in range(100):
        val = random.randint(0, 10)
        await q.async_put(val)


async def _sput(q: Queue[int | None]) -> None:
    for _ in range(100):
        val = random.randint(0, 10)
        q.sync_put(val)


async def _sget(q: Queue[int | None]) -> None:
    while (v := q.sync_get()) is not None:
        await asyncio.sleep(v / 10000)
        log.info("sget %d", v)


def _main() -> None:
    with _with_logging(), threaded_loop() as loop1, threaded_loop() as loop2, threaded_loop() as loop3, threaded_loop() as loop4:

        loops = [loop1, loop2]

        q: Queue[int | None] = Queue(maxsize=5)
        gs: set[cf.Future[None]] = set()
        for lo in loops:
            gs.update(lo.schedule(_aget(q)) for _ in range(100))
        gs.add(loop3.schedule(_sget(q)))
        futures = {lo.schedule(_aput(q)) for lo in loops}
        futures.add(loop4.schedule(_sput(q)))

        cf.wait(futures, timeout=60)
        for _ in range(201):
            q.sync_put(None)
        cf.wait(gs, timeout=60)

        for lo in loops:
            lo.cancel_all()


if __name__ == "__main__":
    _main()