import os
import sys
import io
import threading
import shutil
import json
from fractions import Fraction
try:
    from urllib import urlencode
    from urlparse import urlunsplit, urlsplit, parse_qs
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from urllib.parse import urlencode, urlunsplit, urlsplit, parse_qs
    from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

PY3 = sys.version_info.major >= 3


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


class KPHttpHandler(BaseHTTPRequestHandler):
    def _get_data(self):
        p = urlsplit(self.path)
        path = p.path
        if p.query:
            query = parse_qs(p.query)
        else:
            query = None
        if path == '/options':
            param_id = p.query.lstrip('?')
            return {'response':get_parameter_response_real_json(param_id)}
        elif path == '/config':
            param_id = query.get('paramName')
            if isinstance(param_id, list):
                param_id = param_id[0]
            value = query.get('newValue')
            if isinstance(value, list):
                value = value[0]
            return {'response':get_parameter_response_crap_json(param_id, value)}
        for resp_data in KP_RESPONSE_DATA:
            if resp_data['url_path'] != path:
                continue
            if resp_data.get('query_params') and resp_data['query_params'] != query:
                continue
            return resp_data
        return None
    def do_GET(self):
        resp_data = self._get_data()
        if resp_data is None:
            self.send_error(404, 'Not Found')
            return None
        r = ''.join(resp_data['response'].splitlines())
        if PY3:
            f = io.BytesIO()
            f.write(bytes(r, 'UTF-8'))
        else:
            f = io.StringIO()
            f.write(r.decode('UTF-8'))
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", 'text/javascript')
        self.send_header("Content-Length", str(length))
        self.end_headers()
        try:
            shutil.copyfileobj(f, self.wfile)
        finally:
            f.close()

class KPHttpServerThread(threading.Thread):
    def __init__(self):
        super(KPHttpServerThread, self).__init__()
        self.running = threading.Event()
        self.server = None
        self.port = None
    def run(self):
        self.server = HTTPServer(('localhost', 0), KPHttpHandler)
        self.port = self.server.server_port
        self.running.set()
        self.server.serve_forever()
        self.running.clear()
    def stop(self):
        if not self.running.is_set():
            return
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.server = None

@pytest.fixture
def kp_http_server(monkeypatch):
    monkeypatch.setattr('kpkontrol.actions.SetParameter.method', 'get')
    server_thread = KPHttpServerThread()
    server_thread.start()
    server_thread.running.wait()
    yield 'localhost:{}'.format(server_thread.port)
    server_thread.stop()

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
