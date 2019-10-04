A tango subscribtion wrapper for asyncio.

It mimics the taurus attribute logic:
 - subscribe to change event
 - subscribe to periodic event if change event is not available
 - poll attribute is no event channel is available


A subscribtion object can be used to share tango read attribute event on different listeners:

```python 

import asyncio
from aioattribute import SubscriptionManager


mgr = SubscriptionManager()

async def subscribe_and_listen(names):
    async with mgr.attribute_reads(names) as attribute_reads:
        async for read in attribute_reads:
            print(f"{read.name} -> {read.value}")

```
