import json
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

    # Allow a margin of +/- 2 frames
    tc_diff = device.transport.timecode.total_frames - meta_clip.end_timecode.total_frames
    assert -2 < tc_diff < 2



    await device.stop()
    await server.stop()

@pytest.mark.asyncio
async def test_meta_clip_serialization(kp_http_device_servers):

    server = kp_http_device_servers['FakeDevice_0']
    await server.start()

    device1 = await KpDevice.create(host_address=server.host_address)
    session = device1.session

    await device1.transport.go_to_clip('A003SC10TK23.mov')

    await device1.transport.play()

    await asyncio.sleep(2)

    await device1.transport.set_cue_in()

    await device1.transport.pause()
    await asyncio.sleep(1)

    await device1.transport.go_to_timecode('00:00:10;00')
    await asyncio.sleep(.5)

    await device1.transport.set_cue_out()

    meta_clip = device1.transport.meta_clip
    assert meta_clip.start_timecode.total_frames > 0
    assert meta_clip.end_timecode == device1.transport.timecode

    data = device1._serialize()
    s = json.dumps(data)

    kw = json.loads(s)
    kw['session'] = session
    device2 = await KpDevice.create(**kw)

    for key, meta_clip1 in device1.meta_clips.items():
        assert key in device2.meta_clips
        meta_clip2 = device2.meta_clips[key]

        assert meta_clip1.name == meta_clip2.name
        assert meta_clip1.source_clip_name == meta_clip2.source_clip_name
        assert meta_clip1.start_timecode == meta_clip2.start_timecode
        assert meta_clip1.end_timecode == meta_clip2.end_timecode
        assert meta_clip1.duration_tc == meta_clip2.duration_tc
        assert meta_clip1.total_frames == meta_clip2.total_frames

    assert device1.transport.meta_clip.name == device2.transport.meta_clip.name

    await device2.stop(close_session=False)
    await device1.stop()

    await server.stop()
