
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
