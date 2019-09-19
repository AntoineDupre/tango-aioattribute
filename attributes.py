import asyncio
from tango import AttributeProxy, EventType, DevFailed

try:
    from contextlib import asynccontextmanager as contextmanager
except ImportError:
    from async_generator import asynccontextmanager as contextmanager
from tango import GreenMode
from tango import DeviceProxy
from loguru import logger


class Attribute:
    def __init__(self, name, polling_interval=3):
        self.name = name
        logger.debug(f"Create attribute {name}")
        self.attr = name.split("/")[-1]
        self.device = "/".join(name.split("/")[:-1])
        self.listeners = []
        self.device_proxy = DeviceProxy(
            self.device, green_mode=GreenMode.Asyncio
        )
        # self.attr_proxy = AttributeProxy(name,green_mode=GreenMode.Asyncio)
        # For polling
        self.is_polling = False
        self.polling_interval = polling_interval
        self.polling_task = None

        # For subscriptions
        self.event_id = None
        self.subscription_task = None

    def add_listener(self, listener):
        logger.debug(f"{self.name} add listener")
        if not self.listeners:
            self.subscription_task = asyncio.ensure_future(self._subscribe())

        self.listeners.append(listener)

    def remove_listener(self, listener):
        logger.debug(f"{self.name} Remove listener")
        self.listeners.remove(listener)

        if not self.listeners:
            self._unsubscribe()

    def _on_event(self, event):
        logger.debug(f"{self.name} :: New event {event.event}")
        if event.err:
            logger.error(f"Error for on {self.device}/{self.name}:\n{event}")
        self._notify_listeners(event.attr_value)

    async def _subscribe_events(self, event_type):
        # First value?
        self.event_id = await self.device_proxy.subscribe_event(
            self.attr, event_type, self._on_event, green_mode=GreenMode.Asyncio
        )
        logger.info(f"{self.name} :: Subscribe Event {event_type}")

    def _poll(self):
        async def poll_coro():
            logger.info(f"{self.name} Start polling")
            try:
                while self.is_polling:
                    try:
                        logger.debug(f"{self.name} Polling loop")
                        read = await self.device_proxy.read_attribute(
                            self.attr
                        )
                        self._notify_listeners(read)
                    except DevFailed:
                        pass  # TODO: Let the client know in an appropriate way

                    await asyncio.sleep(self.polling_interval)
            except asyncio.CancelledError:
                logger.debug(f"{self.name} Stop polling")

        self.is_polling = True
        self.polling_task = asyncio.ensure_future(poll_coro())

    def _notify_listeners(self, value):
        if value:
            logger.debug(f"{self.name} notify listeners")
            for listener in self.listeners:
                listener.put_nowait(value)

    async def _subscribe(self):
        try:
            await self._subscribe_events(EventType.CHANGE_EVENT)
        except DevFailed:

            try:
                await self._subscribe_events(EventType.PERIODIC_EVENT)
            except DevFailed:
                self._poll()

    def _unsubscribe(self):
        logger.debug(f"{self.name} Unsubscribe event")
        if self.event_id:
            self.device_proxy.unsubscribe_event(self.event_id)
        elif self.is_polling:
            self.is_polling = False
            if not self.polling_task.done():
                self.polling_task.cancel()
        elif not self.subscription_task.done():
            self.subscription_task.cancel()


class SubscriptionManager:
    def __init__(self):
        self.attributes = {}

    def _get_attribute(self, name):
        if not name in self.attributes:
            self.attributes[name] = Attribute(name)
        return self.attributes[name]

    @contextmanager
    async def attribute_reads(self, names):
        listener = asyncio.Queue()
        for name in names:
            # TODO: figure out how to do cleanup properly
            await asyncio.sleep(0.01)
            attribute = self._get_attribute(name)
            attribute.add_listener(listener)

        # Cannot `async for' over Queue directly, so I had to create a wrapping
        # async iterator to make it work. Is there a better way?
        async def async_iterator():
            try:
                while True:
                    read = await listener.get()
                    listener.task_done()
                    yield read
            except asyncio.CancelledError:
                return

        yield async_iterator()

        for name in names:
            attribute = self._get_attribute(name)
            attribute.remove_listener(listener)


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
