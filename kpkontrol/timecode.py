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
        obj = cls(frame_format=frame_format)
        for i in range(total_frames):
            obj.incr()
        return obj
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
    def __add__(self, other):
        obj = self.copy()
        if isinstance(other, Timecode):
            other = other.total_frames
        if isinstance(other, numbers.Number):
            obj += other
            return obj
        elif isinstance(other, datetime.timedelta):
            dt = self.datetime
            dt += other
            obj.from_dt(dt)
            return obj
        else:
            return NotImplemented
    def __sub__(self, other):
        obj = self.copy()
        if isinstance(other, Timecode):
            other = other.total_frames
        if isinstance(other, numbers.Number):
            obj -= other
            return obj
        elif isinstance(other, datetime.timedelta):
            dt = self.datetime
            dt -= other
            obj.from_dt(dt)
            return obj
        else:
            return NotImplemented
    def copy(self):
        f = self.__class__(frame_format=self.frame_format, total_frames=self.total_frames)
        f._value = self._value
        f.second._value = self.second._value
        f.minute._value = self.minute._value
        f.hour._value = self.hour._value
        return f
    def __str__(self):
        fmt = ':'.join(['{:02}'] * 3)
        if self.frame_format.drop_frame:
            fmt = ';'.join([fmt, '{:02}'])
        else:
            fmt = ':'.join([fmt, '{:02}'])
        return fmt.format(*[v.value for v in self.get_hmsf()])
