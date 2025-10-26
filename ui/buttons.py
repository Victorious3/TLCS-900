from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.properties import ListProperty, StringProperty, NumericProperty
from kivy.core.window import Window
from kivy.metrics import dp

from kivy.lang import Builder

Builder.load_file("ui/buttons.kv")

class Icon(Image):
    def on_touch_down(self, touch):
        return False
    def on_touch_up(self, touch):
        return False

class IconButton(Button):
    icon_color = ListProperty([1, 1, 1, 1])
    default_color = ListProperty([0.2, 0.2, 0.2, 1])
    hover_color = ListProperty([0.25, 0.25, 0.25, 1])
    source = StringProperty("")
    icon_height = NumericProperty(dp(20))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = self.default_color
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, widget, pos):
        if self.get_root_window() is not None:
            inside = self.collide_point(*self.to_widget(*pos))
            if inside and not self.disabled:
                self.background_color = self.hover_color
            else:
                self.background_color = self.default_color

class XButton(IconButton): pass