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

# With thanks to everyone I've ever discussed concurrency or datastructures with

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Generator
from heapq import heappop, heappush

from . import _typings as t

__all__ = ("LIFOQueue", "PriorityQueue", "Queue", "QueueEmpty", "QueueFull")


class QueueEmpty(Exception):
    """Raised when a queue is empty and attempting to get without waiting."""


class QueueFull(Exception):
    """Raised when a queue is full and attempting to put without waiting."""


class AsyncEvent:
    __slots__ = ("_cancelled", "_future", "_loop", "_unset")

    def __init__(self, /) -> None:
        self._loop = asyncio.get_running_loop()
        self._future: asyncio.Future[bool] | None = None
        self._unset = [True]
        self._cancelled = False

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __reduce__(self, /) -> t.Never:
        raise TypeError

    def __bool__(self, /) -> bool:
        return not self._unset

    def cancel(self, /) -> bool:
        cancelled = self._cancelled

        if not cancelled and (unset := self._unset):
            try:
                unset.pop()
            except IndexError:
                pass
            else:
                self._cancelled = cancelled = True

        return cancelled

    def is_set(self, /) -> bool:
        return not self._unset

    def is_cancelled(self, /) -> bool:
        return self._cancelled

    def __await__(self, /) -> Generator[t.Any, t.Any, bool]:
        if self._unset:
            self._future = self._loop.create_future()

            try:
                return (yield from self._future.__await__())
            except BaseException:
                self.cancel()
                raise
            finally:
                self._future = None

        return (yield from asyncio.sleep(0, True).__await__())

    def _set_state(self, /) -> None:
        if (future := self._future) is not None:
            try:  # faster to race than lock
                future.set_result(True)
            except asyncio.InvalidStateError:
                pass

    def set(self, /) -> bool:
        success = True

        if is_unset := self._unset:
            try:
                is_unset.pop()
            except IndexError:
                success = False
            else:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop is self._loop:
                    self._set_state()
                else:
                    try:
                        self._loop.call_soon_threadsafe(self._set_state)
                    except RuntimeError:
                        pass
        else:
            success = False

        return success


class ThreadingEvent:
    __slots__ = ("_cancelled", "_lock", "_unset")

    def __init__(self, /) -> None:
        self._unset = [True]
        self._cancelled = False
        self._lock = threading.Lock()
        self._lock.acquire()

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __reduce__(self, /) -> t.Never:
        raise TypeError

    def wait(self, /, timeout: float | None = None) -> bool:
        if not self._unset:
            return True

        if timeout is None:
            return self._lock.acquire()
        if timeout > 0:
            return self._lock.acquire(timeout=timeout)

        return self._lock.acquire(blocking=False)

    def __bool__(self, /) -> bool:
        return not self._unset

    def cancel(self, /) -> bool:
        cancelled = self._cancelled

        if not cancelled and (unset := self._unset):
            try:
                unset.pop()
            except IndexError:
                pass
            else:
                self._cancelled = cancelled = True

        return cancelled

    def is_set(self, /) -> bool:
        return not self._unset

    def is_cancelled(self, /) -> bool:
        return self._cancelled

    def set(self, /) -> bool:
        success = True

        if is_unset := self._unset:
            try:
                is_unset.pop()
            except IndexError:
                success = False
            else:
                self._lock.release()
        else:
            success = False

        return success


