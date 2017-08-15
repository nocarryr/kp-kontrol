import datetime
import math
from fractions import Fraction

class FrameRate(object):
    registry = {}
    def __new__(cls, numerator, denom=1):
        key = Fraction(numerator, denom)
        if key in cls.registry:
            return cls.registry[key]
        obj = super(FrameRate, cls).__new__(cls)
        cls.registry[key] = obj
        return obj
    def __init__(self, numerator, denom=1):
        self.__numerator = numerator
        self.__denom = denom
        self.__value = Fraction(numerator, denom)
    @property
    def numerator(self):
        return self.__numerator
    @property
    def denom(self):
        return self.__denom
    @property
    def value(self):
        return self.__value
    @property
    def float_value(self):
        return float(self.value)
    def __eq__(self, other):
        if not isinstance(other, FrameRate):
            return NotImplemented
        return self.value == other.value
    def __ne__(self, other):
        if not isinstance(other, FrameRate):
            return NotImplemented
        return self.value != other.value
    def __lt__(self, other):
        if not isinstance(other, FrameRate):
            return NotImplemented
        return self.value < other.value
    def __le__(self, other):
        if not isinstance(other, FrameRate):
            return NotImplemented
        return self.value <= other.value
    def __gt__(self, other):
        if not isinstance(other, FrameRate):
            return NotImplemented
        return self.value > other.value
    def __ge__(self, other):
        if not isinstance(other, FrameRate):
            return NotImplemented
        return self.value >= other.value
    def __mul__(self, other):
        return self.value * other
    def __rmul__(self, other):
        return other * self.value
    def __div__(self, other):
        return self.value / other
    def __rdiv__(self, other):
        return other / self.value
    def __truediv__(self, other):
        return self.value / other
    def __rtruediv__(self, other):
        return other / self.value
    def __floordiv__(self, other):
        return self.value // other
    def __rfloordiv__(self, other):
        return other // self.value
    def __mod__(self, other):
        return self.value % other
    def __rmod__(self, other):
        return other % self.value
    def __repr__(self):
        return '<FrameRate: {self} ({self.float_value:05.2f})>'.format(self=self)
    def __str__(self):
        return '{self.numerator}/{self.denom}'.format(self=self)


