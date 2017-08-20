import numbers
import datetime
import json
import re

from kpkontrol.timecode import FrameRate, FrameFormat, Timecode

def parse_crap_json(s):
    c = re.compile('([a-zA-Z_]+):')
    s = ''.join(s.splitlines())
    s = s.strip(';')
    s = c.sub(r'"\1":', s)
    return json.loads(s)

class ObjectBase(object):
    __attribute_names = None
    __attribute_defaults = None
    def __init__(self, **kwargs):
        names, defaults = self._get_attribute_data()
        self.attribute_names_ = names
        for key in names:
            val = kwargs.get(key, defaults.get(key))
            setattr(self, key, val)
    @classmethod
    def iter_bases(cls):
        yield cls
        for subcls in cls.__bases__:
            if subcls is ObjectBase:
                break
            if not issubclass(subcls, ObjectBase):
                continue
            yield subcls
            for _cls in subcls.iter_bases():
                yield _cls
    @classmethod
    def _get_attribute_data(cls):
        all_names = set()
        all_defaults = {}
        for _cls in cls.iter_bases():
            attr = '_{}__attribute_names'.format(_cls.__name__)
            names = getattr(_cls, attr, None)
            if names is not None:
                all_names |= set(names)
            attr = '_{}__attribute_defaults'.format(cls.__name__)
            defaults = getattr(_cls, attr, None)
            if defaults is not None:
                defaults = defaults.copy()
                for key, val in defaults.items():
                    if isinstance(val, list):
                        defaults[key] = val[:]
                    elif isinstance(val, dict):
                        defaults[key] = val.copy()
                all_defaults.update(defaults)
                all_names |= set(defaults.keys())
        return all_names, all_defaults

class ParameterBase(ObjectBase):
    """Parameter definition as reported by the device

    Holds descriptive information and data used to set/get values (where possible).
    The parameter data is retrieved with :class:`kpkontrol.actions.GetAllParameters`.

    Attributes:
        id (str): The param_id used to get or set the parameter value
        name (str): Short name for the parameter
        description (str): Parameter description
        default_value: The device's default value for the parameter
        min_value: Minimum value allowed
        max_value: Maximum value allowed
        class_names (list): A ``list`` containing type information (readonly, etc.)
        relations (dict): A ``dict`` containing conditions for the parameter
            based on the values of other parameters
        persistence_type (str): Value persistence of the parameter on the device
            (persistent/ephemeral)
        register_type (str): Values can be either "excluded" or "included", but
            the significance seems unclear
        param_type (str): The parameter's value type which can be one of
            "data", "enum", "integer", "string", "octets", "octets_read_only".
            This is used to determine which subclass to use for the Parameter

    """
    __attribute_names = [
        'id', 'name', 'description', 'default_value', 'min_value', 'max_value',
        'class_names', 'relations', 'register_type',
        'persistence_type', 'param_type',
    ]
    __attribute_defaults = {
        'class_names':[],
        'relations':{},
    }
    @classmethod
    def from_json(cls, data):
        """Parses the data from the device and creates an instance of :class:`ParameterBase`

        The subclass is chosen from the given 'param_type' and further
        processing is done in the :meth:`_from_json` ``classmethod``

        Args:
            data (dict): The data received from the device

        """
        param_type = data['param_type']
        param_cls = PARAMETER_TYPES.get(param_type, cls)
        return param_cls._from_json(data)
    @classmethod
    def _from_json(cls, data, **kwargs):
        kwargs.update(dict(
            id=data['param_id'],
            name=data['param_name'],
            default_value=data.get('default_value'),
            min_value=data.get('min_value'),
            max_value=data.get('max_value'),
            class_names=data.get('class_names', []),
            relations=data.get('relations', {}),
            register_type=data.get('register_type'),
            persistence_type=data.get('persistence_type'),
            param_type=data['param_type'],
        ))
        for d in data.get('string_attributes', []):
            key = d.get('name')
            val = d.get('value')
            if key in ['description']:
                kwargs[key] = val
        return cls(**kwargs)
    def format_value(self, value):
        """Formats the parameter value into the appropriate type

        Args:
            value: The value to be formatted

        """
        return str(value)
    def parse_response(self, r):
        """Parses the response from :class:`kpkontrol.actions.GetParameter`

        Args:
            r: :class:`requests.Response` object

        """
        s = r.content
        if isinstance(s, bytes):
            s = s.decode('UTF-8')
        parsed = parse_crap_json(s)
        if isinstance(parsed, list) and len(parsed) == 1:
            parsed = parsed[0]
        return parsed
    def __repr__(self):
        return '<{self.__class__.__name__}: {self.name} ({self.id})>'.format(self=self)
    def __str__(self):
        return self.name

