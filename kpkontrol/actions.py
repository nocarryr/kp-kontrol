try:
    from urllib import urlencode
    from urlparse import urlunsplit
except ImportError:
    from urllib.parse import urlencode, urlunsplit

import requests

from kpkontrol.objects import Clip

class RequestError(Exception):
    def __init__(self, req):
        self.status_code = req.status_code
        self.url = req.url
        self.reason = req.reason
    def __str__(self):
        return '{self.url} responded with STATUS_CODE: "{self.status_code}" ({self.reason})'.format(
            self=self
        )

class Action(object):
    _url_path = '/'
    method = 'get'
    _query_params = None
    def __init__(self, netloc, **kwargs):
        self.netloc = netloc
        init_query_params = kwargs.get('query_params', {})
        self.query_params = self.build_query_params(**init_query_params)
        self.result = None
    def __call__(self):
        r = self.build_request()
        result = self.process_response(r)
        self.result = result
        return result
    def process_response(self, r):
        raise NotImplementedError()
    @property
    def url_path(self):
        return self._url_path.lstrip('/')
    @property
    def query_string(self):
        if not len(self.query_params):
            return ''
        return urlencode(self.query_params)
    @property
    def full_url(self):
        return self.build_url()
    def build_url(self):
        sp_tpl = ('http', self.netloc, self.url_path, self.query_string, '')
        return urlunsplit(sp_tpl)
    def build_request(self):
        url = self.full_url
        if self.method == 'get':
            r = requests.get(url)
        elif self.method == 'post':
            r = requests.post(url)
        else:
            raise Exception('{} method not supported'.format(self.method))
        if not r.ok:
            raise RequestError(r)
        return r
    @classmethod
    def iter_bases(cls):
        yield cls
        if cls is not Action:
            for _cls in cls.__bases__:
                if not issubclass(_cls, Action):
                    continue
                for _subcls in _cls.iter_bases():
                    yield _subcls
    def build_query_params(self, **kwargs):
        params = {}
        for cls in self.iter_bases():
            if cls._query_params is None:
                continue
            # Allow subclasses to override
            _params = {k:v for k, v in cls._query_params.items() if k not in params}
            params.update(_params)
        params.update(kwargs)
        return params


class GetClips(Action):
    _url_path = 'clips'
    _query_params = {'action':'get_clips'}
    def process_response(self, r):
        data = r.json()
        clips = []
        for clipdata in data['clips']:
            clips.append(Clip.from_json(clipdata))
        return clips
