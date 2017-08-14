import datetime
from fractions import Fraction

from kpkontrol import actions, objects, timecode

def test_get_clips(kp_http_server):
    action = actions.GetClips(kp_http_server)
    assert action.full_url == 'http://{}/clips?action=get_clips'.format(kp_http_server)

    results = action()
    assert isinstance(results, list)
    assert len(results) == 1

    clip = results[0]
    assert isinstance(clip, objects.Clip)
    assert isinstance(clip.format, objects.ClipFormat)
    assert isinstance(clip.format.frame_rate, timecode.FrameRate)
    assert isinstance(clip.start_timecode, timecode.Timecode)
    assert isinstance(clip.duration_tc, timecode.Timecode)

    assert clip.name == 'A003SC10TK22.mov'
    assert clip.total_frames == 61429
    assert clip.timestamp == datetime.datetime(2017, 8, 5, 18, 59, 16)
    assert clip.audio_channels == 2
    assert clip.format.width == 1920
    assert clip.format.height == 1080
    assert clip.format.frame_rate.value == Fraction(30000, 1001)
    assert clip.format.interlaced is True
    assert clip.format.fourcc == 'apcn'
    assert str(clip.format) == '1920x1080i29.97'
    assert str(clip.start_timecode) == '18:25:06;12'
    assert str(clip.duration_tc) == '00:34:09:20'
