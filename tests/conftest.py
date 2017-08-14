import io
import threading
import shutil
from fractions import Fraction
try:
    from urllib import urlencode
    from urlparse import urlunsplit, urlsplit, parse_qs
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from urllib.parse import urlencode, urlunsplit, urlsplit, parse_qs
    from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest


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
        """},
]


class KPHttpHandler(BaseHTTPRequestHandler):
    def _get_data(self):
        p = urlsplit(self.path)
        path = p.path
        if p.query:
            query = parse_qs(p.query)
        else:
            query = None
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
def kp_http_server():
    server_thread = KPHttpServerThread()
    server_thread.start()
    server_thread.running.wait()
    yield 'localhost:{}'.format(server_thread.port)
    server_thread.stop()

@pytest.fixture
def frame_rate_defs():
    float_vals = [24., 25., 29.97, 30., 59.94, 60.]
    fraction_vals = [
        Fraction(24, 1),
        Fraction(25, 1),
        Fraction(30000, 1001),
        Fraction(30, 1),
        Fraction(60000, 1001),
        Fraction(60, 1),
    ]
    return dict({
        'floats':float_vals, 'fractions':fraction_vals
    })
