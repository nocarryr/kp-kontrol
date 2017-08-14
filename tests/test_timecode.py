import datetime
from fractions import Fraction

from kpkontrol import timecode

def test_frame_rate(frame_rate_defs):
    frame_rate_floats = frame_rate_defs['floats']
    frame_rate_fractions = frame_rate_defs['fractions']

    frame_rate_objs = []

    for flt_val, frac_val in zip(frame_rate_floats, frame_rate_fractions):
        frame_rate = timecode.FrameRate(frac_val.numerator, frac_val.denominator)
        assert frame_rate.value == frac_val
        if flt_val == int(flt_val):
            assert frame_rate.float_value == flt_val
        else:
            assert round(frame_rate.float_value, 2) == round(flt_val, 2)
        assert str(frame_rate) == '{}/{}'.format(frac_val.numerator, frac_val.denominator)
        assert float(repr(frame_rate).split('(')[1].split(')')[0]) == flt_val
        assert frame_rate.value in timecode.FrameRate.registry
        frame_rate_objs.append(frame_rate)

    for i, frame_rate in enumerate(frame_rate_objs):

        ## FrameRate.registry check
        frame_rate2 = timecode.FrameRate(frame_rate.numerator, frame_rate.denom)
        assert frame_rate is frame_rate2
        assert id(frame_rate) == id(frame_rate2)

        ## Equality checking (same values)
        assert frame_rate2 >= frame_rate
        assert frame_rate2 <= frame_rate
        assert frame_rate2 == frame_rate

        assert frame_rate >= frame_rate2
        assert frame_rate <= frame_rate2
        assert frame_rate == frame_rate2

        if i > 0:
            prev_frame_rate = frame_rate_objs[i-1]
        else:
            prev_frame_rate = None

        try:
            next_frame_rate = frame_rate_objs[i+1]
        except IndexError:
            next_frame_rate = None

        ## gt, ge, lt, le, eq, ne checks
        if prev_frame_rate is not None:
            assert prev_frame_rate != frame_rate
            assert prev_frame_rate < frame_rate
            assert frame_rate > prev_frame_rate
            assert prev_frame_rate <= frame_rate
            assert not prev_frame_rate >= frame_rate
            assert frame_rate >= prev_frame_rate
            assert not frame_rate <= prev_frame_rate
            assert not frame_rate == prev_frame_rate
            assert not prev_frame_rate == frame_rate

        if next_frame_rate is not None:
            assert next_frame_rate != frame_rate
            assert next_frame_rate > frame_rate
            assert frame_rate < next_frame_rate
            assert next_frame_rate >= frame_rate
            assert frame_rate <= next_frame_rate
            assert not next_frame_rate <= frame_rate
            assert not frame_rate >= next_frame_rate
            assert not frame_rate == next_frame_rate
            assert not next_frame_rate == frame_rate


def test_frame_rate_ops(frame_rate_defs):

    for frac_val in frame_rate_defs['fractions']:
        frame_rate = timecode.FrameRate(frac_val.numerator, frac_val.denominator)

        for frame_count in range(1, 43202):
            fr_secs = float(frame_rate * frame_count)
            flt_secs = frame_rate.float_value * frame_count
            if frame_rate.denom != 1:
                if frame_count % frame_rate.denom == 0:
                    assert flt_secs == fr_secs
                elif fr_secs < 1:
                    assert round(flt_secs, 2) == round(fr_secs, 2)
                else:
                    assert round(flt_secs, 0) == round(fr_secs, 0)
            else:
                assert flt_secs == fr_secs

def test_timecode(frame_rate_defs):

    for frac_val in frame_rate_defs['fractions']:
        frame_rate = timecode.FrameRate(frac_val.numerator, frac_val.denominator)

        if frac_val.denominator == 1001:
            df_flags = [True, False]
        else:
            df_flags = [False]
        print('frame_rate: ', frame_rate)
        for df in df_flags:
            print('drop_frame: ', df)
            start_tc = timecode.Timecode(0, 0, 0, 0, frame_rate, drop_frame=df)
            for frame_count in range(1, 43202):
                fr_secs = frame_count / frame_rate
                tc = timecode.Timecode.from_frames(frame_count, frame_rate, drop_frame=df)
                if tc.total_frames != frame_count:
                    print('frame_count={}, tc={}, total_frames={}'.format(frame_count, tc, tc.total_frames))
                assert tc.total_frames == frame_count
                if df:
                    assert round(float(fr_secs), 2) == round(tc.total_seconds, 2)
                else:
                    assert float(fr_secs) == tc.total_seconds
                tc_delta = start_tc + tc
                assert tc_delta.total_frames == tc.total_frames == frame_count
                assert tc_delta.total_seconds == tc.total_seconds
