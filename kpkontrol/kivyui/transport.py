
from kivy.properties import (
    ObjectProperty,
    StringProperty,
    NumericProperty,
    BooleanProperty,
    DictProperty,
    ListProperty,
)
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.slider import Slider


class TransportWidget(BoxLayout):
    app = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    connected = BooleanProperty(False)
    playing = BooleanProperty(False)
    paused = BooleanProperty(False)
    recording = BooleanProperty(False)
    stopped = BooleanProperty(False)
    shuttling_forward = BooleanProperty(False)
    shuttling_reverse = BooleanProperty(False)
    transport_str = StringProperty('')
    frame_range = ListProperty([0, 1])
    current_frame = NumericProperty(0)
    clip_name = StringProperty('')
    timecode_str = StringProperty('00:00:00:00')
    timecode_remaining_str = StringProperty('--:--:--:--')
    __events__ = ['on_btn_release']
    def on_connected(self, instance, value):
        print('transport_widget connected: ', value, self.device)
        if not value:
            return
        attrs = [
            'playing', 'paused', 'recording', 'stopped', 'transport_str',
            'shuttling_reverse', 'shuttling_forward',
            'timecode_str', 'timecode_remaining_str',
        ]
        if self.device is not None:
            transport = self.device.transport
            for attr in attrs:
                val = getattr(transport, attr)
                setattr(self, attr, val)
            if transport.clip is not None:
                self.clip_name = transport.clip.name
            else:
                self.clip_name = ''
            self.frame_range = transport.frame_range[:]
            bkwargs = {attr:self.on_transport_prop for attr in attrs}
            bkwargs.update(dict(
                timecode=self.on_transport_timecode_obj,
                timecode_remaining=self.on_transport_timecode_obj,
                frame_range=self.on_transport_frame_range,
                clip=self.on_transport_clip,
            ))
            self.app.bind_events(transport, **bkwargs)
        else:
            for attr in attrs:
                setattr(self, attr, False)
            self.timecode_str = '00:00:00:00'
            self.timecode_remaining_str = '--:--:--:--'
            self.clip_name = ''
    def on_transport_prop(self, instance, value, **kwargs):
        # if instance is not self.device.transport:
        #     return
        # print(instance, value)
        prop_name = kwargs['property'].name
        setattr(self, prop_name, value)
        if prop_name == 'timecode_str':
            tc = self.device.transport.timecode
            if tc is not None:
                self.current_frame = tc.total_frames
    def on_transport_clip(self, instance, value, **kwargs):
        # if instance is not self.device.transport:
        #     return
        if value is None:
            self.clip_name = ''
        else:
            self.clip_name = value.name
    def on_transport_frame_range(self, instance, value, **kwargs):
        self.frame_range = value[:]
    def on_transport_timecode_obj(self, instance, value, **kwargs):
        pass
    def set_current_frame(self, frame):
        transport = self.device.transport
        return self.app.run_async_coro(transport.go_to_frame(frame))
    def on_btn_release(self, name):
        if self.device is None:
            return
        m = getattr(self.device.transport, name)
        self.app.run_async_coro(m())

class TransportPosSlider(Slider):
    transport_widget = ObjectProperty(None)
    value_set = NumericProperty(None, allownone=True)
    transport_value = NumericProperty(0.)
    def __init__(self, **kwargs):
        self.__touch_active = False
        super().__init__(**kwargs)
    def on_value(self, instance, value):
        if not self.__touch_active:
            return
        if self.value_set is not None:
            return
        self.value_set = value
    def on_transport_value(self, instance, value):
        if self.value_set is not None:
            if self.value_set != value:
                return
        self.value = value
    def on_set_current_frame_complete(self, *args):
        self.value_set = None
    def on_value_set(self, instance, value):
        if value is None:
            return
        fut = self.transport_widget.set_current_frame(value)
        fut.add_done_callback(self.on_set_current_frame_complete)
    def on_touch_down(self, touch):
        if self.disabled or not self.collide_point(*touch.pos):
            return
        self.__touch_active = True
        return super().on_touch_down(touch)
    def on_touch_up(self, touch):
        self.__touch_active = False
        return super().on_touch_up(touch)
