import asyncio
from .attribute import Attribute

try:
    from contextlib import asynccontextmanager as contextmanager  # +3.7
except ImportError:
    from async_generator import asynccontextmanager as contextmanager

from loguru import logger


class SubscriptionManager:
    """ Manage attribute subscriptions """

    def __init__(self):
        self.attributes = {}

    def _get_attribute(self, name):
        """ Create a new attribute subscribion or return an existing one"""
        if name not in self.attributes:
            self.attributes[name] = Attribute(name)
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
        for name in names:
            # TODO Event subsction is failling if we subscribe to all event at
            # the same time. So, does it makes sense to subscribe in a task
            # if we have to sleep there ?
            # See tango issue https://github.com/tango-controls/pytango/issues/307
            await asyncio.sleep(0.01)
            # Send listener to all the required attributes.
            attribute = self._get_attribute(name)
            attribute.add_listener(listener)

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
