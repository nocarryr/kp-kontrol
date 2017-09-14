import asyncio
try:
    from urllib import urlencode
    from urlparse import urlunsplit
except ImportError:
    from urllib.parse import urlencode, urlunsplit

import aiohttp

from kpkontrol.parameters import (
    ParameterBase, EnumParameter, IntParameter, StrParameter,
)
from kpkontrol.objects import Clip


class Action(object):
    _url_path = '/'
    method = 'get'
    _query_params = None
    def __init__(self, netloc, **kwargs):
        self.netloc = netloc
        self.session = kwargs.get('session')
        self.loop = kwargs.get('loop')
        init_query_params = kwargs.get('query_params', {})
        self.query_params = self.build_query_params(**init_query_params)
        self.result = None
    async def __call__(self, **kwargs):
        self._build_session(**kwargs)
        r = await self.build_request()
        async with r:
            result = await self.process_response(r)
        self.result = result
        return result
    async def process_response(self, r):
        raise NotImplementedError()
    @property
    def url_path(self):
        return self._url_path.lstrip('/')
    @property
    def query_string(self):
        qs = getattr(self, '_query_string', None)
        if qs is not None:
            return qs
        if not len(self.query_params):
            return ''
        return urlencode(self.query_params)
    @query_string.setter
    def query_string(self, value):
        self._query_string = value
    @property
    def full_url(self):
        return self.build_url()
    def build_url(self):
        if self.method == 'get':
            sp_tpl = ('http', self.netloc, self.url_path, self.query_string, '')
        elif self.method == 'post':
            sp_tpl = ('http', self.netloc, self.url_path, '', '')
        return urlunsplit(sp_tpl)
    async def build_request(self):
        url = self.full_url
        if self.method == 'get':
            r = await self.session.get(url)
        elif self.method == 'post':
            r = await self.session.post(url, data=self.query_params)
        else:
            raise Exception('{} method not supported'.format(self.method))
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
    def _build_session(self, **kwargs):
        session = kwargs.get('session')
        loop = kwargs.get('loop')
        if session is not None:
            self.session = session
            self.loop = session._loop
        elif loop is not None:
            self.loop = loop

        if self.session is None:
            self.session = aiohttp.ClientSession(loop=self.loop)
        self.loop = self.session._loop
        return self.session

class GetAllParameters(Action):
    _url_path = 'descriptors'
    _query_params = {'paramid':'*'}
    async def process_response(self, r):
        params = {'by_id':{}, 'by_type':{}}
        for d in await r.json(content_type=None):
            param = ParameterBase.from_json(d)
            params['by_id'][param.id] = param
            if param.param_type not in params['by_type']:
                params['by_type'][param.param_type] = {}
            params['by_type'][param.param_type][param.id] = param
        return params

class GetParameter(Action):
    _url_path = 'options'
    def __init__(self, netloc, **kwargs):
        self.parameter = kwargs.get('parameter')
        super(GetParameter, self).__init__(netloc, **kwargs)
        self.query_string = self.parameter.id
    async def process_response(self, r):
        return await self.parameter.parse_response(r)

class SetParameter(Action):
    _url_path = 'config'
    method = 'post'
    def __init__(self, netloc, **kwargs):
        self.parameter = kwargs.get('parameter')
        self.value = kwargs.get('value')
        super(SetParameter, self).__init__(netloc, **kwargs)
    def build_query_params(self, **kwargs):
        kwargs['paramName'] = self.parameter.id
        kwargs['newValue'] = self.value
        return super(SetParameter, self).build_query_params(**kwargs)
    async def process_response(self, r):
        return await self.parameter.parse_response(r)

class Connect(Action):
    _url_path = 'json'
    _query_params = {'action':'connect', 'configid':0}
    async def process_response(self, r):
        data = await r.json(content_type=None)
        return data['connectionid']

class ListenForEvents(Action):
    _url_path = 'json'
    _query_params = {'action':'wait_for_config_events', 'configid':0}
    def __init__(self, netloc, **kwargs):
        self.connection_id = kwargs.get('connection_id')
        self.all_parameters = kwargs.get('all_parameters')
        super(ListenForEvents, self).__init__(netloc, **kwargs)
    async def __call__(self, **kwargs):
        self._build_session(**kwargs)
        if self.all_parameters is None:
            a = GetAllParameters(self.netloc, session=self.session)
            self.all_parameters = await a()
        if self.connection_id is None:
            a = Connect(self.netloc, session=self.session)
            self.connection_id = await a()
            self.query_params = self.build_query_params()
        return await super(ListenForEvents, self).__call__()
    def build_query_params(self, **kwargs):
        kwargs['connectionid'] = self.connection_id
        return super(ListenForEvents, self).build_query_params(**kwargs)
    async def process_response(self, r):
        self.response_obj = r
        params = {}
        data = await r.json(content_type=None)
        for d in data:
            if 'services' in d:
                param = self.all_parameters['by_id']['eParamID_NetworkServices']
                _d = {'parameter':param, 'value':d['services']}
                params[param.id] = _d
                continue
            if 'param_id' not in d:
                continue
            if 'str_value' not in d:
                continue
            param = self.all_parameters['by_id'][d['param_id']]
            _d = {'parameter':param}
            if isinstance(param, IntParameter):
                _d['value'] = int(d['int_value'])
            elif isinstance(param, EnumParameter):
                _d['value'] = param.enum_items[int(d['int_value'])]
            else:
                _d['value'] = d['str_value']
            params[param.id] = _d
        return params

class GetClips(Action):
    _url_path = 'clips'
    _query_params = {'action':'get_clips'}
    async def process_response(self, r):
        data = await r.json(content_type=None)
        clips = []
        for clipdata in data['clips']:
            clips.append(Clip.from_json(clipdata))
        return clips
