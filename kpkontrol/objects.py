import datetime


from kpkontrol.base import ObjectBase
from kpkontrol.timecode import FrameRate, FrameFormat, Timecode


class ClipFormat(ObjectBase):
    __attribute_names = [
        'width', 'height', 'frame_rate', 'interlaced', 'fourcc',
    ]
    @classmethod
    def from_json(cls, data):
        kwargs = dict(
            width=int(data['width']),
            height=int(data['height']),
            fourcc=data['fourcc'],
        )
        kwargs['frame_rate'] = FrameRate.from_float(data['framerate'])
        kwargs['interlaced'] = data['interlace'] == '1'
        return cls(**kwargs)
    @classmethod
    def from_string(cls, s):
        kwargs = {}
        w, s = s.split('x')
        kwargs['width'] = int(w)
        h, fr = s.strip(' ').split(' ')
        if h.endswith('i'):
            kwargs['interlaced'] = True
            kwargs['height'] = int(h.rstrip('i'))
        elif h.endswith('p'):
            kwargs['interlaced'] = False
            kwargs['height'] = int(h.rstrip('p'))
        elif h.endswith('PsF'):
            kwargs['interlaced'] = False
            kwargs['height'] = int(h.rstrip('PsF'))
        kwargs['frame_rate'] = FrameRate.from_float(fr)
        return cls(**kwargs)
    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        if self.interlaced:
            fielding = 'i'
        else:
            fielding = 'p'
        return '{self.width}x{self.height}{fielding}{self.frame_rate.float_value:05.2f}'.format(
            self=self, fielding=fielding
        )

class Clip(ObjectBase):
    timestamp_fmt = '%m/%d/%y %H:%M:%S'
    __attribute_names = [
        'name', 'duration_tc', 'duration_timedelta', 'total_frames',
        'timestamp', 'format', 'audio_channels', 'start_timecode',
    ]
    @classmethod
    def from_json(cls, data):
        kwargs = dict(
            name=data['clipname'],
            total_frames=int(data['framecount']),
            timestamp=datetime.datetime.strptime(data['timestamp'], cls.timestamp_fmt),
            audio_channels=int(data['attributes']['Audio Chan']),
        )
        fmt = kwargs['format'] = ClipFormat.from_json(data)
        tc = kwargs['start_timecode'] = Timecode.parse(
            data['attributes']['Starting TC'],
            frame_rate=fmt.frame_rate,
        )
        kwargs['duration_tc'] = Timecode.parse(
            data['duration'],
            frame_rate=fmt.frame_rate,
            drop_frame=False,
        )
        kwargs['duration_timedelta'] = kwargs['duration_tc'].timedelta
        return cls(**kwargs)
    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        return self.name
