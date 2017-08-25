import os
import asyncio
import json
from fractions import Fraction

from aiohttp import web

import pytest


TEST_DIR = os.path.dirname(os.path.abspath(__file__))

def get_all_parameter_defs(deserialize=True):
    fn = os.path.join(TEST_DIR, 'data', 'kp-params-flat.json')
    with open(fn, 'r') as f:
        s = f.read()
    if deserialize:
        data = json.loads(s)
        return {p['param_id']:p for p in data}
    return s

PARAMETER_DEFS = get_all_parameter_defs()

@pytest.fixture
def all_parameter_defs(request):
    def clean_values():
        for key in PARAMETER_DEFS.keys():
            if '_value' in PARAMETER_DEFS[key]:
                del PARAMETER_DEFS[key]['_value']
    request.addfinalizer(clean_values)
    return PARAMETER_DEFS

def get_parameter_response_crap_json(param_id, value=None):
    param = PARAMETER_DEFS[param_id]
    if value is not None:
        if value.isdigit() and param['param_type'] == 'enum':
            value = int(value)
        PARAMETER_DEFS[param_id]['_value'] = value
    else:
        value = param.get('_value', param['default_value'])
    resp = ['[']
    if param['param_type'] == 'enum':
        for item in param['enum_values']:
            selected = 'false'
            if isinstance(value, str) and value == item['short_text']:
                selected = 'true'
            if isinstance(value, int) and value == item['value']:
                selected = 'true'
            item = item.copy()
            item['selected'] = str(selected).lower()
            s = 'value:"{value}", text:"{text}", short_text:"{short_text}", selected:"{selected}"'.format(**item)
            s = '{%s},' % (s)
            resp.append(s)
    else:
        s = 'str_value:"{value}", value:"{value}", int_value:"{value}", param_id:"{param_id}"'.format(
            value=value, param_id=param['param_id'],
        )
        s = '{%s},' % (s)
        resp.append(s)
    resp[-1] = resp[-1].rstrip(',')
    resp.append('];')
    return '\n'.join(resp)

def get_parameter_response_real_json(param_id, value=None):
    param = PARAMETER_DEFS[param_id]
    if value is not None:
        if value.isdigit() and param['param_type'] == 'enum':
            value = int(value)
        PARAMETER_DEFS[param_id]['_value'] = value
    else:
        value = param.get('_value', param['default_value'])
    data = {'value':None, 'str_value':None}
    if param['param_type'] == 'enum':
        for item in param['enum_values']:
            if isinstance(value, str) and value != item['short_text']:
                continue
            if isinstance(value, int) and value != item['value']:
                continue
            data = {'value':item['value'], 'value_name':item['short_text']}
    else:
        data = {k:value for k in ['value', 'str_value']}
    return json.dumps(data)


KP_RESPONSE_DATA = [
    {'url_path':'/clips',
    'query_params':{'action':['get_clips']},
    'response':"""
        {"clips": [
            {"format": "1920x1080i29.97",
              "timestamp": "08/05/17 18:59:16",
              "height": "1080",
              "duration": "00:34:09:20",
              "clipname": "A003SC10TK22.mov",
              "framerate": "29.97",
              "width": "1920",
              "interlace": "1",
              "fourcc": "apcn",
              "attributes": {
                "Audio Chan": "2",
                "CC": "0",
                "Format": "1920x1080i29.97",
                "Starting TC": "18:25:06;12",
                "Encode Type": "0"
              },
              "framecount": "61429"
            }
        ]}
        """,
    },
    {'url_path':'/descriptors',
    'query_params':{'paramid':['*']},
    'response':get_all_parameter_defs(deserialize=False),
    },
]


