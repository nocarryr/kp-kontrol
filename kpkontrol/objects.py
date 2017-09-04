import datetime
import ipaddress
from urllib.parse import urlparse
import json

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
        elif param.id == 'eParamID_NetworkServices':
            _cls = NetworkServicesParameter
        return _cls(**kwargs)
    @property
    def name(self):
        return self.parameter.name
    @property
    def id(self):
        return self.parameter.id
    async def set_value(self, value):
        response = await self.device.set_parameter(self.parameter, value)
        if response == value:
            self.value = value
        return response
    async def get_value(self):
        self.value = await self.device.get_parameter(self.parameter)
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
    async def set_value(self, value):
        key = self.parameter.format_value(value)
        param = self.enum_items[key]
        response = await self.device.set_parameter(self.parameter, param.value)
        if isinstance(response, ParameterEnumItem):
            self.value = self.enum_items[response.name]
        return response
    async def get_value(self):
        value = await self.device.get_parameter(self.parameter)
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
    async def set_active(self):
        await self.device_parameter.set_value(self.name)
    def on_device_parameter_value(self, instance, value, **kwargs):
        self.active = value is self
    def __repr__(self):
        return '<{self.__class__.__name__} {self.parameter_item}: active={self.active}'.format(self=self)
    def __str__(self):
        return self.name

class NetworkServicesParameter(DeviceParameter):
    devices = DictProperty()
    _events_ = ['on_device_added', 'on_device_removed']
    def __init__(self, **kwargs):
        self.bind(value=self.on_value)
        super(NetworkServicesParameter, self).__init__(**kwargs)
    def on_value(self, instance, value, **kwargs):
        if not isinstance(value, list):
            value = json.loads(value)
        keys = set()
        for data in value:
            d = self.add_device_obj(**data)
            keys.add(d.id)
        to_remove = set(self.devices.keys()) - keys
        for key in to_remove:
            d = self.devices[key]
            d.unbind(self)
            del self.devices[key]
            self.emit('on_device_removed', d, parameter=self)
    def add_device_obj(self, **data):
        data.setdefault('device_parameter', self)
        d = NetworkDevice(**data)
        if d.id in self.devices:
            return d
        self.devices[d.id] = d
        d.bind(ip_address=self.on_device_ip_address)
        self.emit('on_device_added', d, parameter=self)
        return d
    def on_device_ip_address(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old and old in self.devices:
            del self.devices[old]
        self.devices[value] = instance
    def __repr__(self):
        return '<{self.__class__.__name__} {self.parameter}: {self.devices}>'.format(self=self)
    def __str__(self):
        return self.name

class NetworkDevice(ObjectBase):
    device_name = Property()
    host_name = Property()
    description = Property()
    ip_address = Property()
    port = Property()
    service_type = Property()
    service_domain = Property()
    __attribute_names = [
        'device_name', 'host_name', 'description', 'ip_address', 'port',
        'service_type', 'service_domain', 'device_parameter',
    ]
    def __init__(self, **kwargs):
        kwargs['port'] = int(kwargs.get('port', 80))
        super(NetworkDevice, self).__init__(**kwargs)
    @property
    def id(self):
        return self.ip_address
    @property
    def host_address(self):
        return ':'.join([str(self.ip_address), str(self.port)])
    @property
    def service_uri(self):
        return '.'.join([self.host_name, self.service_type, self.service_domain])
    @property
    def is_host_device(self):
        param = self.device_parameter.device.all_parameters['eParamID_IPAddress_3']
        return ipaddress.ip_address(self.ip_address) == param.value
    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        return '{self.host_name} ({self.ip_address})'.format(self=self)


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
    def get_url(self, host_address):
        return '/'.join([host_address.rstrip('/'), 'media', self.name])
    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        return self.name
