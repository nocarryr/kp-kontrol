import asyncio
import datetime
import numbers

from pydispatch import Property
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
    total_frames = Property(0)
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
    def incr(self):
        old = self.total_frames
        super(Timecode, self).incr()
        self.emit('on_change', self, self.total_frames, obj=self, old=old)
    def decr(self):
        old = self.total_frames
        super(Timecode, self).decr()
        self.emit('on_change', self, self.total_frames, obj=self, old=old)
    def set_total_frames(self, total_frames):
        old = self.total_frames
        super(Timecode, self).set_total_frames(total_frames)
        if self.total_frames != old:
            self.emit('on_change', self, self.total_frames, obj=self, old=old)
    def set(self, **kwargs):
        old = self.total_frames
        super(Timecode, self).set(**kwargs)
        if self.total_frames != old:
            self.emit('on_change', self, self.total_frames, obj=self, old=old)
    def set_from_string(self, tc_str):
        if self.frame_format.drop_frame:
            tc_str = ':'.join(tc_str.split(';'))
        hmsf = [int(v) for v in tc_str.split(':')]
        keys = ['hours', 'minutes', 'seconds', 'frames']
        self.set(**{k:v for k, v in zip(keys, hmsf)})
    async def start_freerun(self):
        await self.stop_freerun()
        loop = self.loop = asyncio.get_event_loop()
        self._freerunning = asyncio.Event()
        self._freerun_stopped = asyncio.Event()
        self.freerun_offset = 0.
        self.freerun_lock = asyncio.Lock()
        self.freerun_nframes = 0
        self.freerun_start_ts = self.freerun_tick_ts = loop.time()
        self.freerun_fut = asyncio.ensure_future(self.freerun())
    async def freerun(self):
        loop = self.loop
        fr = self.frame_format.rate
        timeout = 1. / fr
        self._freerunning.set()
        while self._freerunning.is_set():
            async with self.freerun_lock:
                self.incr()
                self.freerun_nframes += 1
                now = self.freerun_tick_ts = loop.time()
                frame_time = (self.freerun_nframes-1) / fr
                elapsed = now - self.freerun_start_ts
                offset = elapsed - frame_time
                self.freerun_offset = offset * fr
            next_timeout = timeout - offset
            if next_timeout < 0:
                next_timeout = 0
            await asyncio.sleep(next_timeout)
        self._freerun_stopped.set()
    async def set_async(self, **kwargs):
        if hasattr(self, 'freerun_lock'):
            async with self.freerun_lock:
                prev_frames = self.total_frames
                self.set(**kwargs)
                if prev_frames < self.total_frames:
                    diff = prev_frames - self.total_frames
                    self.freerun_nframes += diff
                    self.freerun_start_ts -= float(diff / self.frame_format.rate)
                elif prev_frames > self.total_frames:
                    diff = self.total_frames - prev_frames
                    self.freerun_nframes -= diff
                    self.freerun_start_ts += float(diff / self.frame_format.rate)
        else:
            self.set(**kwargs)
    async def set_from_string_async(self, tc_str):
        if hasattr(self, 'freerun_lock'):
            async with self.freerun_lock:
                self.freerun_start_ts = self.loop.time()
                self.freerun_nframes = 0
                self.set_from_string(tc_str)
        else:
            self.set_from_string(tc_str)
    async def stop_freerun(self):
        freerunning = getattr(self, '_freerunning', None)
        stop_event = getattr(self, '_freerun_stopped', None)
        if freerunning is None:
            return
        freerunning.clear()
        if stop_event is not None:
            await stop_event.wait()
        await self.freerun_fut
        self._freerunning = None
        self._freerun_stopped = None
