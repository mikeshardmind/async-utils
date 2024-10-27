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
import logging
import select
import signal
import socket
import sys
import threading
from collections.abc import Callable, Coroutine
from types import FrameType
from typing import Any, Literal

type SignalCallback = Callable[[signal.Signals], Any]
type StartStopCall = Callable[[], Any]
type _HANDLER = Callable[[int, FrameType | None], Any] | int | signal.Handlers | None

log = logging.getLogger(__name__)

__all__ = ["SignalService"]

possible = "SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"
actual = tuple(e for name, e in signal.Signals.__members__.items() if name in possible)


class SignalService:
    """Meant for graceful signal handling where the main thread is only used for signal handling.
    This should be paired with event loops being run in threads."""

    def __init__(self, *, startup: list[StartStopCall], signal_cbs: list[SignalCallback], joins: list[StartStopCall]) -> None:
        self._startup: list[StartStopCall] = startup
        self._cbs: list[SignalCallback] = signal_cbs
        self._joins: list[StartStopCall] = joins

    def add_async_lifecycle(self, lifecycle: AsyncLifecycle[Any], /) -> None:
        st, cb, j = lifecycle.get_service_args()
        self._startup.append(st)
        self._cbs.append(cb)
        self._joins.append(j)

    def run(self) -> None:
        ss, cs = socket.socketpair()
        ss.setblocking(False)
        cs.setblocking(False)
        signal.set_wakeup_fd(cs.fileno())

        original_handlers: list[_HANDLER] = []

        for sig in actual:
            original_handlers.append(signal.getsignal(sig))
            signal.signal(sig, lambda s, f: None)
            if sys.platform != "win32":
                signal.siginterrupt(sig, False)

        for task_start in self._startup:
            task_start()

        select.select([ss], [], [])
        data, *_ = ss.recv(4096)

        for cb in self._cbs:
            cb(signal.Signals(data))

        for join in self._joins:
            join()

        for sig, original in zip(actual, original_handlers):
            signal.signal(sig, original)


type CtxSync[Context] = Callable[[Context], Any]
type CtxAsync[Context] = Callable[[Context], Coroutine[Any, None, None]]


class AsyncLifecycle[Context]:
    """Intended to be used with the above."""

    def __init__(
        self,
        context: Context,
        loop: asyncio.AbstractEventLoop,
        signal_queue: asyncio.Queue[signal.Signals],
        sync_setup: CtxSync[Context],
        async_main: CtxAsync[Context],
        async_cleanup: CtxAsync[Context],
        sync_cleanup: CtxSync[Context],
        timeout: float = 0.1,
    ) -> None:
        self.context = context
        self.loop: asyncio.AbstractEventLoop = loop
        self.signal_queue: asyncio.Queue[signal.Signals] = signal_queue
        self.sync_setup: CtxSync[Context] = sync_setup
        self.async_main: CtxAsync[Context] = async_main
        self.async_cleanup: CtxAsync[Context] = async_cleanup
        self.sync_cleanup: CtxSync[Context] = sync_cleanup
        self.timeout: float = timeout
        self.thread: threading.Thread | None | Literal[False] = None

    def get_service_args(self) -> tuple[StartStopCall, SignalCallback, StartStopCall]:
        def runner() -> None:
            loop = self.loop
            loop.set_task_factory(asyncio.eager_task_factory)
            asyncio.set_event_loop(loop)

            self.sync_setup(self.context)

            async def sig_h() -> None:
                await self.signal_queue.get()
                log.info("Recieved shutdown signal, shutting down worker.")
                loop.call_soon(self.loop.stop)

            async def wrapped_main() -> None:
                t1 = asyncio.create_task(self.async_main(self.context))
                t2 = asyncio.create_task(sig_h())
                await asyncio.gather(t1, t2)

            def stop_when_done(fut: asyncio.Future[None]) -> None:
                self.loop.stop()

            fut = asyncio.ensure_future(wrapped_main(), loop=self.loop)
            try:
                fut.add_done_callback(stop_when_done)
                self.loop.run_forever()
            finally:
                fut.remove_done_callback(stop_when_done)

            self.loop.run_until_complete(self.async_cleanup(self.context))

            tasks: set[asyncio.Task[Any]] = {t for t in asyncio.all_tasks(loop) if not t.done()}

            async def limited_finalization() -> None:
                _done, pending = await asyncio.wait(tasks, timeout=self.timeout)
                if not pending:
                    log.debug("All tasks finished")
                    return

                for task in tasks:
                    task.cancel()

                _done, pending = await asyncio.wait(tasks, timeout=self.timeout)

                for task in pending:
                    name = task.get_name()
                    coro = task.get_coro()
                    log.warning("Task %s wrapping coro %r did not exit properly", name, coro)

            if tasks:
                loop.run_until_complete(limited_finalization())
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())

            for task in tasks:
                try:
                    if (exc := task.exception()) is not None:
                        loop.call_exception_handler(
                            {
                                "message": "Unhandled exception in task during shutdown.",
                                "exception": exc,
                                "task": task,
                            }
                        )
                except (asyncio.InvalidStateError, asyncio.CancelledError):
                    pass

            asyncio.set_event_loop(None)
            loop.close()

            if not fut.cancelled():
                fut.result()

            self.sync_cleanup(self.context)

        def wrapped_run() -> None:
            if self.thread is not None:
                msg = "This isn't re-entrant"
                raise RuntimeError(msg)
            self.thread = threading.Thread(target=runner)
            self.thread.start()

        def join() -> None:
            if not self.thread:
                self.thread = False
                return
            self.thread.join()

        def sig(signal: signal.Signals) -> None:
            self.loop.call_soon(self.signal_queue.put_nowait, signal)
            return

        return wrapped_run, sig, join
