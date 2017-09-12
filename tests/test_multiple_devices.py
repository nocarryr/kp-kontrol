import asyncio
import pytest

from kpkontrol.device import KpDevice

@pytest.mark.asyncio
async def test_dummy_device(kp_http_device_servers):

    server_devices = []
    for server in kp_http_device_servers.values():
        await server.start()
        server_devices.append(server.device)
    for device in server_devices[:]:
        await device.build_network_services_data(server_devices)

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

        # current_clip was selected and loaded on the device
        assert device.transport.playing
        assert device.transport.clip.name == server.device.current_clip.name
        check_transport_state(device, server.device)
        assert device.transport.timecode is not None

        # Roll for 5 seconds then pause
        await asyncio.sleep(5)
        await device.transport.pause()
        assert device.transport.paused
        check_transport_state(device, server.device)

        # Wait for updates
        device._listen_event.clear()
        await device._listen_event.wait()

        assert str(device.transport.timecode) == str(server.device.timecode)
        assert device.transport.timecode > device.transport.clip.start_timecode

        # Cue the device to the start timecode for the clip
        cue_tc = device.transport.clip.start_timecode.copy()

        await device.transport.go_to_timecode(cue_tc)
        device._listen_event.clear()
        await device._listen_event.wait()

        # Should be paused since it was previously
        assert device.transport.paused
        assert device.transport.timecode == cue_tc

        # Roll for 5 seconds
        await device.transport.play()
        await asyncio.sleep(5)
        assert device.transport.playing
        assert device.transport.timecode > cue_tc

        now_tc = device.transport.timecode.copy()

        await device.transport.go_to_frame(cue_tc.total_frames)

        # Should be playing since it was previously
        # kpkontrol.device.Transport.go_to_timecode performs this logic
        assert device.transport.playing
        assert device.transport.timecode < now_tc

        await device.transport.pause()
        assert device.transport.paused
        check_transport_state(device, server.device)

        device._listen_event.clear()
        await device._listen_event.wait()

        # Single step forward and reverse
        now_tc = device.transport.timecode.copy()

        await device.transport.step_forward()
        device._listen_event.clear()
        await device._listen_event.wait()

        assert device.transport.timecode == now_tc + 1

        await device.transport.step_reverse()
        device._listen_event.clear()
        await device._listen_event.wait()

        assert device.transport.timecode == now_tc

        # Step 10 frames forward and reverse
        await device.transport.step_forward(10)
        device._listen_event.clear()
        await device._listen_event.wait()

        assert device.transport.timecode == now_tc + 10

        await device.transport.step_reverse(10)
        device._listen_event.clear()
        await device._listen_event.wait()

        assert device.transport.timecode == now_tc

    for device in devices.values():
        await device.stop(close_session=False)
    session.close()
    for server in kp_http_device_servers.values():
        await server.stop()
