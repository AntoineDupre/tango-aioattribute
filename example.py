import asyncio
from aioattribute.manager import SubscriptionManager
from loguru import logger


async def subscribe_and_listen(no, names):

    async with mgr.attribute_reads(names) as attribute_reads:
        async for read in attribute_reads:
            logger.info(f"{read.name} -> {read.value}")


async def main():
    await subscribe_and_listen(
        1,
        [
            "antdup/tangotest/1/ampli",
            "antdup/tangotest/1/double_scalar",
            "antdup/tangotest/1/State",
            "antdup/tangotest/2/ampli",
            "antdup/tangotest/2/double_scalar",
            "antdup/tangotest/2/State",
        ],
    )


mgr = SubscriptionManager()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
