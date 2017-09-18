import asyncio
import pytest

from kpkontrol.device import KpDevice

@pytest.mark.asyncio
async def test_meta_clip(kp_http_device_servers):

    server = kp_http_device_servers['FakeDevice_0']
    await server.start()

    device = await KpDevice.create(host_address=server.host_address)

    await device.transport.go_to_clip('A003SC10TK23.mov')

    meta_clip = device.transport.meta_clip
    assert meta_clip.source_clip is device.clips['A003SC10TK23.mov']

    for attr in ['name', 'start_timecode', 'total_frames']:
        assert getattr(device.transport.clip, attr) == getattr(meta_clip, attr)


    # Offset cue in/out by 20 frames
    start_tc = meta_clip.start_timecode.copy()
    start_tc += 20

    end_tc = meta_clip.end_timecode.copy()
    end_tc -= 20

    orig_duration = meta_clip.total_frames

    await device.transport.set_cue_in(start_tc)
    await device.transport.set_cue_out(end_tc)

    assert meta_clip.total_frames == orig_duration - 40
    assert device.transport.frame_range[1] - device.transport.frame_range[0] == meta_clip.total_frames


    # Load another clip and return to original
    await device.transport.go_to_clip('A003SC10TK22.mov')

    await device.transport.go_to_clip('A003SC10TK23.mov')


    # Now the cue in should be the current timecode
    assert device.transport.timecode == meta_clip.start_timecode
    assert str(device.all_parameters['eParamID_DisplayTimecode'].value) == str(meta_clip.start_timecode)

    # Roll back to before the cue in and start playing
    await device.transport.go_to_timecode('00:00:00;00')
    assert str(device.transport.timecode) == '00:00:00;00'

    await device.transport.play()

    # play() should roll to the cue in point before beginning to play
    assert device.transport.timecode >= meta_clip.start_timecode

    # Play for 2 seconds and set cue out to the current tc value
    await asyncio.sleep(2)
    await device.transport.set_cue_out()
    print(meta_clip.end_timecode)

    await device.transport.pause()
    await asyncio.sleep(1)

    # Roll back and play to make sure it stops at the cue out point
    await device.transport.go_to_timecode(meta_clip.start_timecode)
    await asyncio.sleep(.5)
    await device.transport.play()

    await asyncio.sleep(4)

    assert not device.transport.playing
    assert device.transport.timecode == meta_clip.end_timecode



    await device.stop()
    await server.stop()