class Timecode(object):
    def __init__(self, hour, minute, second, frame, frame_rate, drop_frame=False):
        self._total_frames = None
        self._total_seconds = None
        self._dropped_frames = None
        self.hour = hour
        self.minute = minute
        self.second = second
        self.frame = frame
        self.frame_rate = frame_rate
        self.drop_frame = drop_frame
        if self.drop_frame and self.minute % 10:
            if self.frame_rate == FrameRate(30000, 1001) and self.frame < 2:
                self.frame += 2
            elif self.frame_rate == FrameRate(60000, 1001) and self.frame < 4:
                self.frame += 4
    @property
    def hour(self):
        return getattr(self, '_hour', None)
    @hour.setter
    def hour(self, value):
        if value == self.hour:
            return
        self._total_frames = None
        self._total_seconds = None
        self._dropped_frames = None
        self._hour = value
    @property
    def minute(self):
        return getattr(self, '_minute', None)
    @minute.setter
    def minute(self, value):
        if value == self.minute:
            return
        self._total_frames = None
        self._total_seconds = None
        self._dropped_frames = None
        self._minute = value
    @property
    def second(self):
        return getattr(self, '_second', None)
    @second.setter
    def second(self, value):
        if value == self.second:
            return
        self._total_frames = None
        self._total_seconds = None
        self._dropped_frames = None
        self._second = value
    @property
    def frame(self):
        return getattr(self, '_frame', None)
    @frame.setter
    def frame(self, value):
        if value == self.frame:
            return
        self._total_frames = None
        self._total_seconds = None
        self._dropped_frames = None
        self._frame = value
    @classmethod
    def parse(cls, s, frame_rate, drop_frame=False):
        if ';' in s:
            drop_frame = True
            s = ':'.join(s.split(';'))
        h, m, s, f = [int(v) for v in s.split(':')]
        return cls(h, m, s, f, frame_rate, drop_frame)
    @classmethod
    def from_frames(cls, total_frames, frame_rate, drop_frame=False):
        tseconds = int(total_frames // frame_rate)
        if drop_frame:
            oth = cls(0, 0, 0, 0, frame_rate=frame_rate, drop_frame=drop_frame)
            dropped = oth._calc_dropped_frames(total_seconds=tseconds)
        else:
            dropped = 0
        frame = int(total_frames % frame_rate) + dropped
        h = int(tseconds // 3600)
        m = int(tseconds % 3600 // 60)
        s = int(tseconds % 3600 % 60)
        return cls(h, m, s, frame, frame_rate=frame_rate, drop_frame=drop_frame)
    @property
    def total_frames(self):
        if self._total_frames is not None:
            return self._total_frames
        s = self.hour * 3600
        s += self.minute * 60
        s += self.second
        frames = float(s * self.frame_rate)
        if self.frame_rate.denom == 1001 and round((frames % self.frame_rate), 10) == 0:
            frames = math.ceil(frames)
        frames = int(frames)
        dropped = self.dropped_frames
        frames += self.frame
        frames -= dropped
        self._total_frames = frames
        return frames
    @total_frames.setter
    def total_frames(self, total_frames):
        current_total = self.total_frames
        if current_total == total_frames:
            return
        tc = self.from_frames(total_frames, self.frame_rate, self.drop_frame)
        self.hour = tc.hour
        self.minute = tc.minute
        self.second = tc.second
        self.frame = tc.frame
    @property
    def total_seconds(self):
        if self._total_seconds is not None:
            return self._total_seconds
        frames = self.total_frames
        s = float(frames / self.frame_rate)
        self._total_seconds = s
        return s
    @total_seconds.setter
    def total_seconds(self, total_seconds):
        current_total = self.total_seconds
        if current_total == total_seconds:
            return
        self.total_frames = float(total_seconds * self.frame_rate)
    @property
    def timedelta(self):
        return datetime.timedelta(seconds=self.total_seconds)
    @property
    def dropped_frames(self):
        dropped = self._dropped_frames
        if dropped is None:
            dropped = self._dropped_frames = self._calc_dropped_frames()
        return dropped
    def to_list(self):
        return [self.hour, self.minute, self.second, self.frame]
    def _calc_dropped_frames(self, total_seconds=None, other=None):
        if not self.drop_frame:
            return 0
        if other is not None:
            if not self._same_format(other):
                raise Exception()
            total_seconds = other.total_seconds
        elif total_seconds is None:
            total_seconds = self.hour * 3600
            total_seconds += self.minute * 60
            total_seconds += self.second

        hours = total_seconds // 3600
        total_seconds -= hours * 3600
        minutes = total_seconds // 60

        dropped = (hours * 108) + ((minutes // 10) * 18) + (minutes % 10 * 2)
        if self.frame_rate == FrameRate(60000, 1001):
            dropped *= 2
        return dropped
    def _same_format(self, other):
        if other.frame_rate != self.frame_rate:
            return False
        if other.drop_frame != self.drop_frame:
            return False
        return True
    def __add__(self, other):
        if not isinstance(other, Timecode):
            return NotImplemented
        if not self._same_format(other):
            raise Exception()
        frames = self.total_frames + other.total_frames
        return Timecode.from_frames(frames, self.frame_rate, self.drop_frame)
    def __sub__(self, other):
        if not isinstance(other, Timecode):
            return NotImplemented
        if not self._same_format(other):
            raise Exception()
        frames = self.total_frames - other.total_frames
        return Timecode.from_frames(frames, self.frame_rate, self.drop_frame)
    def __iadd__(self, other):
        if isinstance(other, Timecode):
            if not self._same_format(other):
                raise Exception()
            total_frames = other.total_frames
            if other < self:
                total_frames *= -1
            self.total_frames += other.total_frames
            return self
        elif isinstance(other, datetime.timedelta):
            self.total_seconds += other.total_seconds()
            return self
        return NotImplemented
    def __isub__(self, other):
        if isinstance(other, Timecode):
            if not self._same_format(other):
                raise Exception()
            total_frames = other.total_frames
            if other < self:
                total_frames *= -1
            self.total_frames -= other.total_frames
            return self
        elif isinstance(other, datetime.timedelta):
            self.total_seconds -= other.total_seconds()
            return self
        return NotImplemented
    def __eq__(self, other):
        if not isinstance(other, Timecode):
            return NotImplemented
        if not self._same_format(other):
            return False
        for attr in ['hour', 'minute', 'second', 'frame']:
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True
    def __ne__(self, other):
        if not isinstance(other, Timecode):
            return NotImplemented
        return not self.__eq__(other)
    def __gt__(self, other):
        if isinstance(other, datetime.timedelta):
            total_seconds = other.total_seconds()
        elif isinstance(other, Timecode):
            total_seconds = other.total_seconds
        else:
            return NotImplemented
        return self.total_seconds > total_seconds
    def __lt__(self, other):
        if isinstance(other, datetime.timedelta):
            total_seconds = other.total_seconds()
        elif isinstance(other, Timecode):
            total_seconds = other.total_seconds
        else:
            return NotImplemented
        return self.total_seconds < total_seconds
    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        fmt = ':'.join(['{:02}'] * 3)
        if self.drop_frame:
            fmt = ';'.join([fmt, '{:02}'])
        else:
            fmt = ':'.join([fmt, '{:02}'])
        return fmt.format(*self.to_list())
