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

    async def wait_for_events(device, num_events=3):
        for i in range(num_events):
            device._listen_event.clear()
            await device._listen_event.wait()

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
        await wait_for_events(device)
        assert device.transport.paused
        check_transport_state(device, server.device)

        # Wait for updates
        await wait_for_events(device)

        assert str(device.transport.timecode) == str(server.device.timecode)
        assert device.transport.timecode > device.transport.clip.start_timecode

        # Cue the device to the start timecode for the clip
        cue_tc = device.transport.clip.start_timecode.copy()

        await device.transport.go_to_timecode(cue_tc)
        await wait_for_events(device)

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
        await wait_for_events(device)

        # Should be playing since it was previously
        # kpkontrol.device.Transport.go_to_timecode performs this logic
        assert device.transport.playing
        assert device.transport.timecode < now_tc

        await device.transport.pause()
        await wait_for_events(device)

        assert device.transport.paused
        check_transport_state(device, server.device)
        assert device.transport.timecode == server.device.timecode

        # Single step forward and reverse
        now_tc = device.transport.timecode.copy()

        await device.transport.step_forward()
        await wait_for_events(device)

        assert device.transport.timecode == now_tc + 1

        await device.transport.step_reverse()
        await wait_for_events(device)

        assert device.transport.timecode == now_tc

        # Step 10 frames forward and reverse
        await device.transport.step_forward(10)
        await wait_for_events(device)

        assert device.transport.timecode == now_tc + 10

        await device.transport.step_reverse(10)
        await wait_for_events(device)

        assert device.transport.timecode == now_tc

        # Load a clip and check transport and timecode states
        next_clip = None
        for clip in device.clips.values():
            if clip.name == device.transport.clip.name:
                continue
            next_clip = clip
            break
        assert next_clip is not None

        await device.transport.go_to_clip(next_clip.name)
        await wait_for_events(device)

        assert device.transport.clip is next_clip
        assert device.transport.paused
        check_transport_state(device, server.device)

        assert device.transport.timecode == next_clip.start_timecode
        assert device.transport.timecode == server.device.timecode

    for device in devices.values():
        await device.stop(close_session=False)
    session.close()
    for server in kp_http_device_servers.values():
        await server.stop()

@pytest.mark.asyncio
async def test_device_gang(kp_http_device_servers):

    server_devices = []
    for server in kp_http_device_servers.values():
        await server.start()
        server_devices.append(server.device)
    for device in server_devices[:]:
        await device.build_network_services_data(server_devices)

    devices = {}
    session = None
    for device_name, server in kp_http_device_servers.items():
        device = await KpDevice.create(host_address=server.host_address, session=session)
        if session is None:
            session = device.session
        devices[device_name] = device

        await asyncio.sleep(1)

        for network_device in device.network_devices.values():
            assert network_device.host_name in kp_http_device_servers.keys()
            assert network_device.host_address == kp_http_device_servers[network_device.host_name].host_address
            if network_device.host_name == device_name:
                assert network_device.is_host_device
                assert network_device is device.network_host_device
            else:
                assert network_device.is_host_device is False

    master_name = sorted(kp_http_device_servers.keys())[0]
    master_device = devices[master_name]


    await master_device.create_gang()

    assert master_device.network_host_device.gang_enabled
    assert master_device.network_host_device.gang_master

    for device in devices.values():
        if device is master_device:
            continue
        await device.update_gang_params()
        assert device.network_host_device.gang_enabled
        assert not device.network_host_device.gang_master
        assert device.network_host_device.host_address in master_device.network_host_device.gang_members


    await master_device.remove_gang()

    assert not master_device.network_host_device.gang_enabled
    assert not master_device.network_host_device.gang_master
    assert not len(master_device.network_host_device.gang_members)

    for device in devices.values():
        if device is master_device:
            continue
        await device.update_gang_params()
        assert not device.network_host_device.gang_enabled
        assert not device.network_host_device.gang_master


    for device in devices.values():
        await device.stop(close_session=False)
    session.close()
    for server in kp_http_device_servers.values():
        await server.stop()
