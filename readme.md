# async-utils
This contains various async utility functions I've written

## Design goals

### 1. The obvious use should be correct
Examples of this:

- Any caveats should be documented prominently.
- Internally wrapping user functions should retain features
  such as laziness and backpressure (see: gen_transform.py)
- If the library can't correctly wrap behavior, it shouldn't wrap that behavior.

### 2. Pay for only what you use

This library is designed so that you only pay for the abstractions you use, without
breaking potential interaction with other library uses.

This includes:

- imports are namespaced, (inspect import is incurred only if you import task_cache).
- typing imports are resolvable at runtime.
- typing imports are lazily evaluated (see _typings.py).
- Some classes/functions with only minor variations are intentionally duplicated partially.
- possibly more things I'm forgetting right now.

### 3. Task cancellation should only ocur where obvious and documented

There's not much further to say about this goal right now, but this
should be expanded on later in the WIP accompanying guide on making
concurrent systems written in python fault tolerant at scale.

# Documentation

Most things now have initial documentation, but no rendered docs site, examples, or
prose yet.

What's in each public export, below

| Module                                                 | Description                                                                                                      | Notes                                                                                                                                                                    |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [bg_loop.py](src/async_utils/bg_loop.py)               | Contains a context manager that creates an asyncio event loop in a backgrouns thread and wraps scheduling to it, |                                                                                                                                                                          |
| [bg_tasks.py](src/async_utils/bg_tasks.py)             | Contains a lightweight alternative to asyncio TaskGroups, without the entertwined cancellation semantics.        |                                                                                                                                                                          |
| [corofunc_cache.py](src/async_utils/corofunc_cache.py) | Contains lightweight preemptive async caching decorators                                                         |                                                                                                                                                                          |
| [dual_color.py](src/async_utils/dual_color.py)         | Contains thread-safe queues and a thread-safe semaphore with both sync and async colored access.                 | Missing docs                                                                                                                                                             |
| [gen_transform.py](src/async_utils/gen_transform.py)   | Contains a function to wrap a synchronous generator in a thread use it asynchronously                            |                                                                                                                                                                          |
| [lockout.py](src/async_utils/lockout.py)               | async digital loto tags!                                                                                         |                                                                                                                                                                          |
| [lru.py](src/async_utils/lru.py)                       | A lightweight lru-cache mapping                                                                                  |                                                                                                                                                                          |
| [priority_sem.py](src/async_utils/priority_sem.py)     | A priority semaphore.                                                                                            |                                                                                                                                                                          |
| [ratelimiter.py](src/async_utils/ratelimiter.py)       | A ratelimiting context manager.                                                                                  |                                                                                                                                                                          |
| [scheduler.py](src/async_utils/scheduler.py)           | A simple in-memory asyncio job runner.                                                                           |                                                                                                                                                                          |
| [sig_service.py](src/async_utils/sig_service.py)       | A means of abstracting signal handling for graceful shutdown in multi-color concurrent applications              | Note: This needs much better examples and documentation                                                                                                                  |
| [task_cache.py](src/async_utils/task_cache.py)         | task-based decorators for preemptive async caching.                                                              | This pulls in inspect, see [`corofunc_cache.py`](src/async_utils/corofunc_cache.py) for the lightweight if you don't need direct access to the lower level task objects. |
| [waterfall.py](src/async_utils/waterfall.py)           | an async batching mechanism that dispatches by volume or time interval, whichever is satisfied first.            |                                                                                                                                                                          |

