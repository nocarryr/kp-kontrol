import asyncio

from pydispatch.properties import (
    Property, DictProperty, ListProperty
)

from kpkontrol.base import ObjectBase
from kpkontrol import actions
from kpkontrol.parameters import ParameterBase
from kpkontrol.objects import DeviceParameter, Clip
from kpkontrol.timecode import FrameRate, FrameFormat, Timecode

class KpDevice(ObjectBase):
    name = Property()
    serial_number = Property()
    clips = DictProperty()
    input_format = Property()
    input_timecode = Property()
    connected = Property(False)
    parameters_received = Property(False)
    __attribute_names = [
        'host_address', 'name', 'serial_number',
        'transport', 'clips',
    ]
    __attribute_defaults = {
        'clips':{}
    }
    _events_ = ['on_events_received', 'on_parameter_value']
    def __init__(self, **kwargs):
        super(KpDevice, self).__init__(**kwargs)
        self.all_parameters = {}
        self.loop = kwargs.get('loop')
        self.session = kwargs.get('session')
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        self.transport = KpTransport(device=self)
    @classmethod
    async def create(cls, **kwargs):
        obj = cls(**kwargs)
        await obj.connect()
    @property
    def session(self):
        return getattr(self, '_session', None)
    @session.setter
    def session(self, value):
        if value == self.session:
            return
        self._session = value
        if value is not None:
            self.loop = value._loop
    @property
    def listen_action(self):
        a = getattr(self, '_listen_action', None)
        if a is None:
            all_parameters = {'by_id':self.all_parameters}
            a = self._listen_action = actions.ListenForEvents(
                self.host_address,
                all_parameters=all_parameters,
                session=self.session,
                loop=self.loop,
            )
        return a
    async def connect(self):
        await self._get_all_parameters()
        await self.update_clips()
        self.connected = True
        self._update_loop_fut = asyncio.ensure_future(self._update_loop())
    async def stop(self):
        if not self.connected:
            return
        self.connected = False
        fut = getattr(self, '_update_loop_fut', None)
        if fut is not None:
            await fut
        if self.session is not None:
            self.session.close()
            self.session = None
    async def _update_loop(self):
        while self.connected:
            await self.listen_for_events()
            await self.update_clips()
            await asyncio.sleep(.1)
    async def _do_action(self, action_cls, **kwargs):
        kwargs.setdefault('session', self.session)
        kwargs.setdefault('loop', self.loop)
        a = action_cls(self.host_address, **kwargs)
        response = await a()
        if self.session is None:
            self.session = a.session
        return response
    async def update_clips(self):
        clips = await self._do_action(actions.GetClips)
        for clip in clips:
            if clip.name not in self.clips:
                self.clips[clip.name] = clip
            else:
                for attr in clip.attribute_names_:
                    if attr == 'name':
                        continue
                    if attr == 'format':
                        if str(clip.format) != str(self.clips[clip.name].format):
                            self.clips[clip.name] = clip
                        continue
                    val = getattr(clip, attr)
                    if getattr(self.clips[clip.name], attr) == val:
                        continue
                    setattr(self.clips[clip.name], attr, val)
        current = await self.get_parameter('eParamID_CurrentClip')
        if current in self.clips:
            self.transport.clip = self.clips[current]
    async def listen_for_events(self):
        await self._get_all_parameters()
        a = self.listen_action
        events = await a()
        print(events)
        self.emit('on_events_received', self, events)
        for param_id, data in events.items():
            device_param = self.all_parameters[param_id]
            device_param.value = data['value']
    async def _get_all_parameters(self):
        if self.parameters_received:
            return
        params = await self._do_action(actions.GetAllParameters)
        for param_id, param in params['by_id'].items():
            if param_id in self.all_parameters:
                continue
            device_param = DeviceParameter.create(device=self, parameter=param)
            self.all_parameters[param_id] = device_param
            device_param.bind(value=self._on_device_parameter_value)
        self.parameters_received = True
        await self.get_all_parameter_values()
    async def get_all_parameter_values(self):
        for device_param in self.all_parameters.values():
            if device_param.parameter.param_type == 'data':
                continue
            if device_param.id == 'eParamID_MACAddress':
                continue
            await device_param.get_value()
    def _on_device_parameter_value(self, instance, value, **kwargs):
        if instance.id == 'eParamID_SysName':
            self.name = value
        elif instance.id == 'eParamID_FormattedSerialNumber':
            self.serial_number = value
        self.emit('on_parameter_value', instance, value, **kwargs)
    async def _get_parameter_object(self, parameter):
        await self._get_all_parameters()
        if isinstance(parameter, (ParameterBase, DeviceParameter)):
            return self.all_parameters[parameter.id]
        return self.all_parameters[parameter]
    async def get_parameter(self, parameter):
        parameter = await self._get_parameter_object(parameter)
        return await self._do_action(
            actions.GetParameter,
            parameter=parameter.parameter,
        )
    async def set_parameter(self, parameter, value):
        parameter = await self._get_parameter_object(parameter)
        return await self._do_action(
            actions.SetParameter,
            parameter=parameter.parameter,
            value=value,
        )

