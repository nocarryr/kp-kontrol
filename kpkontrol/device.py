import asyncio

from pydispatch.properties import (
    Property, DictProperty, ListProperty
)

from kpkontrol.base import ObjectBase
from kpkontrol import actions
from kpkontrol.parameters import ParameterBase
from kpkontrol.objects import (
    DeviceParameter,
    NetworkServicesParameter,
    NetworkDevice,
    Clip,
    MetaClip,
)
from kpkontrol.timecode import FrameRate, FrameFormat, Timecode

class KpDevice(ObjectBase):
    name = Property()
    serial_number = Property()
    clips = DictProperty()
    meta_clips = DictProperty()
    input_format = Property()
    input_timecode = Property()
    connected = Property(False)
    parameters_received = Property(False)
    network_host_device = Property()
    network_devices = DictProperty()
    __attribute_names = [
        'host_address', 'name', 'serial_number',
        'transport', 'clips', 'meta_clips',
    ]
    __attribute_defaults = {
        'clips':{}, 'meta_clips':{},
    }
    _events_ = [
        'on_events_received', 'on_parameter_value',
        'on_network_device_added', 'on_network_device_removed',
    ]
    def __init__(self, **kwargs):
        meta_clips = kwargs.get('meta_clips', {})
        for key in meta_clips.keys():
            mclip = meta_clips[key]
            if isinstance(mclip, dict):
                mclip['device'] = self
                mclip = MetaClip(**mclip)
                meta_clips[key] = mclip
        kwargs['meta_clips'] = meta_clips
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
        return obj
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
        self._listen_event = asyncio.Event()
        await self._get_all_parameters()
        await self.update_clips()
        self.connected = True
        self._update_loop_fut = asyncio.ensure_future(self._update_loop())
    async def stop(self, close_session=True):
        if not self.connected:
            return
        self.connected = False
        fut = getattr(self, '_update_loop_fut', None)
        if fut is not None:
            await fut
            self._update_loop_fut = None
        if close_session and self.session is not None:
            self.session.close()
        self.session = None
    async def _update_loop(self):
        async def inner(f, timeout):
            while self.connected:
                await f()
                await asyncio.sleep(timeout)
        coros = [
            inner(self.listen_for_events, .1),
            inner(self.update_clips, .5),
            inner(self.update_gang_params, .5),
        ]
        await asyncio.wait(coros)
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
            if clip.name not in self.meta_clips:
                mclip = MetaClip(device=self, source_clip=clip)
                self.meta_clips[clip.name] = mclip
        current = await self.get_parameter('eParamID_CurrentClip')
        if current in self.clips:
            self.transport.clip = self.clips[current]
    async def update_gang_params(self):
        for pid in ['GangEnable', 'GangMaster', 'GangList']:
            pid = 'eParamID_{}'.format(pid)
            p = self.all_parameters[pid]
            await p.get_value()
    async def listen_for_events(self):
        self._listen_event.clear()
        await self._get_all_parameters()
        a = self.listen_action
        events = await a()
        self.emit('on_events_received', self, events)
        for param_id, data in events.items():
            device_param = self.all_parameters[param_id]
            device_param.value = data['value']
        self._listen_event.set()
    async def _get_all_parameters(self):
        if self.parameters_received:
            return
        params = await self._do_action(actions.GetAllParameters)
        for param_id, param in params['by_id'].items():
            if param_id in self.all_parameters:
                continue
            device_param = DeviceParameter.create(device=self, parameter=param)
            if isinstance(device_param, NetworkServicesParameter):
                for d in device_param.devices.values():
                    self._on_network_device_added(d)
                device_param.bind(
                    on_device_added=self._on_network_device_added,
                    on_device_removed=self._on_network_device_removed,
                )
            self.all_parameters[param_id] = device_param
            device_param.bind(value=self._on_device_parameter_value)
        self.parameters_received = True
        await self.get_all_parameter_values()
    async def get_all_parameter_values(self):
        for device_param in self.all_parameters.values():
            if device_param.parameter.param_type == 'data':
                continue
            if device_param.id in ['eParamID_MACAddress', 'eParamID_NetworkServices']:
                continue
            await device_param.get_value()
    def _on_device_parameter_value(self, instance, value, **kwargs):
        if instance.id == 'eParamID_SysName':
            self.name = value
        elif instance.id == 'eParamID_FormattedSerialNumber':
            self.serial_number = value
        self.emit('on_parameter_value', instance, value, **kwargs)
    def _on_network_device_added(self, device, **kwargs):
        if device.is_host_device:
            self.network_host_device = device
        self.network_devices[device.id] = device
        self.emit('on_network_device_added', self, device)
    def _on_network_device_removed(self, device, **kwargs):
        if device.id in self.network_devices:
            del self.network_devices[device.id]
        self.emit('on_network_device_removed', self, device)
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
    async def create_gang(self, *members):
        if not len(members):
            members = [m for m in self.network_devices.values() if m is not self.network_host_device]
        addrs = []
        for member in members:
            if isinstance(member, NetworkDevice):
                addr = member.host_address
            device = await KpDevice.create(host_address=addr, loop=self.loop, session=self.session)
            p = device.all_parameters['eParamID_GangEnable']
            await p.set_value('ON')
            await device.stop(close_session=False)
            addrs.append(addr)

        p = self.all_parameters['eParamID_GangEnable']
        await p.set_value('ON')
        await p.get_value()

        p = self.all_parameters['eParamID_GangMaster']
        await p.set_value('ON')
        await p.get_value()

        p = self.all_parameters['eParamID_GangList']
        await p.set_value(','.join(addrs))
        await p.get_value()

    async def remove_gang(self):
        for member in self.network_devices.values():
            if member is self.network_host_device:
                continue
            addr = member.host_address
            device = await KpDevice.create(host_address=addr, loop=self.loop, session=self.session)
            p = device.all_parameters['eParamID_GangMaster']
            if p.value.name == 'ON':
                await p.set_value('OFF')
            p = device.all_parameters['eParamID_GangEnable']
            await p.set_value('OFF')
            await device.stop(close_session=False)

        p = self.all_parameters['eParamID_GangMaster']
        await p.set_value('OFF')
        await p.get_value()

        p = self.all_parameters['eParamID_GangEnable']
        await p.set_value('OFF')
        await p.get_value()

        p = self.all_parameters['eParamID_GangList']
        await p.set_value('')
        await p.get_value()

    def _serialize(self):
        d = {k:getattr(self, k) for k in ['name', 'serial_number', 'host_address']}
        d['meta_clips'] = {}
        for key, mclip in self.meta_clips.items():
            d['meta_clips'][key] = mclip._serialize()
        return d


