import asyncio
from .attribute import Attribute

try:
    from contextlib import asynccontextmanager as contextmanager  # +3.7
except ImportError:
    from async_generator import asynccontextmanager as contextmanager


class SubscriptionManager:
    """ Manage attribute subscriptions """

    def __init__(self):
        self.attributes = {}
        self.lock = asyncio.Lock()

    def _get_attribute(self, name):
        """ Create a new attribute subscribion or return an existing one"""
        if name not in self.attributes:
            self.attributes[name] = Attribute(name, polling_interval=1)
        return self.attributes[name]

    @contextmanager
    async def attribute_reads(self, names):
        """ Use as a context manager
         * Handle event subscription and unsubscription
         * Return an asynchronous generator
         * Spawn a value for each event
        """
        # Create listener
        listener = asyncio.Queue()
        # Tango does not support concurent subscribitons
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
                    # TODO: Make listener itearble ?
                    read = await listener.get()
                    listener.task_done()
                    yield read
            except asyncio.CancelledError:
                return

        # Yield generator
        yield async_iterator()
        # Unregister client
        for name in names:
            attribute = self._get_attribute(name)
            attribute.remove_listener(listener)
