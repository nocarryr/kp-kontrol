import datetime
import numbers

from pyltc.frames import FrameRate as _FrameRate
from pyltc.frames import FrameFormat, Frame
from kpkontrol.base import ObjectBase

class FrameRate(_FrameRate):
    defaults = {
        23.98:(24000, 1001),
        24:(24, 1),
        25:(25, 1),
        29.97:(30000, 1001),
        30:(30, 1),
        50:(50, 1),
        59.94:(60000, 1001),
        60:(60, 1),
        119.88:(120000, 1001),
        120:(120, 1),
    }
    @classmethod
    def from_float(cls, value):
        if not isinstance(value, numbers.Number):
            value = float(value)
        return super(FrameRate, cls).from_float(value)

class Timecode(Frame, ObjectBase):
    _events_ = ['on_change']
    def __new__(cls, *args, **kwargs):
        return ObjectBase.__new__(cls)
    @classmethod
    def parse(cls, tc_str, frame_rate, drop_frame=False):
        if ';' in tc_str:
            drop_frame = True
            tc_str = ':'.join(tc_str.split(';'))
        keys = ['hours', 'minutes', 'seconds', 'frames']
        kwargs = {k:int(v) for k, v in zip(keys, tc_str.split(':'))}
        kwargs['frame_format'] = FrameFormat(rate=frame_rate, drop_frame=drop_frame)
        return cls(**kwargs)
    @classmethod
    def from_frames(cls, total_frames, frame_format):
        return cls(frame_format=frame_format, total_frames=total_frames)
    @property
    def total_seconds(self):
        s = int((self.total_frames-self.value) / self.frame_format.rate)
        micro_s = self.frame_times[self.value]
        s += float(micro_s)
        return s
    @property
    def timedelta(self):
        return datetime.timedelta(seconds=self.total_seconds)
    @property
    def datetime(self):
        t = datetime.time()
        dt = datetime.datetime.combine(datetime.date(2000, 1, 1), t)

        dt += self.timedelta
        return dt
    def set_value(self, value):
        super(Timecode, self).set_value(value)
        self.emit('on_change', obj=self)
    def set(self, **kwargs):
        prev = self.value
        super(Timecode, self).set(**kwargs)
        if self.value == prev:
            self.emit('on_change', obj=self)
    def set_from_string(self, tc_str):
        if self.frame_format.drop_frame:
            tc_str = ':'.join(tc_str.split(';'))
        hmsf = [int(v) for v in tc_str.split(':')]
        keys = ['hours', 'minutes', 'seconds', 'frames']
        self.set(**{k:v for k, v in zip(keys, hmsf)})
