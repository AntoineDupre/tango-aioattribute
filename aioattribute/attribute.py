""" Handle tango subscription/polling for an attribute"""
import asyncio
import logging as logger

from tango import EventType, DevFailed, GreenMode, DeviceProxy, ExtractAs


class Attribute:
    """ Handle tango subscription/polling for one attribute"""

    # pylint: disable=too-many-instance-attributes
    # This does not seem to be an unreasonable number of attributes in this case
    # TODO should we initialise some of these in a separate call?
    def __init__(self, name, use_evt=False, polling_interval=3):
        self.name = name
        self.use_evt = use_evt

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

    async def add_listener(self, listener):
        """ Subscribe to event or append a new listener
        to the event callback.
        Event subscription is not blocking (delegated to a task)"""
        logger.debug(
            f"{self.name} Add listener, number of listeners "
            f"before addition: {len(self.listeners)}"
        )
        # Append listener
        self.listeners.append(listener)
        # First client, setup tango connection
        if len(self.listeners) <= 1:
            await self._subscribe()

    async def remove_listener(self, listener):
        """ Remove listener on listener from event notification"""
        # Unsubscribe to the event if only the listener to be removed is listening to it
        if len(self.listeners) == 1:
            await self._unsubscribe()
        logger.debug(
            f"{self.name} Remove listener, number of listeners "
            f"before removal: {len(self.listeners)}"
        )
        self.listeners.remove(listener)

    def _on_event(self, event):
        """ Tango event callback """
        logger.debug(
            f"{self.name} Event callback, type: {event.event}, error: {event.err}"
        )
        if event.err:
            logger.error(f"{self.name} Event error: \n{event}")
        # Propagate event to listeners
        self._notify_listeners(event.attr_value)

    async def _subscribe_events(self, event_type):
        """ Try to connect to a tango event channel """
        # TODO, Be sure to not erase event id
        self.event_id = await self.device_proxy.subscribe_event(
            self.attr,
            event_type,
            self._on_event,
            extract_as=ExtractAs.List,
            green_mode=GreenMode.Asyncio,
        )
        logger.info(
            f"{self.name} Subscribed to {event_type} (event id: {self.event_id})"
        )

    async def _read_attribute(self):
        try:
            # Read attribute
            read = await self.device_proxy.read_attribute(
                self.attr, extract_as=ExtractAs.List
            )
            # Check if value field exists. This is a bug in Tango where it does not include value field on
            # DeviceAttribute object if DataFormat is SPECTRUM or IMAGE and x and y dimensions are 0
            value = getattr(read, "value", None)
            logger.debug(f"{self.name} Read value {value}")
            self._notify_listeners(read)
        except DevFailed as error:
            logger.error(f"{self.name} DevFailed when reading {self.attr}")
            logger.debug(f"{error}")
            # TODO: Let the client know in an appropriate way

    async def poller(self):
        """ Polling task coroutine """
        logger.info(f"{self.name} Start polling")
        try:
            while self.is_polling:
                await self._read_attribute()
                # Schedule next read
                await asyncio.sleep(self.polling_interval)
        except asyncio.CancelledError:
            logger.info(f"{self.name} Stop polling")

    def _start_polling_task(self):
        """ Start a periodic polling task to read the attribute"""
        # Start task
        self.is_polling = True
        self.polling_task = asyncio.ensure_future(self.poller())

    def _notify_listeners(self, value):
        """ Propagate value to listeners """
        if value:
            logger.debug(f"{self.name} Notify listeners")
            # Feed listener queues
            for listener in self.listeners:
                listener.put_nowait((self.device, value))

    async def _try_events_subscription(self):
        try:
            # Change event
            logger.debug(
                f"{self.name} Try subscribing to {EventType.CHANGE_EVENT}"
            )
            await self._subscribe_events(EventType.CHANGE_EVENT)
        except DevFailed:
            # Periodic Event
            logger.debug(
                f"{self.name} Try subscribing to {EventType.PERIODIC_EVENT}"
            )
            await self._subscribe_events(EventType.PERIODIC_EVENT)

    async def _subscribe(self):
        """ Start monitoring an attribute in the best possible way:

            Note: there is currently a feature toggle to disable the Tango polling
            which is what determines the value of  use_evt. If the polling feature is
            switched off (i.e. use_evt is false) then we can bypass even trying to subscribe

           * change_event
           * periodic_event
           * active_polling
        """
        if self.use_evt:
            try:
                await self._try_events_subscription()
            except DevFailed:
                self._start_polling_task()
        else:
            self._start_polling_task()

    async def _unsubscribe(self):
        """ Unsubscibe from event channels or cancel polling task"""
        logger.info(f"{self.name} Unsubscribe/Stop polling")
        if self.use_evt:
            if self.event_id:
                # Unsubscribe event
                await self.device_proxy.unsubscribe_event(self.event_id)
                logger.debug(
                    f"{self.name} Unsubscribed from event {self.event_id}"
                )
            elif self.is_polling:
                # Stop polling task
                self.is_polling = False
                if not self.polling_task.done():
                    self.polling_task.cancel()
                logger.debug(f"{self.name} Polling stopped")
        else:
            self.polling_task.cancel()