class BaseQueue[T]:
    """Base queue implementation.

    Not meant for direct public use. You probably should use
    one of the provided subclasses.

    May make sense as a type annotation.
    """

    __slots__ = ("__get_ws", "__put_ws", "__unlocked", "__unlocked", "__ws", "maxsize")

    def __init__(self, /, maxsize: int | None = None) -> None:
        self.__ws: deque[AsyncEvent | ThreadingEvent] = deque()
        self.__get_ws: deque[AsyncEvent | ThreadingEvent] = deque()
        self.__put_ws: deque[AsyncEvent | ThreadingEvent] = deque()
        self.__unlocked: list[bool] = [True]
        self.maxsize: int = maxsize if maxsize is not None else 0

    def __bool__(self, /) -> bool:
        return self._qsize() > 0

    def __len__(self, /) -> int:
        return self._qsize()

    def _acquire_nowait(self, /) -> bool:
        if unlocked := self.__unlocked:
            try:
                unlocked.pop()
            except IndexError:
                success = False
            else:
                success = True
        else:
            success = False

        return success

    def _acquire_nowait_put(self, /) -> bool:
        maxsize = self.maxsize

        if unlocked := self.__unlocked:
            if maxsize <= 0:
                try:
                    unlocked.pop()
                except IndexError:
                    success = False
                else:
                    success = True
            elif self._qsize() < maxsize:
                try:
                    unlocked.pop()
                except IndexError:
                    success = False
                else:
                    if self._qsize() < maxsize:
                        success = True
                    else:
                        self._release()

                        success = False
            else:
                success = False
        else:
            success = False

        return success

    def _acquire_nowait_get(self, /) -> bool:
        if unlocked := self.__unlocked:
            if self._qsize() > 0:
                try:
                    unlocked.pop()
                except IndexError:
                    success = False
                else:
                    if self._qsize() > 0:
                        success = True
                    else:
                        self._release()

                        success = False
            else:
                success = False
        else:
            success = False

        return success

    def _release(self, /) -> None:
        maxsize = self.maxsize

        unlocked = self.__unlocked

        while True:
            size = self._qsize()

            if not size:
                actual_waiters = self.__put_ws
            elif size >= maxsize > 0:
                actual_waiters = self.__get_ws
            else:
                actual_waiters = self.__ws

            while actual_waiters:
                try:
                    event = actual_waiters.popleft()
                except IndexError:
                    pass
                else:
                    if event.set():
                        break
            else:
                unlocked.append(True)

                if actual_waiters and self._acquire_nowait():
                    continue

            break

    async def async_put(self, item: T, /) -> None:
        """Put an item into the queue."""
        waiters = self.__ws
        put_waiters = self.__put_ws
        success = self._acquire_nowait_put()

        try:
            if not success:
                event = AsyncEvent()
                waiters.append(event)
                put_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_put()):
                        success = await event
                finally:
                    if success or event.cancel():
                        try:
                            put_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueFull

            self._put(item)
        finally:
            if success:
                self._release()

    def sync_put(
        self, item: T, /, *, blocking: bool = True, timeout: float | None = None
    ) -> None:
        """Put an item into the queue.

        Parameters
        ----------
        blocking: bool
            Whether or not to block until space in the queue is available.
        timeout: float | None
            The maximum time to wait if waiting on room in the queue.
        """
        waiters = self.__ws
        put_waiters = self.__put_ws
        success = self._acquire_nowait_put()

        try:
            if not success:
                if not blocking:
                    raise QueueFull

                event = ThreadingEvent()
                waiters.append(event)
                put_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_put()):
                        success = event.wait(timeout)
                finally:
                    if success or event.cancel():
                        try:
                            put_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueFull

            self._put(item)
        finally:
            if success:
                self._release()

    async def async_get(self, /) -> T:
        """Get an item from the queue."""
        waiters = self.__ws
        get_waiters = self.__get_ws
        success = self._acquire_nowait_get()

        try:
            if not success:
                event = AsyncEvent()
                waiters.append(event)
                get_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_get()):
                        success = await event
                finally:
                    if success or event.cancel():
                        try:
                            get_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueEmpty

            item = self._get()
        finally:
            if success:
                self._release()

        return item

    def sync_get(self, /, *, blocking: bool = True, timeout: float | None = None) -> T:
        """Get an item from the queue.

        Parameters
        ----------
        blocking: bool
            Whether or not to block until an item is available.
        timeout: float | None
            The maximum time to wait if waiting on an item.
        """
        waiters = self.__ws
        get_waiters = self.__get_ws

        success = self._acquire_nowait_get()

        try:
            if not success:
                if not blocking:
                    raise QueueFull

                event = ThreadingEvent()
                waiters.append(event)
                get_waiters.append(event)

                try:
                    if not (success := self._acquire_nowait_get()):
                        success = event.wait(timeout)
                finally:
                    if success or event.cancel():
                        try:
                            get_waiters.remove(event)
                        except ValueError:
                            pass
                        try:
                            waiters.remove(event)
                        except ValueError:
                            pass
                    else:
                        success = True

            if not success:
                raise QueueEmpty

            item = self._get()
        finally:
            if success:
                self._release()

        return item

    def _qsize(self, /) -> int:
        raise NotImplementedError

    def _items(self, /) -> list[T]:
        raise NotImplementedError

    def _put(self, item: T, /) -> None:
        raise NotImplementedError

    def _get(self, /) -> T:
        raise NotImplementedError

    @property
    def waiting(self, /) -> int:
        return len(self.__ws)

    @property
    def putting(self, /) -> int:
        return len(self.__put_ws)

    @property
    def getting(self, /) -> int:
        return len(self.__get_ws)


class Queue[T](BaseQueue[T]):
    """A thread-safe queue with both sync and async access methods."""

    __slots__ = ("_data",)

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, /, maxsize: int | None = None) -> None:
        super().__init__(maxsize)
        self._data: deque[T] = deque()

    def _qsize(self, /) -> int:
        return len(self._data)

    def _items(self, /) -> list[T]:
        return list(self._data)

    def _put(self, item: T, /) -> None:
        self._data.append(item)

    def _get(self, /) -> T:
        return self._data.popleft()


class LIFOQueue[T](BaseQueue[T]):
    """A thread-safe queue with both sync and async access methods."""

    __slots__ = ("_data",)

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, /, maxsize: int | None = None) -> None:
        super().__init__(maxsize)
        self._data: deque[T] = deque()

    def _qsize(self, /) -> int:
        return len(self._data)

    def _items(self, /) -> list[T]:
        return list(self._data)

    def _put(self, item: T, /) -> None:
        self._data.append(item)

    def _get(self, /) -> T:
        return self._data.pop()


class PriorityQueue[T](BaseQueue[T]):
    """A thread-safe queue with both sync and async access methods."""

    __slots__ = ("_data",)

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, /, maxsize: int | None = None) -> None:
        super().__init__(maxsize)
        self._data: list[T] = []

    def _qsize(self, /) -> int:
        return len(self._data)

    def _items(self, /) -> list[T]:
        return self._data.copy()

    def _put(self, item: T, /) -> None:
        heappush(self._data, item)

    def _get(self, /) -> T:
        return heappop(self._data)
