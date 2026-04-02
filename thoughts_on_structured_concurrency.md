

# TL;DR

Overall, useful as a primary model, though when adhered to without consideration
for the realities of an application's needs and developer ergonomics, runs into
significant limitations.


# Failings of task groups

## Ergonomics

Nobody wants to have their async entry point need to create a top level task group
that has to be passed into everyything to effectively have a way to scope tasks
as having the same lifetime as the event loop (and thereby, for most applications,
effectively the main lifecycle of the application.)

We can show trivially that it's possible to create the same actual flow with
"structured concurrency", but passing the task group down is of dubious benefit when
we already have a "top level" tool for scheduling, that being the event loop itself.

In terms of the benefit to reasoning, the obvious answer is to ensure APIs designed
for such spawning are clearly labeled in their behavior.
Use of such APIs should be opaque to the caller, and not their concern.
If the caller should have control over the semantics of such tasks,
that's when the API should include recieving a task group, but only then.

## Cancellation semantics

cancelling sibling tasks for any failing tasks creates a situation where cancellation
and error handling are both harder to do correctly than that of APIs that return Futures
(or in other languages, return Result objects). This doesn't mean that the default
behavior should be to *ignore* errors, but that in the case of parallelism,
the user should be the one choosing when to handle any errors that occur,
and which errors are recoverable or not.

It might seem to some that an exception hitting the task group is a sign the error
isn't handleable or it would have been handled, however, that ignores several realities
when it comes to library or framework code that runs callbacks provided by application code.
An exception that hits a task in this scenario wasn't handled by the application code,
but may be recoverable, restartable, or otherwise handled by the framework.

In other words, the automatic cancellation is a highly opinionated choice,
with significant downsides for specific use cases.

cancelling all sibling tasks means that all tasks launched from a task group must
be designed for interruption as their primary means of cancellation, rather than
leveraging the cooperative nature of async to choose the best point in a task to handle a signal.

issuing a cancellation implicitly here makes any attempt at graceful shutdown
upon failure harder than it needs to be.

# What can we use instead?

`async_utils.bg_tasks`

this module contains both an intentionally simpler task group implementation,
and a task API that looks somewhat like that provided by `concurrent.futures`

the simpler task group implementation keeps all of the existing
"when this exits, tasks scheduled are finished" semantics,
but does not automate any cancellation upon error.
This is left to the application to decide how to handle.

Similarly, the `concurrent.futures` executor-like provides futures as results.

