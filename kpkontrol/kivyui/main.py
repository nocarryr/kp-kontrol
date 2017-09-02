import os
import asyncio
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
)
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout

from kpkontrol.kivyui.aiobridge import AioBridge
from kpkontrol.kivyui.transport import TransportWidget
from kpkontrol.kivyui.cliplist import ClipList, ClipListItem
from kpkontrol.device import KpDevice

class RootWidget(FloatLayout):
    app = ObjectProperty(None)
    header_widget = ObjectProperty(None)
    main_widget = ObjectProperty(None)
    device_widget = ObjectProperty(None)
    footer_widget = ObjectProperty(None)
    device = ObjectProperty(None, allownone=True)
    device_name = StringProperty('')
    connected = BooleanProperty(False)
    host_address = StringProperty('192.168.1.197')
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
        )
        self.app.run_async_coro(device.connect())
    def disconnect(self, *args, **kwargs):
        self.connected = False
        if self.device is not None:
            self.device.unbind(self)
            self.device_name = ''
            self.app.run_async_coro(self.device.stop())
            self.device = None
    def on_device_connected(self, instance, value, **kwargs):
        if instance is not self.device:
            return
        self.connected = value
    def on_device_obj_name(self, instance, value, **kwargs):
        self.device_name = value

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
    def on_start(self, *args, **kwargs):
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
    def bind_events(self, obj, **kwargs):
        self.async_server.bind_events(obj, **kwargs)
    def run_async_coro(self, coro):
        return self.async_server.run_async_coro(coro)

def main():
    KpKontrolApp().run()

if __name__ == '__main__':
    main()
