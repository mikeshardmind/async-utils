from async_utils.merge_gens import batch_merge_gens


async def _g(n: int):
    for val in range(n, n + 100):
        print("Produced", val, flush=True)  # noqa: T201
        yield val


async def main():
    async with batch_merge_gens(_g(100), _g(200), _g(300)) as merged:
        async for batch in merged:
            should_break = False
            for val in batch:
                print("Consumed", val, flush=True)  # noqa: T201
                if val == 250:
                    should_break = True

            if should_break:
                break


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
