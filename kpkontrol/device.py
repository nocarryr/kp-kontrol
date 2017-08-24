from pydispatch.properties import (
    Property, DictProperty, ListProperty
)

from kpkontrol.base import ObjectBase
from kpkontrol import actions
from kpkontrol.parameters import ParameterBase
from kpkontrol.objects import DeviceParameter, Clip
from kpkontrol.timecode import FrameRate, Timecode

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
        self.transport = KpTransport(device=self)
        self.connect()
    @property
    def listen_action(self):
        a = getattr(self, '_listen_action', None)
        if a is None:
            all_parameters = {'by_id':self.all_parameters}
            a = self._listen_action = actions.ListenForEvents(self.host_address, all_parameters=all_parameters)
        return a
    def connect(self):
        self._get_all_parameters()
        self.update_clips()
        self.connected = True
    def update_clips(self):
        a = actions.GetClips(self.host_address)
        clips = a()
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
        current = self.get_parameter('eParamID_CurrentClip')
        if current in self.clips:
            self.transport.clip = self.clips[current]
    def listen_for_events(self):
        self._get_all_parameters()
        a = self.listen_action
        events = a()
        print(events)
        self.emit('on_events_received', self, events)
        for param_id, data in events.items():
            device_param = self.all_parameters[param_id]
            device_param.value = data['value']
    def _get_all_parameters(self):
        if self.parameters_received:
            return
        a = actions.GetAllParameters(self.host_address)
        params = a()
        for param_id, param in params['by_id'].items():
            if param_id in self.all_parameters:
                continue
            device_param = DeviceParameter.create(device=self, parameter=param)
            self.all_parameters[param_id] = device_param
            device_param.bind(value=self._on_device_parameter_value)
        self.parameters_received = True
        self.get_all_parameter_values()
    def get_all_parameter_values(self):
        for device_param in self.all_parameters.values():
            if device_param.parameter.param_type == 'data':
                continue
            if device_param.id == 'eParamID_MACAddress':
                continue
            device_param.get_value()
    def _on_device_parameter_value(self, instance, value, **kwargs):
        if instance.id == 'eParamID_SysName':
            self.name = value
        elif instance.id == 'eParamID_FormattedSerialNumber':
            self.serial_number = value
        self.emit('on_parameter_value', instance, value, **kwargs)
    def _get_parameter_object(self, parameter):
        self._get_all_parameters()
        if isinstance(parameter, (ParameterBase, DeviceParameter)):
            return self.all_parameters[parameter.id]
        return self.all_parameters[parameter]
    def get_parameter(self, parameter):
        parameter = self._get_parameter_object(parameter).parameter
        a = actions.GetParameter(self.host_address, parameter=parameter)
        return a()
    def set_parameter(self, parameter, value):
        parameter = self._get_parameter_object(parameter).parameter
        a = actions.SetParameter(self.host_address, parameter=parameter, value=value)
        return a()

class KpTransport(ObjectBase):
    active = Property(False)
    playing = Property(False)
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
    def set_transport(self, value):
        p = self.transport_param_set
        if p is None:
            return
        p.set_value(value)
        self.transport_param_get.get_value()
    def go_to_clip(self, clip):
        if not isinstance(clip, Clip):
            clip = self.device.clips[clip]
        param = self.device.all_parameters['eParamID_GoToClip']
        param.set_value(clip.name)
        self.clip = clip
    def play(self):
        self.set_transport('Play Command')
    def record(self):
        self.set_transport('Record Command')
    def stop(self):
        self.set_transport('Stop Command')
    def shuttle_forward(self):
        self.set_transport('Fast Forward')
    def shuttle_reverse(self):
        self.set_transport('Fast Reverse')
    def step_forward(self, nframes=1):
        while nframes > 0:
            self.set_transport('Single Step Forward')
            nframes -= 1
    def step_reverse(self, nframes=1):
        while nframes > 0:
            self.set_transport('Single Step Reverse')
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
        elif instance.id == self.timecode_param:
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
