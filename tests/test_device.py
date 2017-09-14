import asyncio
import pytest

from kpkontrol.device import KpDevice

@pytest.mark.asyncio
async def test_device(kp_http_server, all_parameter_defs):
    await kp_http_server.start()
    host_address = kp_http_server.host_address

    device = KpDevice(host_address=host_address)
    await device.connect()

    assert set(device.all_parameters.keys()) == set(all_parameter_defs.keys())

    await device.set_parameter('eParamID_CurrentClip', 'A003SC10TK22.mov')
    await device.update_clips()

    assert device.transport.clip.name == 'A003SC10TK22.mov'
    assert str(device.transport.timecode) == "18:25:06;12"

    await device.set_parameter('eParamID_TransportState', 'Playing Forward')
    await device.transport.transport_param_get.get_value()

    assert device.transport.active
    assert device.transport.playing
    assert not device.transport.recording
    assert not device.transport.paused
    assert not device.transport.shuttle

    await device.set_parameter('eParamID_TransportState', 'Paused')
    await device.transport.stop()

    assert device.transport.active
    assert not device.transport.playing
    assert not device.transport.recording
    assert device.transport.paused
    assert not device.transport.shuttle

    await device.set_parameter('eParamID_TransportState', 'Recording')
    await device.transport.record()

    assert device.transport.active
    assert not device.transport.playing
    assert device.transport.recording
    assert not device.transport.paused
    assert not device.transport.shuttle

    await device.stop()
    assert not device.connected
    assert device._update_loop_fut is None
    assert device.session is None

    await kp_http_server.stop()
