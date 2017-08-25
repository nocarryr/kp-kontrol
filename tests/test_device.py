from kpkontrol.device import KpDevice

def test_device(kp_http_server, all_parameter_defs):
    host_address = kp_http_server

    device = KpDevice(host_address=host_address)

    assert set(device.all_parameters.keys()) == set(all_parameter_defs.keys())

    device.set_parameter('eParamID_CurrentClip', 'A003SC10TK22.mov')
    device.update_clips()

    assert device.transport.clip.name == 'A003SC10TK22.mov'
    assert str(device.transport.timecode) == "18:25:06;12"

    device.set_parameter('eParamID_TransportState', 'Playing Forward')
    device.transport.transport_param_get.get_value()

    assert device.transport.active
    assert device.transport.playing
    assert not device.transport.recording
    assert not device.transport.paused
    assert not device.transport.shuttle

    device.set_parameter('eParamID_TransportState', 'Paused')
    device.transport.stop()

    assert device.transport.active
    assert not device.transport.playing
    assert not device.transport.recording
    assert device.transport.paused
    assert not device.transport.shuttle

    device.set_parameter('eParamID_TransportState', 'Recording')
    device.transport.record()

    assert device.transport.active
    assert not device.transport.playing
    assert device.transport.recording
    assert not device.transport.paused
    assert not device.transport.shuttle
