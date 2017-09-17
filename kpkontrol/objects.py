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
        d.bind(device_id=self.on_device_id)
        self.emit('on_device_added', d, parameter=self)
        return d
    def on_device_id(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old and old in self.devices:
            del self.devices[old]
        self.devices[value] = instance
    def __repr__(self):
        return '<{self.__class__.__name__} {self.parameter}: {self.devices}>'.format(self=self)
    def __str__(self):
        return self.name

class NetworkDevice(ObjectBase):
    device_id = Property()
    device_name = Property()
    host_name = Property()
    description = Property()
    ip_address = Property()
    port = Property()
    service_type = Property()
    service_domain = Property()
    gang_enabled = Property(False)
    gang_master = Property(False)
    gang_members = DictProperty()
    __attribute_names = [
        'device_name', 'host_name', 'description', 'ip_address', 'port',
        'service_type', 'service_domain', 'device_parameter',
    ]
    def __init__(self, **kwargs):
        kwargs['port'] = int(kwargs.get('port', 80))
        self.bind(
            ip_address=self._on_ip_prop,
            port=self._on_ip_prop,
        )
        super(NetworkDevice, self).__init__(**kwargs)
        self._check_gang_params()
        self.device.bind(
            on_parameter_value=self.on_device_parameter_value,
            network_devices=self.on_device_network_devices,
        )
    @property
    def id(self):
        return self.device_id
    @property
    def host_address(self):
        return ':'.join([str(self.ip_address), str(self.port)])
    @property
    def service_uri(self):
        return '.'.join([self.host_name, self.service_type, self.service_domain])
    @property
    def is_host_device(self):
        param = self.device.all_parameters['eParamID_IPAddress_3']
        if ipaddress.ip_address(self.ip_address) != param.value:
            return False
        param = self.device.all_parameters['eParamID_SysName']
        if self.host_name != param.value:
            return False
        return True
    @property
    def device(self):
        return self.device_parameter.device
    def _on_ip_prop(self, *args, **kwargs):
        self.device_id = '{self.ip_address}:{self.port}'.format(self=self)
    def _check_gang_params(self, *args, **kwargs):
        all_params = self.device.all_parameters
        if self.is_host_device:
            self.gang_enabled = str(all_params['eParamID_GangEnable'].value) == 'ON'
            self.gang_master = str(all_params['eParamID_GangMaster'].value) == 'ON'
            addrs = all_params['eParamID_GangList'].value.split(',')
            for addr in addrs:
                if addr in self.gang_members:
                    continue
                d = self.device.network_devices.get(addr)
                if d is not None:
                    self.gang_members[addr] = d
            to_remove = set(self.gang_members.keys()) - set(addrs)
            for addr in to_remove:
                del self.gang_members[addr]
        else:
            self.gang_enabled = self.ip_address in all_params['eParamID_GangList'].value
    def on_device_parameter_value(self, instance, value, **kwargs):
        if 'Gang' not in instance.id:
            return
        self._check_gang_params()
    def on_device_network_devices(self, instance, value, **kwargs):
        self._check_gang_params()
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

class MetaClip(ObjectBase):
    name = Property()
    start_timecode = Property()
    end_timecode = Property()
    duration_tc = Property()
    total_frames = Property()
    __attribute_names = [
        'name', 'device', 'source_clip', 'source_clip_name',
        'start_timecode', 'end_timecode',
    ]
    def __init__(self, **kwargs):
        source_clip = kwargs.get('source_clip')
        if source_clip is None:
            device = kwargs.get('device')
            source_clip_name = kwargs.get('source_clip_name')
            if source_clip_name is not None and hasattr(device, 'clips'):
                source_clip = device.clips.get(source_clip_name)
                kwargs.setdefault('source_clip', source_clip)
            elif hasattr(device, 'transport'):
                source_clip = device.transport.clip
                kwargs.setdefault('source_clip', source_clip)
        if source_clip is not None:
            kwargs.setdefault('source_clip_name', source_clip.name)
            kwargs.setdefault('name', source_clip.name)

        self.bind(
            start_timecode=self._on_tc_range,
            end_timecode=self._on_tc_range,
        )

        super().__init__(**kwargs)

        if self.source_clip is not None:
            self._init_timecode_objs()
        else:
            self.device.bind(clips=self.on_device_clips)

    @classmethod
    async def create_from_current(cls, **kwargs):
        device = kwargs.get('device')
        transport = device.transport
        async with transport.timecode.freerun_lock:
            start_tc = transport.timecode.copy()
        kwargs.setdefault('start_timecode', start_tc)
        kwargs['source_clip'] = transport.clip
        return cls(**kwargs)

    def _init_timecode_objs(self):
        if self.start_timecode is None:
            self.start_timecode = self.source_clip.start_timecode.copy()
        else:
            self.start_timecode = self._create_timecode(self.start_timecode)
        if self.end_timecode is None:
            self.end_timecode = self.source_clip.start_timecode + self.source_clip.total_frames
        else:
            self.end_timecode = self._create_timecode(self.end_timecode)

    def on_device_clips(self, device, clips, **kwargs):
        if self.source_clip is not None:
            return
        clip = clips.get(self.source_clip_name)
        if clip is None:
            return
        self.device.unbind(self.on_device_clips)
        self.source_clip = clip
        self._init_timecode_objs()

    def _on_tc_range(self, instance, tc, **kwargs):
        start_tc = self.start_timecode
        end_tc = self.end_timecode
        if not isinstance(start_tc, Timecode) or not isinstance(end_tc, Timecode):
            return
        self.duration_tc = end_tc - start_tc
        self.total_frames = self.duration_tc.total_frames

    def _create_timecode(self, tc):
        fmt = self.source_clip.start_timecode.frame_format
        if isinstance(tc, str):
            tc = Timecode.parse(tc, frame_rate=fmt.rate)
        elif isinstance(tc, int):
            tc = Timecode.from_frames(tc, frame_format=fmt)
        return tc

    async def set_cue_in(self, tc=None):
        if tc is None:
            transport = self.device.transport
            async with transport.timecode.freerun_lock:
                tc = transport.timecode.copy()
        else:
            tc = self._create_timecode(tc)
        if tc > self.end_timecode:
            return
        self.start_timecode = tc

    async def set_cue_out(self, tc=None):
        if tc is None:
            transport = self.device.transport
            async with transport.timecode.freerun_lock:
                tc = transport.timecode.copy()
        else:
            tc = self._create_timecode(tc)
        if tc < self.start_timecode:
            return
        self.end_timecode = tc

    async def play(self):
        self.remaining = self.end_timecode - self.start_timecode
        transport = self.device.transport
        if transport.active:
            await transport.pause()
        if transport.clip is not self.source_clip:
            await transport.go_to_clip(self.source_clip)
        await transport.go_to_timecode(self.start_timecode)
        await transport.play()
        while True:
            if transport.clip is not self.source_clip:
                break
            if not transport.active:
                break
            async with transport.freerun_lock:
                tc = transport.timecode.copy()
            if tc >= self.end_timecode:
                await self.transport.pause()
                break
            self.remaining = self.end_timecode - tc
            if self.remaining.total_seconds <= 1:
                timeout = tc.frame_format.rate.float_value
            else:
                timeout = .5
            await asyncio.sleep(timeout)

    def _serialize(self):
        d = {k:getattr(self, k) for k in ['name', 'source_clip_name']}
        d.update({
            'start_timecode':str(self.start_timecode),
            'end_timecode':str(self.end_timecode),
        })
        return d

    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        return self.name
