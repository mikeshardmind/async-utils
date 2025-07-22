# What?

This is just some assorted info that may be useful to anyone considering why
certain things in this library are done the way there are and also
as a place to record some important information that I may not always remember
all of, but may need to revisit in the future related to it.

## Task switching semantic changes in the standard library

### Before eager tasks

- await
- async with (both enter and exit)
- async for (per loop)
- return (from a coroutine)
- yield (from a coroutine)
- Raising an exception (that leaves a coroutine)

### As of eager tasks, the below are included

- Constructing an asyncio.Task with eager_start=True while the associated event loop is running
- asyncio.create_task
- asyncio.ensure_future (when wrapping a non-future awaitable)
- asyncio.wait_for\* (when any non-future awaitables are waited on) (ensure_future)
- asyncio.as_completed\* (when any non-future awaitables are waited on) (ensure_future)
- asyncio.gather\* (when any non-future awaitables are gathered) (ensure_future)
- asyncio.IocpProactor.accept (unlikely to impact most)  (ensure_future on a coro)
- asyncio.StreamReaderProtocol.connection_made (library use, perhaps?) (create task)
- Constructing asyncio.BaseSubprocessTransport (create task)
    - Note: extremely unlikely to impact anyone, asyncio.create_subprocess_* doesn't construct this prior to an await.

\* Likely not a meaningfully new place, awaiting these immediately is the most common use.


## EventLoop.create_task + Task.set_name

- While asyncio.Task has had these since 3.8, 3.13 is the first version where
  the presence of `set_name` is mandatory.
- 3.12 eager_tasks don't have their name set when using `loop.create_task`,
  being set by an internal function aware of the above issue in `asyncio.create_task`.
  This divergent behavior has to be kept track of, however, relying on task names
  being reliably set prior to python 3.13 as a library or application
  minimum is unsafe.


## Deferred typing-only imports

There's a bunch of imports that are deferred, but not elided.
This allows annotation inspection at runtime to continue working, while minimizing
(but unfortunately, not fully removing) the costs for anyone not introspecting.