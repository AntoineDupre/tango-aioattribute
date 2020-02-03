# Imports
import socket

import pytest

from aioattribute.attribute import Attribute
from aioattribute.subscription import SubscriptionManager
from tango.asyncio import DeviceProxy as asyncio_DeviceProxy
from tango.server import Device, attribute, command
from tango.test_utils import DeviceTestContext


# PyTango helpers

def get_open_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port


# Test device

class EventDevice(Device):
    def init_device(self):
        self.set_change_event("change_attr", True, False)
        self.set_change_event("periodic_attr", True, False)
        self._change_attr = 1
        self._periodic_attr = 1
        self._polled_attr = 1

    @attribute
    def change_attr(self):
        return self._change_attr

    @attribute
    def periodic_attr(self):
        return self._periodic_attr

    @attribute
    def polled_attr(self):
        return self._polled_attr

    @command
    def send_change_attr(self):
        self._change_attr += 1
        self.push_change_event("change_attr", self._change_attr)

    @command
    def send_periodic_attr(self):
        self._periodic_attr += 1
        self.push_change_event("periodic_attr", self._periodic_attr)

    @command
    def send_polled_attr(self):
        self._polled_attr += 1


# Fixtures

@pytest.fixture(params=["change_attr", "periodic_attr", "polled_attr"])
def event_type(request):
    return request.param


# Tests

@pytest.mark.asyncio
async def test_event(event_type):  # &event_loop, event_device):
    port = get_open_port()
    context = DeviceTestContext(EventDevice, port=port, process=True)
    with context:
        event_device = await asyncio_DeviceProxy(context.get_device_access())
        sub = SubscriptionManager()
        event_count = 0
        async with sub.attribute_reads(
            [context.get_device_access() + "/" + event_type]
        ) as m:
            async for device, read in m:
                event_count += 1
                assert read.value == event_count
                await event_device.command_inout(
                    "send_{}".format(event_type)
                )  # , wait=True)
                if event_count > 3:
                    break
        assert event_count == 4


@pytest.mark.asyncio
async def test_multiple_source():  # &event_loop, event_device):
    port = get_open_port()
    context = DeviceTestContext(EventDevice, port=port, process=True)
    with context:
        event_device = await asyncio_DeviceProxy(context.get_device_access())
        sub = SubscriptionManager()
        entries = []
        event_count = 0
        attrs = ["change_attr", "periodic_attr", "polled_attr"]
        attr_names = [
            context.get_device_access() + "/" + attr for attr in attrs
        ]
        async with sub.attribute_reads(attr_names) as m:
            event_device.command_inout("send_{}".format(attrs[0]))
            event_device.command_inout("send_{}".format(attrs[1]))
            async for device, evt in m:
                assert evt.value
                event_count += 1
                print(evt)
                entries.append(device + "/" + evt.name)
                if event_count > 5:
                    break
        assert event_count == 6
        for attr in attr_names:
            assert attr in entries