class KpTransport(ObjectBase):
    active = Property(False)
    playing = Property(False)
    recording = Property(False)
    paused = Property(False)
    stopped = Property(False)
    shuttle = Property(False)
    shuttling_forward = Property(False)
    shuttling_reverse = Property(False)
    transport_str = Property('')
    timecode = Property()
    timecode_str = Property('00:00:00:00')
    timecode_remaining = Property()
    timecode_remaining_str = Property('00:00:00:00')
    frame_range = ListProperty([0, 1])
    clip = Property()
    meta_clip = Property()
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
    def __init__(self, **kwargs):
        self.bind(
            clip=self.on_clip,
            meta_clip=self.on_meta_clip,
            active=self.on_active,
            playing=self.on_playing,
            recording=self.on_recording,
            timecode=self.on_timecode,
            timecode_remaining=self.on_timecode_remaining,
        )
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
        param = self.device.all_parameters['eParamID_CurrentClip']
        while param.value != clip.name:
            await param.get_value()
        while True:
            await asyncio.sleep(0)
            if self.clip is not clip:
                continue
            if self.meta_clip is None or self.meta_clip.source_clip is not clip:
                continue
            break
        await self.go_to_timecode(self.meta_clip.start_timecode)
    async def go_to_frame(self, frame):
        tc = self.timecode.copy()
        tc.set_total_frames(frame)
        await self.go_to_timecode(tc)
    async def go_to_timecode(self, tc):
        if isinstance(tc, Timecode):
            tc = str(tc)
        await self.transport_param_get.get_value()
        param = self.device.all_parameters['eParamID_CueToTimecode']
        playing = self.playing
        await param.set_value(tc)
        param = self.timecode_param
        await param.get_value()
        while param.value != tc:
            await param.get_value()
            await asyncio.sleep(0)
        if playing:
            await self.play()
        else:
            await self.set_transport_async('Cue')
    async def play(self):
        if self.meta_clip is not None:
            if self.timecode < self.meta_clip.start_timecode:
                await self.go_to_timecode(self.meta_clip.start_timecode)
        await self.set_transport_async('Play Command')
    async def record(self):
        await self.set_transport_async('Record Command')
    async def stop(self):
        await self.set_transport_async('Stop Command')
    async def pause(self):
        await self.transport_param_get.get_value()
        if self.paused:
            return
        await self.stop()
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
    async def set_cue_in(self, tc=None):
        if self.meta_clip is not None:
            await self.meta_clip.set_cue_in(tc)
    async def set_cue_out(self, tc=None):
        if self.meta_clip is not None:
            await self.meta_clip.set_cue_out(tc)
    def on_clip(self, instance, clip, **kwargs):
        if clip is None:
            self.meta_clip = None
            self.timecode = None
            self.timecode_remaining = None
        else:
            self.meta_clip = self.device.meta_clips[clip.name]
    def on_meta_clip(self, instance, clip, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
        if clip is None:
            return
        self.timecode = self.clip.start_timecode.copy()
        self.timecode_remaining = Timecode(
            frame_format=FrameFormat(rate=self.timecode.frame_format.rate),
            total_frames=clip.duration_tc.total_frames,
        )
        self.frame_range = [
            clip.start_timecode.total_frames,
            clip.end_timecode.total_frames
        ]
        clip.bind(
            start_timecode=self.on_meta_clip_tc,
            end_timecode=self.on_meta_clip_tc,
        )
    def on_meta_clip_tc(self, instance, value, **kwargs):
        if instance is not self.meta_clip:
            return
        prop = kwargs.get('property')
        async def set_tc(end_timecode):
            tc = self.timecode
            if tc is None:
                return
            tf = end_timecode.total_frames
            if hasattr(tc, 'freerun_lock'):
                async with tc.freerun_lock:
                    tf -= tc.total_frames
            else:
                tf -= tc.total_frames
            self.timecode_remaining.set_total_frames(tf)
        if prop.name == 'end_timecode':
            asyncio.ensure_future(set_tc(value), loop=self.loop)
        self.frame_range = [
            self.meta_clip.start_timecode.total_frames,
            self.meta_clip.end_timecode.total_frames,
        ]
    def on_active(self, *args, **kwargs):
        pass
    def on_playing(self, instance, value, **kwargs):
        if self.timecode is None:
            return
        if value:
            asyncio.ensure_future(self.timecode.start_freerun(), loop=self.loop)
        else:
            asyncio.ensure_future(self.stop_freerun(), loop=self.loop)
    def on_recording(self, instance, value, **kwargs):
        if self.timecode is None:
            return
        if value:
            asyncio.ensure_future(self.timecode.start_freerun(), loop=self.loop)
        else:
            asyncio.ensure_future(self.stop_freerun(), loop=self.loop)
    def on_timecode(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
            asyncio.ensure_future(self.stop_freerun(old), loop=self.loop)
        if value is None:
            return
        self.timecode_str = str(value)
        value.bind(on_change=self.on_timecode_change)
        if self.playing or self.recording:
            asyncio.ensure_future(value.start_freerun(), loop=self.loop)
    def on_timecode_remaining(self, instance, value, **kwargs):
        old = kwargs.get('old')
        if old is not None:
            old.unbind(self)
        if value is not None:
            self.timecode_remaining_str = str(value)
            value.bind(on_change=self.on_timecode_remaining_change)
        else:
            self.timecode_remaining_str = '00:00:00:00'
    def on_timecode_change(self, tc, total_frames, **kwargs):
        prev_frames = kwargs.get('old')
        if tc is not self.timecode:
            return
        if self.meta_clip is not None and self.playing:
            if tc >= self.meta_clip.end_timecode:
                asyncio.ensure_future(self.pause(), loop=self.loop)
        self.timecode_str = str(tc)
        if self.timecode_remaining is not None:
            if total_frames > prev_frames:
                self.timecode_remaining -= total_frames - prev_frames
            else:
                self.timecode_remaining += prev_frames - total_frames
    def on_timecode_remaining_change(self, tc, total_frames, **kwargs):
        tc = kwargs.get('obj')
        self.timecode_remaining_str = str(tc)
    async def stop_freerun(self, timecode=None):
        if timecode is None:
            timecode = self.timecode
        await timecode.stop_freerun()
        param = self.timecode_param
        self.on_parameter_value(param, param.value)
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
        tc = self.timecode
        if tc is None:
            return
        if str(self.timecode) == value:
            return
        asyncio.ensure_future(tc.set_from_string_async(value), loop=self.loop)
    def process_transport_response(self, instance, value, **kwargs):
        self.transport_str = str(value)
        s = str(value).lower()
        self.playing = 'playing' in s
        self.recording = s == 'recording'
        if s.startswith('forward') or s.startswith('reverse'):
            self.paused = s.endswith('step')
            self.shuttle = s.endswith('x')
            if self.shuttle:
                self.shuttling_forward = s.startswith('forward')
                self.shuttle_reverse = not self.shuttling_forward
        else:
            self.paused = s == 'paused'
            self.shuttle = False
        if not self.shuttle:
            self.shuttling_forward = False
            self.shuttling_reverse = False
        self.active = self.playing or self.recording or self.paused or self.shuttle
        self.stopped = not self.active
