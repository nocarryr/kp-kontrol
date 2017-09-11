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

@pytest.mark.asyncio
async def test_dummy_device(kp_http_device_servers):

    for server in kp_http_device_servers.values():
        await server.start()


    def check_transport_state(device, fake_device):
        assert device.transport.playing is fake_device.playing
        assert device.transport.paused is fake_device.paused
        assert device.transport.stopped is fake_device.stopped

    devices = {}
    session = None
    for device_name, server in kp_http_device_servers.items():
        device = await KpDevice.create(host_address=server.host_address, session=session)
        if session is None:
            session = device.session
        devices[device_name] = device

        assert device.name == server.device.name
        assert device.serial_number == server.device.serial_number
        await asyncio.sleep(1)
        assert set(device.clips.keys()) == set(server.device.clips.keys())

        check_transport_state(device, server.device)

        assert device.transport.clip is server.device.current_clip is None

        await device.transport.play()

        await asyncio.sleep(1)

        assert device.transport.playing
        assert device.transport.clip.name == server.device.current_clip.name
        check_transport_state(device, server.device)
        assert device.transport.timecode is not None

        await asyncio.sleep(5)

        await device.transport.pause()
        assert device.transport.paused
        check_transport_state(device, server.device)
        await asyncio.sleep(.2)
        assert str(device.transport.timecode) == str(server.device.timecode)
        assert device.transport.timecode > device.transport.clip.start_timecode

        cue_tc = device.transport.clip.start_timecode.copy()

        await device.transport.go_to_timecode(cue_tc)
        await asyncio.sleep(1)
        assert device.transport.paused
        assert device.transport.timecode == cue_tc

        await device.transport.play()
        await asyncio.sleep(5)

        assert device.transport.playing
        assert device.transport.timecode > cue_tc
        now_tc = device.transport.timecode.copy()

        await device.transport.go_to_frame(cue_tc.total_frames)
        assert device.transport.playing
        assert device.transport.timecode < now_tc



    for device in devices.values():
        await device.stop(close_session=False)
    session.close()
    for server in kp_http_device_servers.values():
        await server.stop()
