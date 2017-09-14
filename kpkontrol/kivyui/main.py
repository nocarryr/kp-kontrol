import os
import asyncio
import json
from functools import partial

from kpkontrol.kivyui import garden
from kpkontrol.kivyui.garden import iconfonts

FONT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fonts'))
iconfonts.register(
    'default_font',
    os.path.join(FONT_PATH, 'fontawesome-webfont.ttf'),
    os.path.join(FONT_PATH, 'font-awesome.fontd'),
)

from kivy.clock import Clock
from kivy.app import App
from kivy.properties import (
    ObjectProperty,
    StringProperty,
    NumericProperty,
    BooleanProperty,
    DictProperty,
    ListProperty,
    ConfigParserProperty,
)
from kivy.storage.jsonstore import JsonStore
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button

from kpkontrol.kivyui.aiobridge import AioBridge
from kpkontrol.kivyui.transport import TransportWidget
from kpkontrol.kivyui.cliplist import ClipList, ClipListItem
from kpkontrol.device import KpDevice


APP_SETTINGS = [
    {
        'type':'title',
        'title':'KpKontrol',
    },{
        'type':'string',
        'title':'Host Address',
        'section':'device',
        'key':'host_address',
    },
]

APP_SETTINGS_DEFAULTS = {
    'device':{
        'host_address':'',
    },
}


class RootWidget(FloatLayout):
    app = ObjectProperty(None)
    header_widget = ObjectProperty(None)
    device_selector = ObjectProperty(None)
    main_widget = ObjectProperty(None)
    device_widget = ObjectProperty(None)
    footer_widget = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    device_name = StringProperty('')
    connected = BooleanProperty(False)
    host_address = ConfigParserProperty(
        '', 'device', 'host_address', 'app', val_type=str,
    )
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_selector = DeviceSelector()
        self.device_selector.bind(on_select=self.on_device_selector_selected)
    def connect(self, *args, **kwargs):
        if self.connected:
            self.disconnect()
        if not self.host_address:
            return
        device = self.device = KpDevice(
            host_address=self.host_address,
            loop=self.app.async_server_loop,
        )
        self.app.bind_events(
            device,
            name=self.on_device_obj_name,
            connected=self.on_device_connected,
            on_network_device_added=self.on_device_network_device_added,
            on_network_device_removed=self.on_device_network_device_removed,
        )
        self.app.run_async_coro(device.connect())
    def disconnect(self, *args, **kwargs):
        self.connected = False
        if self.device is not None:
            self.device.unbind(self)
            self.device_name = ''
            self.app.run_async_coro(self.device.stop())
            self.app.dispatch('on_device_disconnect', self.device)
            self.device = None
    def on_device_connected(self, instance, value, **kwargs):
        if instance is not self.device:
            return
        self.connected = value
    def on_device_obj_name(self, instance, value, **kwargs):
        self.device_name = value
    def on_device_network_device_added(self, instance, network_device, **kwargs):
        self.device_selector.add_device(network_device)
    def on_device_network_device_removed(self, instance, network_device, **kwargs):
        pass
    def on_device_selector_selected(self, instance, btn):
        self.disconnect()
        self.host_address = btn.host_address
        self.connect()

class DeviceSelector(DropDown):
    app = ObjectProperty(None)
    btns = DictProperty()
    selected_device_id = StringProperty()
    def add_device(self, device, **kwargs):
        if device.id in self.btns:
            return
        d = dict(
            dropdown_parent=self,
            device_id=device.id,
            name=device.host_name,
            ip_address=device.ip_address,
            port=device.port,
            host_address=device.host_address,
            is_selected=device.is_host_device,
        )
        for key, val in d.items():
            kwargs.setdefault(key, val)
        btn = DeviceSelectorButton(**kwargs)
        self.btns[device.id] = btn
        self.add_widget(btn)
    def on_device_btn_selected(self, btn, value):
        if not value:
            return
        self.selected_device_id = btn.device_id
        self.select(btn)

class DeviceSelectorButton(Button):
    dropdown_parent = ObjectProperty()
    device_id = StringProperty()
    name = StringProperty()
    ip_address = ObjectProperty()
    port = NumericProperty()
    host_address = StringProperty()
    is_selected = BooleanProperty(False)
    def on_release(self, *args):
        if self.is_selected:
            return
        self.dropdown_parent.on_device_btn_selected(self, True)
    def on_dropdown_parent(self, *args):
        self.dropdown_parent.bind(selected_device_id=self.on_selected_device_id)
    def on_selected_device_id(self, instance, value):
        self.is_selected = value == self.device_id

class DeviceWidget(BoxLayout):
    app = ObjectProperty(None)
    transport_widget = ObjectProperty(None)
    clip_list = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    connected = BooleanProperty(False)

class KpKontrolApp(App):
    async_server = ObjectProperty(None)
    aio_loop = ObjectProperty(None)
    async_server_loop = ObjectProperty(None)
    btn_flash = BooleanProperty(False)
    storage = ObjectProperty(None)
    _config_base_dir = None
    __events__ = ['on_device_disconnect']
    @property
    def config_base_dir(self):
        p = self._config_base_dir
        if p is None:
            p = self._config_base_dir = self.user_data_dir
        return p
    def on_device_disconnect(self, *args, **kwargs):
        pass
    def on_start(self, *args, **kwargs):
        self.storage = self.get_application_storage()
        if self.aio_loop is None:
            self.aio_loop = asyncio.get_event_loop()
        self.async_server = AioBridge(self)
        self.async_server.start()
        self.async_server.thread_run_event.wait()
        #Clock.schedule_interval(self.tick_aio_loop, .1)
        Clock.schedule_interval(self.toggle_btn_flash, .5)
    def tick_aio_loop(self, *args, **kwargs):
        async def tick():
            await asyncio.sleep(0)
        self.aio_loop.run_until_complete(tick())
    def toggle_btn_flash(self, *args):
        self.btn_flash = not self.btn_flash
    def on_stop(self, *args, **kwargs):
        self.async_server.stop()
    def get_application_config(self):
        p = self.config_base_dir
        return super().get_application_config(os.path.join(p, '%(appname)s.ini'))
    def get_application_storage(self):
        p = self.config_base_dir
        fn = os.path.join(p, 'data.json')
        return JsonStore(fn)
    def build_config(self, config):
        for section_name, section in APP_SETTINGS_DEFAULTS.items():
            config.setdefaults(section_name, section)
    def build_settings(self, settings):
        settings.add_json_panel('KpKontrol', self.config, data=json.dumps(APP_SETTINGS))
    def bind_events(self, obj, **kwargs):
        self.async_server.bind_events(obj, **kwargs)
    def run_async_coro(self, coro):
        return self.async_server.run_async_coro(coro)

def main():
    KpKontrolApp().run()

if __name__ == '__main__':
    main()
