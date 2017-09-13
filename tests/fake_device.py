import asyncio
import ipaddress
import json

from kpkontrol import timecode
from kpkontrol.parameters import ParameterBase
from kpkontrol.objects import Clip

DEFAULT_PARAMETER_VALS = {
    #'eParamID_TransportState':'Idle',
    'eParamID_GangEnable':'OFF',
    'eParamID_GangMaster':'OFF',
    'eParamID_GangList':'',
}

def ip_to_kp_octet(ip):
    if not isinstance(ip, ipaddress.IPv4Address):
        ip = ipaddress.ip_address(ip)
    i = int.from_bytes(ip.packed, byteorder='big')
    return i - (1 << 32)

class FakeDevice(object):
    def __init__(self, **kwargs):
        self._running = False
        self._timecode = None
        self.connections = set()
        self.loop = kwargs.get('loop')
        self.parameters = {}
        self.host_address = kwargs.get('host_address')
        self.name = kwargs.get('name')
        self.serial_number = kwargs.get('serial_number')
        self.clips = kwargs.get('clips', {})
        self.parameter_values = kwargs.get('parameter_values', {})

        parameter_defs = kwargs.get('parameter_defs', {})
        self._build_parameters(parameter_defs)
        clip_data = kwargs.get('clip_data', [])
        self.parse_clips(clip_data)

        self.playing = False
        self.paused = False
        self.stopped = True


    async def start(self):
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        for key, val in DEFAULT_PARAMETER_VALS.items():
            await self.set_formatted_value(key, val)

        await self.set_formatted_value('eParamID_SysName', self.name)
        await self.set_formatted_value('eParamID_FormattedSerialNumber', self.serial_number)
        await self.set_formatted_value('eParamID_IPAddress_3', self.host_address.split(':')[0])
        self._running = True
        self._run_coro = asyncio.ensure_future(self.run_loop())
    async def run_loop(self):
        while self._running:
            await asyncio.sleep(.1)
    async def stop(self):
        self._running = False
        tc = self.timecode
        if tc is not None:
            tc.unbind(self)
            await tc.stop_freerun()
        if getattr(self, '_run_coro', None):
            await self._run_coro
        self.timecode = None
        self._run_coro = None
    def _build_parameters(self, parameter_defs):
        for d in parameter_defs.values():
            param = ParameterBase.from_json(d)
            self.parameters[param.id] = param
    def parse_clips(self, data):
        for d in data:
            clip = Clip.from_json(d)
            if clip.name in self.clips:
                continue
            self.clips[clip.name] = clip
    @property
    def timecode(self):
        return self._timecode
    @timecode.setter
    def timecode(self, tc):
        self._timecode = tc
        old = self.timecode
        if old is not None and self._running:
            old.unbind(self)
            asyncio.ensure_future(old.stop_freerun())
        if tc is None:
            tc = self.build_default_timecode()
        self._timecode = tc
        asyncio.ensure_future(self.set_formatted_value('eParamID_DisplayTimecode', str(tc)))
        tc.bind(on_change=self.on_timecode_change)
    @property
    def current_clip(self):
        clip_name = self.get_formatted_value('eParamID_CurrentClip')
        return self.clips.get(clip_name)
    def on_timecode_change(self, tc, total_frames, **kwargs):
        if tc is not self.timecode:
            return
        asyncio.ensure_future(self.set_formatted_value('eParamID_DisplayTimecode', str(tc)))
    async def update_current_clip(self, old):
        clip = self.current_clip
        if clip is None:
            self.timecode = None
        elif clip.name == old:
            return
        else:
            self.timecode = clip.start_timecode.copy()
    def build_default_timecode(self):
        fr = timecode.FrameRate.from_float(29.97)
        ff = timecode.FrameFormat(rate=fr, drop_frame=True)
        return timecode.Timecode(frame_format=ff)
    async def cue_to_timecode(self, tc_str):
        if self.current_clip is None:
            return
        await self.set_formatted_value('eParamID_TransportState', 'Paused')
        await self.timecode.set_from_string_async(tc_str)
    async def update_transport_command(self, old):
        cmd = self.get_formatted_value('eParamID_TransportCommand')
        if cmd == 'Play Command':
            state = 'Playing Forward'
        elif cmd == 'Record Command':
            state = 'Recording'
        elif cmd == 'Stop Command':
            if self.playing:
                state = 'Paused'
            else:
                state = 'Idle'
        elif cmd == 'Cue':
            state = 'Paused'
        elif cmd == 'Single Step Forward':
            state = 'Forward Step'
        elif cmd == 'Single Step Reverse':
            state = 'Reverse Step'
        else:
            ## TODO:
            state = 'Idle'
        await self.set_formatted_value('eParamID_TransportState', state)
    async def update_transport_state(self, old):
        state = self.get_formatted_value('eParamID_TransportState')
        if old == state:
            return
        print('eParamID_TransportState: ', state)
        if state == 'Forward Step':
            if self.current_clip is None:
                await self.set_formatted_value('eParamID_TransportState', 'Idle')
                return
            await self.timecode.stop_freerun()
            self.timecode += 1
            await self.set_formatted_value('eParamID_TransportState', 'Paused')
            return
        elif state == 'Reverse Step':
            if self.current_clip is None:
                await self.set_formatted_value('eParamID_TransportState', 'Idle')
                return
            await self.timecode.stop_freerun()
            self.timecode -= 1
            await self.set_formatted_value('eParamID_TransportState', 'Paused')
            return
        self.playing = state == 'Playing Forward'
        self.paused = state == 'Paused'
        self.stopped = state == 'Idle'
        if self.playing:
            if self.current_clip is None:
                clip_name = sorted(self.clips.keys())[0]
                await self.set_formatted_value('eParamID_CurrentClip', clip_name)
            await self.timecode.start_freerun()
        elif self.paused:
            await self.timecode.stop_freerun()
        elif self.stopped:
            await self.set_formatted_value('eParamID_CurrentClip', '')
    def get_parameter_value(self, param_id):
        vals = self.parameter_values
        param = self.parameters[param_id]
        value = vals.get(param_id, param.default_value)
        if param.param_type in ['integer', 'enum']:
            value = int(value)
        return value
    async def set_parameter_value(self, param_id, value):
        param = self.parameters[param_id]
        if param.param_type in ['integer', 'enum', 'octets']:
            value = int(value)
        old = self.get_formatted_value(param_id)
        self.parameter_values[param_id] = value
        if param_id == 'eParamID_TransportCommand':
            await self.update_transport_command(old)
        elif param_id == 'eParamID_TransportState':
            await self.update_transport_state(old)
        elif param_id == 'eParamID_GoToClip':
            await self.set_formatted_value('eParamID_TransportState', 'Idle')
            await self.set_parameter_value('eParamID_CurrentClip', value)
            await self.set_formatted_value('eParamID_TransportState', 'Paused')
        elif param_id == 'eParamID_CueToTimecode':
            await self.cue_to_timecode(value)
        elif param_id == 'eParamID_CurrentClip':
            await self.update_current_clip(old)
        return json.dumps(self.format_response(param_id))
    def get_formatted_value(self, param_id):
        value = self.get_parameter_value(param_id)
        param = self.parameters[param_id]
        if param.param_type == 'enum':
            return param.format_value(value)
        elif param.param_type == 'octets':
            if value < 0:
                value += 1 << 32
            return ipaddress.ip_address(value)
        return value
    async def set_formatted_value(self, param_id, value):
        param = self.parameters[param_id]
        if param.param_type == 'enum':
            item = param.enum_items[value]
            value = item.value
        elif param.param_type == 'octets':
            value = ip_to_kp_octet(value)
        await self.set_parameter_value(param_id, value)
    def format_response(self, param_id):
        param = self.parameters[param_id]
        if param_id == 'eParamID_DisplayTimecode' and self.timecode is not None:
            value = str(self.timecode)
        else:
            value = self.get_parameter_value(param_id)
        if param_id == 'eParamID_NetworkServices':
            d = {'services':value, 'param_id':param_id}
        elif param.param_type == 'enum':
            if not len(param.enum_items):
                d = {'param_id':param_id, 'int_value':value}
            else:
                item = param.item_from_value(value)
                d = {'param_id':param_id, 'value':value, 'value_name':item.name}
        else:
            d = {'param_id':param_id, 'str_value':str(value), 'value':value, 'int_value':value}
        return d
    async def build_network_services_data(self, devices):
        l = []
        for device in devices:
            if ':' in device.host_address:
                ip, port = device.host_address.split(':')
            else:
                ip = device.host_address
                port = '80'
            l.append({
                'description':'Tapeless Recorder',
                'boardType':'0',
                'ip_address':ip,
                'port':port,
                'service_domain':'local',
                'host_name':device.name,
                'device_name':'Ki Pro',
                'service_type':'_http._tcp',
            })
        await self.set_parameter_value('eParamID_NetworkServices', l)
    async def get_listen_events(self, connection_id):
        l = []
        if connection_id not in self.connections:
            self.connections.add(connection_id)
            params = ['eParamID_NetworkServices']
        else:
            params = ['eParamID_DisplayTimecode']
        for param_id in params:
            l.append(self.format_response(param_id))
        return json.dumps(l)