class KpTransport(ObjectBase):
    active = Property(False)
    playing = Property(False)
    recording = Property(False)
    paused = Property(False)
    shuttle = Property(False)
    clip = Property()
    __attribute_names = [
        'active', 'playing', 'recording', 'paused', 'shuttle',
        'timecode', 'clip', 'device',
    ]
    __attribute_defaults = {
        'active':False,
        'playing':False,
        'recording':False,
        'paused':False,
        'shuttle':False,
    }
    # _timecode_param = 'eParamID_DisplayTimecode'
    # _transport_param_get = 'eParamID_TransportState'
    # _transport_param_set = 'eParamID_TransportCommand'
    def __init__(self, **kwargs):
        self.bind(clip=self.on_clip, active=self.on_active)
        super(KpTransport, self).__init__(**kwargs)
        self.device.bind(on_parameter_value=self.on_parameter_value)
    @property
    def loop(self):
        return self.device.loop
    @property
    def timecode_param(self):
        p = getattr(self, '_timecode_param', None)
        if p is None:
            all_params = self.device.all_parameters
            p = self._timecode_param = all_params.get('eParamID_DisplayTimecode')
            p.bind(value=self.process_timecode_response)
        return p
    @property
    def transport_param_get(self):
        p = getattr(self, '_transport_param_get', None)
        if p is None:
            all_params = self.device.all_parameters
            p = self._transport_param_get = all_params.get('eParamID_TransportState')
        return p
    @property
    def transport_param_set(self):
        p = getattr(self, '_transport_param_set', None)
        if p is None:
            all_params = self.device.all_parameters
            p = self._transport_param_set = all_params.get('eParamID_TransportCommand')
        return p
    async def set_transport_async(self, value):
        p = self.transport_param_set
        if p is None:
            return
        await p.set_value(value)
        await self.transport_param_get.get_value()
    def set_transport(self, value):
        return asyncio.ensure_future(self.set_transport_async(value), loop=self.loop)
    async def go_to_clip(self, clip):
        if not isinstance(clip, Clip):
            clip = self.device.clips[clip]
        param = self.device.all_parameters['eParamID_GoToClip']
        await param.set_value(clip.name)
        self.clip = clip
    async def play(self):
        await self.set_transport_async('Play Command')
    async def record(self):
        await self.set_transport_async('Record Command')
    async def stop(self):
        await self.set_transport_async('Stop Command')
    async def shuttle_forward(self):
        await self.set_transport_async('Fast Forward')
    async def shuttle_reverse(self):
        await self.set_transport_async('Fast Reverse')
    async def step_forward(self, nframes=1):
        while nframes > 0:
            await self.set_transport_async('Single Step Forward')
            nframes -= 1
    async def step_reverse(self, nframes=1):
        while nframes > 0:
            await self.set_transport_async('Single Step Reverse')
            nframes -= 1
    def on_clip(self, instance, clip, **kwargs):
        if clip is None:
            self.timecode = None
        self.timecode = clip.start_timecode.copy()
    def on_active(self, *args, **kwargs):
        pass
    def on_parameter_value(self, instance, value, **kwargs):
        param = self.transport_param_get
        if param is not None and param.id == instance.id:
            self.process_transport_response(instance, value, **kwargs)
        elif instance.id == self.timecode_param.id:
            self.process_timecode_response(instance, value, **kwargs)
        elif instance.id == 'eParamID_CurrentClip':
            if value in self.device.clips:
                self.clip = self.device.clips[value]
    def process_timecode_response(self, instance, value, **kwargs):
        if self.timecode is None:
            return
        self.timecode.set_from_string(value)
    def process_transport_response(self, instance, value, **kwargs):
        s = str(value).lower()
        self.playing = 'playing' in s
        self.recording = s == 'recording'
        if s.startswith('forward') or s.startswith('reverse'):
            self.paused = s.endswith('step')
            self.shuttle = s.endswith('x')
        else:
            self.paused = s == 'paused'
            self.shuttle = False
        self.active = self.playing or self.recording or self.paused or self.shuttle
