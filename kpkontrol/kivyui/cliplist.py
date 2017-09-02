from kivy.clock import Clock

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ToggleButtonBehavior

from kivy.properties import (
    ObjectProperty,
    StringProperty,
    NumericProperty,
    BooleanProperty,
    ListProperty,
    DictProperty,
)

# class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior,
#                                  RecycleBoxLayout):
#     pass

# class ClipListHeader(RecycleDataViewBehavior, BoxLayout):
#     index = None
#     selected = BooleanProperty(False)
#     selectable = BooleanProperty(False)

class ClipListItem(ToggleButtonBehavior, BoxLayout):
    selected = BooleanProperty(False)
    clip = ObjectProperty(None)
    name = StringProperty()
    start_timecode = ObjectProperty(None)
    duration = ObjectProperty(None)
    timestamp = ObjectProperty(None)
    index = NumericProperty(0)
    is_current_clip = BooleanProperty(False)
    def on_clip(self, instance, clip):
        self.name = clip.name
        self.start_timecode = clip.start_timecode
        self.duration = clip.duration_tc
        self.timestamp = clip.timestamp
    def on_state(self, *args):
        self.selected = self.state == 'down'


class ClipList(BoxLayout):
    app = ObjectProperty(None)
    list_widget = ObjectProperty(None)
    selected_item = ObjectProperty(None, allownone=True)
    current_clip_name = StringProperty('')
    device = ObjectProperty(None, allownone=True)
    list_items = DictProperty()
    __events__ = ['on_load_clip_btn', 'on_delete_clip_btn', 'on_get_url_btn']
    def __init__(self, **kwargs):
        self.group_name = '{}-list_items'.format(id(self))
        super().__init__(**kwargs)
    def on_list_widget(self, *args):
        self.list_widget.bind(minimum_height=self.list_widget.setter('height'))
    def on_device(self, *args):
        self.list_items.clear()
        self.list_widget.clear_widgets()
        self.selected_item = None
        if self.device is None:
            return
        self._update_clips(self.device, self.device.clips)
        self.app.bind_events(self.device, clips=self.update_clips)
    def update_clips(self, device, clips, **kwargs):
        if device is not self.device:
            return
        #Clock.schedule_once(self._update_clips, 0)
        self._update_clips()
    def _update_clips(self, *args, **kwargs):
        for key in sorted(self.device.clips.keys()):
            if key in self.list_items:
                continue
            clip = self.device.clips[key]
            item = ClipListItem(
                clip=clip,
                group=self.group_name,
                index=len(self.list_items),
                is_current_clip=clip.name == self.current_clip_name,
            )
            item.bind(selected=self.on_item_selected)
            self.list_items[key] = item
            self.list_widget.add_widget(item)
    def on_current_clip_name(self, instance, value):
        keys = set(self.list_items.keys())
        keys.discard(value)
        for key in keys:
            self.list_items[key].is_current_clip = False
        if value:
            item = self.list_items.get(value)
            if item is not None:
                item.is_current_clip = True
    def on_item_selected(self, instance, value):
        if value:
            self.selected_item = instance
        else:
            self.selected_item = None
    def on_load_clip_btn(self, *args):
        clip = self.selected_item.clip
        transport = self.device.transport
        self.app.run_async_coro(transport.go_to_clip(clip))
    def on_delete_clip_btn(self, *args):
        pass
    def on_get_url_btn(self, *args):
        print(self.selected_item.clip.get_url(self.device.host_address))
