import asyncio
from collections.abc import Generator

from async_utils.gen_transform import sync_to_async_gen


class TestExc:
    def __init__(self) -> None:
        self.exc_caught: bool = False

    def __enter__(self) -> None:
        pass

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        if exc_value is not None:
            self.exc_caught = True
        return True


def bg_work() -> Generator[int]:
    ctx = TestExc()

    with ctx:
        yield from range(10)

    if not ctx.exc_caught:
        raise RuntimeError


async def test():
    try:
        async with sync_to_async_gen(bg_work) as g:
            async for _val in g:
                raise ValueError  # noqa: TRY301
    except ValueError:
        pass


if __name__ == "__main__":
    asyncio.run(test())
