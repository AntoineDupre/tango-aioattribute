import asyncio
from tango import EventType, DevFailed
from tango import GreenMode
from tango import DeviceProxy
from loguru import logger


class Attribute:
    """ Handle tango subsciption/polling for one attribute"""

    def __init__(self, name, polling_interval=3):
        self.name = name
        logger.debug(f"Create attribute {name}")
        # Get Device Name
        self.attr = name.split("/")[-1]
        self.device = "/".join(name.split("/")[:-1])
        self.listeners = []
        # Create Proxy
        self.device_proxy = DeviceProxy(
            self.device, green_mode=GreenMode.Asyncio
        )
        # Polling
        self.is_polling = False
        self.polling_interval = polling_interval
        self.polling_task = None
        # Subscriptions
        self.event_id = None
        self.subscription_task = None

    def add_listener(self, listener):
        """ Subscribe to event or append a new listener
        to the event callback.
        Event subscription is not blocking (delegated to a task)"""
        logger.debug(f"{self.name} add listener")
        # First client, setup tango connection
        if not self.listeners:
            # Delegate subscription to a task
            self.subscription_task = asyncio.ensure_future(self._subscribe())
        # Append listener
        self.listeners.append(listener)

    def remove_listener(self, listener):
        """ Remove listener on listener from event notification"""
        logger.debug(f"{self.name} Remove listener")
        self.listeners.remove(listener)
        # Unsubscribe to the event if nobody is listening to it
        if not self.listeners:
            self._unsubscribe()

    def _on_event(self, event):
        """ Tango event callback """
        logger.debug(f"{self.name} :: New event {event.event}")
        if event.err:
            logger.error(f"Error for on {self.device}/{self.name}:\n{event}")
        # Propagate event to listeners
        self._notify_listeners(event.attr_value)

    async def _subscribe_events(self, event_type):
        """ Try to connect to a tango event channel """
        # TODO, Be sure to not erase event id
        self.event_id = await self.device_proxy.subscribe_event(
            self.attr, event_type, self._on_event, green_mode=GreenMode.Asyncio
        )
        logger.info(f"{self.name} :: Subscribe Event {event_type}")

    def _start_polling_task(self):
        """ Start a periodic polling task to read the attribute"""

        async def poll_coro():
            """ Polling task corountine """
            logger.info(f"{self.name} Start polling")
            try:
                while self.is_polling:
                    try:
                        logger.debug(f"{self.name} Polling loop")
                        # Read attribute
                        read = await self.device_proxy.read_attribute(
                            self.attr
                        )
                        self._notify_listeners(read)
                    except DevFailed:
                        pass  # TODO: Let the client know in an appropriate way
                    # Schedule next read
                    await asyncio.sleep(self.polling_interval)
            except asyncio.CancelledError:
                logger.debug(f"{self.name} Stop polling")

        # Start task
        self.is_polling = True
        self.polling_task = asyncio.ensure_future(poll_coro())

    def _notify_listeners(self, value):
        """ Propagate value to listeners """
        if value:
            logger.debug(f"{self.name} notify listeners")
            # Feed listener queues
            for listener in self.listeners:
                listener.put_nowait(value)

    async def _subscribe(self):
        """ Start monitoring an attribute in the best possible way:
           * change_event
           * periodic_event
           * active_polling
        """
        try:
            # Change event
            await self._subscribe_events(EventType.CHANGE_EVENT)
        except DevFailed:
            try:
                # Periodic Event
                await self._subscribe_events(EventType.PERIODIC_EVENT)
            except DevFailed:
                # Start a periodic polling task
                self._start_polling_task()

    def _unsubscribe(self):
        """ Unsubscibe from event channels or cancel polling task"""
        logger.debug(f"{self.name} Unsubscribe event")
        if self.event_id:
            # Unsubscribe event
            self.device_proxy.unsubscribe_event(self.event_id)
        elif self.is_polling:
            # Stop polling task
            self.is_polling = False
            if not self.polling_task.done():
                self.polling_task.cancel()
        elif not self.subscription_task.done():
            # Subscription is not over, cancel it
            self.subscription_task.cancel()
