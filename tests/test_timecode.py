import pytest
from kpkontrol import timecode

def test_timecode(frame_rate_defs):
    flt_val = frame_rate_defs['float']
    frac_val = frame_rate_defs['fraction']

    class Listener(object):
        def __init__(self, tc):
            self.tc = tc
            self.last_value = str(tc)
            tc.bind(on_change=self.on_tc_change)
        def on_tc_change(self, *args, **kwargs):
            tc = kwargs.get('obj')
            assert tc is self.tc
            self.last_value = str(tc)

    frame_rate = timecode.FrameRate(frac_val.numerator, frac_val.denominator)

    if frac_val.denominator == 1001:
        df_flags = [True, False]
    else:
        df_flags = [False]
    print('frame_rate: ', frame_rate)
    for df in df_flags:
        print('drop_frame: ', df)
        frame_format = timecode.FrameFormat(rate=frame_rate, drop_frame=df)
        start_tc = timecode.Timecode(frame_format=frame_format)
        tc = None
        listener = None
        next_tc = None
        prev_tc = None
        for frame_count in range(1, 43202):
            fr_secs = float(frame_count / frame_rate)
            if tc is None:
                tc = timecode.Timecode.from_frames(frame_count, frame_format)
                listener = Listener(tc)
            else:
                tc += frame_count - tc.total_frames
                assert listener.last_value == str(tc)

            if next_tc is not None:
                assert next_tc.total_frames == tc.total_frames
                assert str(next_tc) == str(tc)

            assert tc.total_frames == frame_count

            if frac_val.denominator == 1:
                dt = tc.datetime
                assert dt.strftime('%H:%M:%S') == tc.get_tc_string()[:8]
                assert dt.hour == tc.hour.value
                assert dt.minute == tc.minute.value
                assert dt.second == tc.second.value
                dt_microsecond = dt.microsecond / 1e6
                assert dt_microsecond == pytest.approx(float(tc.value / frame_rate), rel=1e-3)


            if prev_tc is not None:
                tc2 = tc - 1
                assert tc2.total_frames == prev_tc.total_frames
                assert str(tc2) == str(prev_tc)

            next_tc = tc + 1

            assert fr_secs == pytest.approx(tc.total_seconds, rel=1e-1)


            ## Disable these for now since each iteration requires ** 2 CPU
            # tc_delta = start_tc + tc
            # assert tc_delta.total_frames == tc.total_frames == frame_count
            # assert tc_delta.total_seconds == tc.total_seconds

            prev_tc = tc.copy()

def test_timecode_set(frame_rate_defs):
    flt_val = frame_rate_defs['float']
    frac_val = frame_rate_defs['fraction']

    class Listener(object):
        def __init__(self, tc):
            self.tc = tc
            self.last_value = str(tc)
            tc.bind(on_change=self.on_tc_change)
        def on_tc_change(self, *args, **kwargs):
            tc = kwargs.get('obj')
            assert tc is self.tc
            self.last_value = str(tc)

    frame_rate = timecode.FrameRate(frac_val.numerator, frac_val.denominator)
    frame_format = timecode.FrameFormat(rate=frame_rate)

    tc = timecode.Timecode(frame_format=frame_format)
    listener = Listener(tc)

    tc_counter = timecode.Timecode(frame_format=frame_format)
    hmsf_keys = ['hours', 'minutes', 'seconds', 'frames']
    while True:
        tc.set(**{k:v.value for k, v in zip(hmsf_keys, tc_counter.get_hmsf())})
        assert listener.last_value == str(tc_counter) == str(tc)
        tc_counter += 1
        if tc_counter.hour.value >= 1 and tc_counter.minute.value > 0:
            break
