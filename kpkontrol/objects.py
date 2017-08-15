import datetime

from kpkontrol.timecode import FrameRate, Timecode

class ObjectBase(object):
    pass

class ClipFormat(ObjectBase):
    def __init__(self, **kwargs):
        self.width = kwargs.get('width')
        self.height = kwargs.get('height')
        self.frame_rate = kwargs.get('frame_rate')
        self.interlaced = kwargs.get('interlaced')
        self.fourcc = kwargs.get('fourcc')
    @classmethod
    def from_json(cls, data):
        kwargs = dict(
            width=int(data['width']),
            height=int(data['height']),
            fourcc=data['fourcc'],
        )
        fr = data['framerate']
        if fr == '29.97':
            fr = FrameRate(30000, 1001)
        elif fr == '59.94':
            fr = FrameRate(60000, 1001)
        else:
            fr = FrameRate(int(fr), 1)
        kwargs['frame_rate'] = fr
        kwargs['interlaced'] = data['interlace'] == '1'
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
    def __init__(self, **kwargs):
        self.name = kwargs.get('name')
        self.duration_tc = kwargs.get('duration_tc')
        self.duration_timedelta = kwargs.get('duration_timedelta')
        self.total_frames = kwargs.get('total_frames')
        self.timestamp = kwargs.get('timestamp')
        self.format = kwargs.get('format')
        self.audio_channels = kwargs.get('audio_channels')
        self.start_timecode = kwargs.get('start_timecode')
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
