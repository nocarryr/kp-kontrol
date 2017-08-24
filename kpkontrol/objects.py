import datetime

from pydispatch.properties import Property, DictProperty

from kpkontrol.base import ObjectBase
from kpkontrol.parameters import EnumParameter, ParameterEnumItem
from kpkontrol.timecode import FrameRate, FrameFormat, Timecode

class DeviceParameter(ObjectBase):
    value = Property()
    __attribute_names = [
        'device', 'parameter', 'value',
    ]
    @classmethod
    def create(cls, **kwargs):
        param = kwargs.get('parameter')
        _cls = cls
        if isinstance(param, EnumParameter):
            _cls = DeviceEnumParameter
        return _cls(**kwargs)
    @property
    def name(self):
        return self.parameter.name
    @property
    def id(self):
        return self.parameter.id
    def set_value(self, value):
        self.device.set_parameter(self.parameter, value)
    def get_value(self):
        self.value = self.device.get_parameter(self.parameter)
    def __repr__(self):
        return '<{self.__class__.__name__} {self.parameter}: {self.value}>'.format(self=self)
    def __str__(self):
        return self.name

class DeviceEnumParameter(DeviceParameter):
    enum_items = DictProperty()
    def __init__(self, **kwargs):
        super(DeviceEnumParameter, self).__init__(**kwargs)
        for param_item in self.parameter.enum_items.values():
            device_item = DeviceEnumItem(
                device_parameter=self,
                parameter_item=param_item,
            )
            self.enum_items[device_item.name] = device_item
    def set_value(self, value):
        key = self.parameter.format_value(value)
        param = self.enum_items[key]
        self.device.set_parameter(self.parameter, param.value)
    def get_value(self):
        value = self.device.get_parameter(self.parameter)
        if value is None:
            return
        self.value = self.enum_items[value.name]

class DeviceEnumItem(ObjectBase):
    active = Property(False)
    def __init__(self, **kwargs):
        self.device_parameter = kwargs.get('device_parameter')
        self.parameter_item = kwargs.get('parameter_item')
        self.device_parameter.bind(value=self.on_device_parameter_value)
    @property
    def name(self):
        return self.parameter_item.name
    @property
    def description(self):
        return self.parameter_item.description
    @property
    def value(self):
        return self.parameter_item.value
    def set_active(self):
        self.device_parameter.set_value(self.name)
    def on_device_parameter_value(self, instance, value, **kwargs):
        self.active = value is self
    def __repr__(self):
        return '<{self.__class__.__name__} {self.parameter_item}: active={self.active}'.format(self=self)
    def __str__(self):
        return self.name


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
