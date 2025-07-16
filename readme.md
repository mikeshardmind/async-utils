# async-utils
This contains various async utility functions I've written

## Using it

### Warning, this is not stable yet

While my intent is that all of this is already suitably ready for use
(and started by extracting private in-use code for public consumption) and will
not require breaking changes, you may want to Subscribe to this issue for
breaking change notices https://github.com/mikeshardmind/async-utils/issues/10

### Breaking policy (Future)

The breaking policy only applies to symbols exported in ``__all__`` for a
given public module. Public modules are those not prefixed with `_`.

Only documented public attributes and methods are guaranteed for exported classes.

Things that will **not** be considered breaking:

1. Type annotations changing is not a breaking change.
   Types are descriptive of the API, not perscriptive. An attempt will be made
   to keep these stable, but may change if a more useful description of the types
   is found or later made possible.

2. Docstring values, logging message values, exception message values,
   and/or warning messages changing are not breaking changes.
   These will not be frivolously changed, but should not be considered as unchanging.
   If you have a specific need of detecting something which cannot be accomplished
   without relying on these, please open an issue,
   it may be possible to accomodate your use in another manner.

3. The calling convention of decorated functions and user provided callbacks is a
   non-guaranteed implementation detail.
   If you need a guarantee here, please open an issue explaining why.

4. Base class layouts, metaclasses
   The non-public base classes are considered an implementation detail.
   They may be removed, changed, etc. The library does not support subclassing
   of types provided, and only the public types should need be relied upon.

5. Non-explicit compatability with `weakref`
   Any compatability with weakref should be considered accidental **unless** a
   type has declared slots and includes `__weakref__` in those slots.
   (open an issue if you want `__weakref__` with a reason why)

6. Going from *inable* to *able* share a resource across threads.
7. Adding or removing internal locking that does not introduce deadlocks,
   races, or remove the threadsafety of an object's documented use.

Things that will be considered a breaking change:

1. Removal of a symbol from ``__all__``.
2. Removal of a documented public attribute or method of a publicly exported class.
3. Removal of a public module.
4. Removal of a parameter's default value making an optional argument required.
5. Changing the semantic meaning of a parameter's default value.
6. Changing the allowed runtime type of a parameter in a way that makes a previously supported call invalid.
7. Changing the runtime return type of a documented function to no longer match prior documentation.
8. Changing an object to no longer be shareable across threads.

When something isn't covered explicitly one way or the other above,
it will be considered a breaking change if an intended supported usage
no longer has the same semantic meaning or no longer works at all.

Breaking changes will be announced
[here](https://github.com/mikeshardmind/async-utils/issues/10)
as well as in the release notes for stable releases.

### Subclassing

Unless specifically documented as supporting it, none of the types within
are intended to be subclassed, and things which impact that will **not** be taken
into account. These are not marked with ``typing.Final`` due to typecheckers
not supporting the usage pattern required to have lazy typing imports when
taking ``Final`` into account.

### Just tell me how to install it already

```
pip install mikeshardmind-async-utils
```
or
```
pip install mikeshardmind-async-utils @ git+https://github.com/mikeshardmind/async-utils
```

swap pip commands for pdm, uv, or other tool as desired.


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

- imports are namespaced
- inspect import is incurred only if you introspect the signature of a task cache object.
- typing imports are resolvable at runtime.
- typing imports are lazily evaluated (see _typings.py).
- Some classes/functions with only minor variations are intentionally duplicated partially.
- possibly more things I'm forgetting right now.

### 3. Task cancellation should only ocur where obvious and documented

There's not much further to say about this goal right now, but this
should be expanded on later in the WIP accompanying guide on making
concurrent systems written in python fault tolerant at scale.

### 4. Typed

- The public API surface should be well-typed.
- The public API surface should be introspectible at runtime.
- Decorators that transform types should not destroy introspection.
- Expensive types should be lazily imported or otherwise avoided.


The public api surface is defined by everything in any non-underscored
import name's `__all__`. Certain type aliases are provided, but are not
exported as part of the public api surface, and may change.

The project currently uses pyright for development, and both pyright and mypy
when ensuring the public api surface is well-typed and compatible with strict
use of typechecking. The configurations used are in pyproject.toml.

While compatible with strict interpretations of python's type system,
both pyright and mypy enable checks that are not type errors in their
strict modes. See the configurations mentioned for more detail.

In particular, `pyright --verifytypes async_utils --ignoreexternal`
should report zero ambiguous or unknown public types.

The use of Any in a few places is *intentional* for internals.

### 5. Threading and multiple event loops

When possible, things should "just work" even in event loop per thread scenarios.

Examples: caching decorators and ratelimiter

## Non-goals

At the current moment, the following are non-goals

- compatability with gevent or other libraries which patch threading and async behavior.
- compatability with non-asyncio event loops (event loops like uvloop that are asyncio event loops are included in compatability, event loops such as those provided by trio are not)
- compatability with non CPython python implementations

# Documentation

Most things now have initial documentation, but no rendered docs site, examples, or
prose yet.

What's in each public export, below

| Module                                                 | Description                                                                                                      | Notes                                                                                                                                                                    |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [bg_loop.py](src/async_utils/bg_loop.py)               | Contains a context manager that creates an asyncio event loop in a background thread and wraps scheduling to it, |                                                                                                                                                                          |
| [bg_tasks.py](src/async_utils/bg_tasks.py)             | Contains a lightweight alternative to asyncio TaskGroups, without the problematic cancellation semantics.        |                                                                                                                                                                          |
| [corofunc_cache.py](src/async_utils/corofunc_cache.py) | Contains lightweight preemptive async caching decorators.                                                        |                                                                                                                                                                          |
| [dual_color.py](src/async_utils/dual_color.py)         | Contains thread-safe queues with both sync and async colored access.                                             | Missing docs, but behaves similarly to the combined interfaces of threading and asyncio Queues                                                                           |
| [gen_transform.py](src/async_utils/gen_transform.py)   | Contains a function to wrap a synchronous generator in a thread use it asynchronously                            |                                                                                                                                                                          |
| [lockout.py](src/async_utils/lockout.py)               | multi-timeout lockouts tags                                                                                      |                                                                                                                                                                          |
| [lru.py](src/async_utils/lru.py)                       | A lightweight lru-cache mapping                                                                                  |                                                                                                                                                                          |
| [priority_sem.py](src/async_utils/priority_sem.py)     | A priority semaphore.                                                                                            |                                                                                                                                                                          |
| [ratelimiter.py](src/async_utils/ratelimiter.py)       | A ratelimiting context manager.                                                                                  |                                                                                                                                                                          |
| [scheduler.py](src/async_utils/scheduler.py)           | A simple in-memory asyncio job runner.                                                                           |                                                                                                                                                                          |
| [sig_service.py](src/async_utils/sig_service.py)       | A means of abstracting signal handling for graceful shutdown in multi-color concurrent applications              | This needs much better examples and documentation                                                                                                                        |
| [task_cache.py](src/async_utils/task_cache.py)         | task-based decorators for preemptive async caching.                                                              |                                                                                                                                                                          |
| [waterfall.py](src/async_utils/waterfall.py)           | an async batching mechanism that dispatches by volume or time interval, whichever is satisfied first.            |                                                                                                                                                                          |