class KPHttpHandler(object):
    async def _get_data(self, request):
        u = request.url
        path = u.path
        if request.method == 'POST':
            query = await request.post()
        else:
            query = u.query
        if path == '/options':
            param_id = u.query_string.lstrip('?')
            return {'response':get_parameter_response_real_json(param_id)}
        elif path == '/config':
            param_id = query.getall('paramName')
            if isinstance(param_id, list):
                param_id = param_id[0]
            value = query.getall('newValue')
            if isinstance(value, list):
                value = value[0]
            return {'response':get_parameter_response_crap_json(param_id, value)}
        for resp_data in KP_RESPONSE_DATA:
            if resp_data['url_path'] != path:
                continue
            if resp_data.get('query_params'):
                if set(resp_data['query_params'].keys()) != set(query.keys()):
                    continue
                match = True
                for key, val in resp_data['query_params'].items():
                    if query.getall(key) != val:
                        match = False
                        break
                if not match:
                    continue
            return resp_data
        return None
    async def do_GET(self, request):
        resp_data = await self._get_data(request)
        if resp_data is None:
            raise web.HTTPNotFound(text='Not Found')

        r = ''.join(resp_data['response'].splitlines())
        return web.Response(body=r, content_type='text/javascript')


class KPHttpServer(object):
    def __init__(self, *args, **kwargs):
        pass
    async def start(self, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.running = asyncio.Event()
        self.run_coro = asyncio.ensure_future(self.run())
        await self.running.wait()
        self.host_address = '{self.host}:{self.port}'.format(self=self)
        return self.host_address
    async def run(self):
        print(self.loop)
        self.handler = KPHttpHandler()
        self.app = web.Application(loop=self.loop)
        for d in KP_RESPONSE_DATA:
            self.app.router.add_route('*', d['url_path'], self.handler.do_GET)
        self.w_server = web.Server(self.handler.do_GET)
        self.server = await self.loop.create_server(self.w_server, '127.0.0.1', 0)
        self.host, self.port = self.server.sockets[0].getsockname()

        self.running.set()
        while self.running.is_set():
            await asyncio.sleep(.1)

        await self.w_server.shutdown()
        self.server.close()
        await self.server.wait_closed()
        self.server = None
    async def stop(self):
        if not self.running.is_set():
            return
        self.running.clear()
        await self.run_coro

@pytest.fixture
def kp_http_server():
    event_loop = asyncio.get_event_loop()
    server = KPHttpServer(loop=event_loop)
    return server

FRAME_RATES = [
    (23.98, Fraction(24000, 1001)),
    (24., Fraction(24, 1)),
    (25., Fraction(25, 1)),
    (29.97, Fraction(30000, 1001)),
    (30., Fraction(30, 1)),
    (50., Fraction(50, 1)),
    (59.94, Fraction(60000, 1001)),
    (60., Fraction(60, 1)),
    (119.88, Fraction(120000, 1001)),
    (120., Fraction(120, 1)),
]

@pytest.fixture(params=FRAME_RATES)
def frame_rate_defs(request):
    flt_val, frac_val = request.param
    return {'float':flt_val, 'fraction':frac_val}

@pytest.fixture
def clip_format_defs():
    field_fmts = ['i', 'p', 'PsF']
    resolutions = [
        (720, 486), (720, 576), (1280, 720), (1920, 1080), (2048, 1080),
        (3840, 2160), (4096, 2160),
    ]
    defs = []
    for fr_flt, fr_frac in FRAME_RATES:
        for field_fmt in field_fmts:
            for res in resolutions:
                w, h = res
                d = dict(
                    width=w,
                    height=h,
                    interlaced=field_fmt=='i',
                    field_fmt=field_fmt,
                    rate_float=fr_flt,
                    rate_fraction=fr_frac,
                )
                fmt_str = '{width}x{height}{field_fmt} {rate_float}'.format(**d)
                d['format_string'] = fmt_str
                defs.append(d)
    return defs

@pytest.fixture
def parameter_test_data():
    data = dict(
        param_id='eParamID_Foo',
        param_name='Foo',
        default_value=0,
        min_value=0,
        max_value=10,
        class_names=['test'],
        string_attributes=[
            {'name':'description',
            'value':'Foo Description'},
        ],
    )
    return data