class EnumParameter(ParameterBase):
    """Enum parameter definition

    Attributes:
        enum_items (dict): Contains :class:`ParameterEnumItem` objects stored
            using the item name as the key
        enum_items_by_value (dict): Contains :class:`ParameterEnumItem` objects
            stored using the item value as the key

    """
    __attribute_names = ['enum_items']
    __attribute_defaults = {
        'enum_items':{},
    }
    def __init__(self, **kwargs):
        enum_items = kwargs.pop('enum_items', [])
        super(EnumParameter, self).__init__(**kwargs)
        self.enum_items_by_value = {}
        for item in enum_items:
            self.add_enum_item(item)
    @classmethod
    def _from_json(cls, data, **kwargs):
        kwargs['enum_items'] = data['enum_values']
        return super(EnumParameter, cls)._from_json(data, **kwargs)
    def add_enum_item(self, item):
        if not isinstance(item, ParameterEnumItem):
            item = ParameterEnumItem.from_json(item, parameter=self)
        else:
            item.parameter = self
        self.enum_items[item.name] = item
        self.enum_items_by_value[item.value] = item
        return item
    def item_from_value(self, value):
        return self.enum_items_by_value[value]
    def format_value(self, value):
        """Returns the item for the given value

        If the given value is ``int`` the item matching the :class:`ParameterEnumItem`
        value is used.

        If value is ``str`` the item matching the :class:`ParameterEnumItem`
        name is used.

        Args:
            value (int or str):

        Returns:
            :class:`ParameterEnumItem`

        """
        if isinstance(value, numbers.Number):
            item = self.item_from_value(value)
        else:
            item = self.enum_items[value]
        return str(item)
    def parse_response(self, r):
        parsed = super(EnumParameter, self).parse_response(r)
        for d in parsed:
            if d.get('selected') == 'true':
                return self.enum_items[d['text']]

class ParameterEnumItem(ObjectBase):
    """Enumeration data used by :class:`EnumParameter`

    Attributes:
        name (str):
        description (str):
        value (int):

    """
    __attribute_names = [
        'name', 'description', 'value',
    ]
    def __init__(self, **kwargs):
        super(ParameterEnumItem, self).__init__(**kwargs)
        self.parameter = kwargs.get('parameter')
    @classmethod
    def from_json(cls, data, **kwargs):
        kwargs.update(dict(
            name=data['short_text'],
            description=data['text'],
            value=data['value'],
        ))
        return cls(**kwargs)
    def __repr__(self):
        return str(self)
    def __str__(self):
        return self.name

class IntParameter(ParameterBase):
    """Parameter with an integer value type

    Attributes:
        value_suffix_singular (str): Suffix used for singular values
        value_suffix_plural (str): Suffix used for plural values

    """
    __attribute_names = [
        'value_suffix_singular', 'value_suffix_plural',
    ]
    @classmethod
    def _from_json(cls, data, **kwargs):
        for d in data.get('string_attributes', []):
            key = d.get('name')
            val = d.get('value')
            if key in ['value_suffix_singular', 'value_suffix_plural']:
                kwargs[key] = val
        return super(IntParameter, cls)._from_json(data, **kwargs)
    def format_value(self, value):
        if value == 1:
            suffix = self.value_suffix_singular
        else:
            suffix = self.value_suffix_plural
        return '{} {}'.format(value, suffix)
    def parse_response(self, r):
        parsed = super(IntParameter, self).parse_response(r)
        return int(parsed['value'])

class StrParameter(ParameterBase):
    """Parameter with a string value type

    Attributes:
        min_length (int):
        max_length (int):

    """
    __attribute_names = [
        'min_length', 'max_length',
    ]
    @classmethod
    def _from_json(cls, data, **kwargs):
        kwargs.update({k:data[k] for k in ['min_length', 'max_length']})
        return super(StrParameter, cls)._from_json(data, **kwargs)
    def parse_response(self, r):
        parsed = super(StrParameter, self).parse_response(r)
        return str(parsed['value'])

class OctetParameter(ParameterBase):
    pass

PARAMETER_TYPES = {
    'enum':EnumParameter,
    'integer':IntParameter,
    'string':StrParameter,
}

class ClipFormat(ObjectBase):
    """Video format information

    Attributes:
        width (int): Width in pixels
        height (int): Height in pixels
        frame_rate: :class:`~kpkontrol.timecode.FrameRate`
        interlaced (bool): Whether the format is interlaced (``True``) or
            progressive (``False``)
        fourcc (str): FOURCC codec information

    """
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
        fr = data['framerate']
        if fr == '29.97':
            fr = FrameRate(30000, 1001)
        elif fr == '59.94':
            fr = FrameRate(60000, 1001)
        else:
            fr = FrameRate(int(fr), 1)
        kwargs['frame_rate'] = fr
        kwargs['interlaced'] = data['interlace'] == '1'
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
    """Clip information

    Attributes:
        name (str): The clip filename
        duration_tc: The clip duration as a :class:`~kpkontrol.timecode.Timecode`
            instance
        duration_timedelta: The clip duration as a :class:`datetime.timedelta`
        total_frames (int): Total number of video frames
        timestamp: The last modified time for the clip as a :class:`datetime.datetime`
            (Does not contain timezone information)
        format: An :class:`ClipFormat` object containing video format information
        audio_channels (int): Number of audio channels in the clip
        start_timecode: The starting timecode for the clip as a
            :class:`~kpkontrol.timecode.Timecode` object

    """
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
    def __repr__(self):
        return '<{self.__class__.__name__}: {self}>'.format(self=self)
    def __str__(self):
        return self.name
