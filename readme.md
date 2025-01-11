# async-utils

This contains various async utility functions I've written

# Documentation

Things now have initial documentation, but no rendered docs site, examples, or
prose yet.

# Design goals

## The obvious use should be correct

Examples of this:

- Any caveats should be documented prominently.
- Internally wrapping user functions should retain features
  such as laziness and backpressure (see: gen_transform.py)
- If the library can't correctly wrap behavior, it shouldn't wrap that behavior.

## Pay for only what you use

This library is designed so that you only pay for the abstractions you use, without
breaking potential interaction with other library uses.

This includes:

- imports are namespaced, (inspect import is incurred only if you import task_cache).
- typing imports are resolvable at runtime.
- typing imports are lazily evaluated (see _typings.py).
- Some classes/functions with only minor variations are intentionally duplicated partially.
- possibly more things I'm forgetting right now.

## Task cancellation should only ocur where obvious and documented

There's not much further to say about this goal right now, but this
should be expanded on later in the WIP accompanying guide on making
concurrent systems written in python fault tolerant at scale.