from kpkontrol import actions, objects, timecode

def get_base_attr_data():
    all_names = set(objects.ParameterBase._ParameterBase__attribute_names).copy()
    all_defaults = objects.ParameterBase._ParameterBase__attribute_defaults.copy()
    return all_names, all_defaults

def test_int_parameter(parameter_test_data):
    all_names, all_defaults = get_base_attr_data()
    all_names |= set(objects.IntParameter._IntParameter__attribute_names)

    parameter_test_data['param_type'] = 'integer'
    parameter_test_data['string_attributes'].extend([
        {'name':'value_suffix_singular',
        'value':'thing'},
        {'name':'value_suffix_plural',
        'value':'things'},
    ])

    param = objects.ParameterBase.from_json(parameter_test_data)

    assert isinstance(param, objects.IntParameter)

    assert param.attribute_names_ == all_names

    assert param.id == 'eParamID_Foo'
    assert param.name == 'Foo'
    assert param.default_value == 0
    assert param.min_value == 0
    assert param.max_value == 10
    assert param.class_names == ['test']
    assert param.param_type == 'integer'
    assert param.description == 'Foo Description'
    assert param.value_suffix_singular == 'thing'
    assert param.value_suffix_plural == 'things'

    assert param.format_value(0) == '0 things'
    assert param.format_value(1) == '1 thing'
    assert param.format_value(2) == '2 things'

def test_enum_parameter(parameter_test_data):
    all_names, all_defaults = get_base_attr_data()
    all_names |= set(objects.EnumParameter._EnumParameter__attribute_names)

    parameter_test_data['param_type'] = 'enum'
    parameter_test_data['enum_values'] = [
        {'value':0,
        'short_text':'bar',
        'text':'Bar'},
        {'value':1,
        'short_text':'baz',
        'text':'Baz'},
    ]

    param = objects.ParameterBase.from_json(parameter_test_data)

    assert isinstance(param, objects.EnumParameter)

    assert param.attribute_names_ == all_names

    assert param.id == 'eParamID_Foo'
    assert param.name == 'Foo'
    assert param.default_value == 0
    assert param.min_value == 0
    assert param.max_value == 10
    assert param.class_names == ['test']
    assert param.param_type == 'enum'
    assert param.description == 'Foo Description'

    for i, item_name in enumerate(['bar', 'baz']):
        assert item_name in param.enum_items

        item = param.enum_items[item_name]
        assert isinstance(item, objects.ParameterEnumItem)
        assert item.attribute_names_ == set(['name', 'description', 'value'])

        assert item.description == item_name.title()
        assert item.value == i
        assert param.enum_items_by_value[i] == param.item_from_value(i) == item

        assert param.format_value(item.value) == param.format_value(item.name) == item.name
