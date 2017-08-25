import datetime
from fractions import Fraction

from kpkontrol import actions, objects, timecode, parameters

def test_get_clips(kp_http_server):
    action = actions.GetClips(kp_http_server)
    assert action.full_url == 'http://{}/clips?action=get_clips'.format(kp_http_server)

    results = action()
    assert isinstance(results, list)
    assert len(results) == 1

    clip = results[0]
    assert isinstance(clip, objects.Clip)
    assert isinstance(clip.format, objects.ClipFormat)
    assert isinstance(clip.format.frame_rate, timecode.FrameRate)
    assert isinstance(clip.start_timecode, timecode.Timecode)
    assert isinstance(clip.duration_tc, timecode.Timecode)

    assert clip.name == 'A003SC10TK22.mov'
    assert clip.total_frames == 61429
    assert clip.timestamp == datetime.datetime(2017, 8, 5, 18, 59, 16)
    assert clip.audio_channels == 2
    assert clip.format.width == 1920
    assert clip.format.height == 1080
    assert clip.format.frame_rate.value == Fraction(30000, 1001)
    assert clip.format.interlaced is True
    assert clip.format.fourcc == 'apcn'
    assert str(clip.format) == '1920x1080i29.97'
    assert str(clip.start_timecode) == '18:25:06;12'
    assert str(clip.duration_tc) == '00:34:09:20'

def test_get_parameters(kp_http_server, all_parameter_defs):

    host_address = kp_http_server
    action = actions.GetAllParameters(host_address)

    all_parameters = action()

    for param in all_parameters['by_id'].values():
        if param.param_type in ['data', 'octets', 'octets_read_only']:
            continue
        assert param is all_parameters['by_id'][param.id]
        assert param.id == all_parameter_defs[param.id]['param_id']
        assert param.param_type == all_parameter_defs[param.id]['param_type']

        action = actions.GetParameter(host_address, parameter=param)
        value = action()
        if value is None:
            assert not all_parameter_defs[param.id]['default_value']
        elif param.param_type == 'enum':
            assert isinstance(value, parameters.ParameterEnumItem)
            assert value.value == all_parameters['by_id'][param.id].default_value == all_parameter_defs[param.id]['default_value']
        else:
            assert value == all_parameter_defs[param.id].get('_value', all_parameter_defs[param.id]['default_value'])

            if param.param_type == 'string':
                assert isinstance(value, str)
            elif param.param_type == 'integer':
                assert isinstance(value, int)

        if param.param_type == 'enum':
            for item in param.enum_items.values():
                action = actions.SetParameter(host_address, parameter=param, value=item.value)
                response = action()
                assert response is item

                action2 = actions.GetParameter(host_address, parameter=param)
                response2 = action2()
                assert response2 is response

        else:
            action = actions.SetParameter(host_address, parameter=param, value='42')
            response = action()
            if param.param_type == 'string':
                assert response == '42'
            else:
                assert response == 42

            action2 = actions.GetParameter(host_address, parameter=param)
            response2 = action2()
            assert response2 == response
