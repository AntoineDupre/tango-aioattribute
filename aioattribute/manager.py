""" Manage attribute subscriptions """
import asyncio

from .attribute import Attribute
import logging as logger

try:
    from contextlib import asynccontextmanager as contextmanager  # +3.7
except ImportError:
    from async_generator import asynccontextmanager as contextmanager





class SubscriptionManager:
    """ Manage attribute subscriptions
    :param use_evt boolean flag - attempt to use event based polling if true (default false)
    :param polling_interval: polling interval (default is 1 sec)
    """

    def __init__(self, use_evt=False, polling_interval=1):

        logger.info(f"====================== Creating New Subscription Manager ==============")
        if use_evt:
            logger.info(f"Subscription to Tango events is ENABLED "
                        f"- TangoGQL will attempt to subscribe to Tango events")
        else:
            logger.info(f"Subscription to Tango events is DISABLED "
                        f"- TangoGQL will self poll")

        self.attributes = {}
        self.event_allowed = use_evt
        self.polling_interval = polling_interval
        self.lock = asyncio.Lock()

    def _get_attribute(self, name):
        """ Create a new attribute subscription or return an existing one"""
        if name not in self.attributes:
            attr = Attribute(name,
                             use_evt=self.event_allowed,
                             polling_interval=self.polling_interval)
            self.attributes[name] = attr
        return self.attributes[name]

    @contextmanager
    async def attribute_reads(self, names):
        """ Use as a context manager
         * Handle event subscription and unsubscription
         * Return an asynchronous generator
         * Spawn a value for each event
        """
        # Create listener
        logger.debug(f"Create listener for {names}")
        listener = asyncio.Queue()
        # Tango does not support concurrent subscriptions
        # Be sure that the subscription are done one by one
        async with self.lock:
            for name in names:
                # Send listener to all the required attributes.
                attribute = self._get_attribute(name)
                await attribute.add_listener(listener)

        async def async_iterator():
            """ asynchronous iterator to yield event from attributes """
            try:
                while True:
                    # TODO: Make listener iterable ?
                    read = await listener.get()
                    listener.task_done()
                    yield read
            except asyncio.CancelledError:
                return

        # Yield generator
        yield async_iterator()
        # Unregister client

        async with self.lock:
            for name in names:
                attribute = self._get_attribute(name)
                await attribute.remove_listener(listener)

