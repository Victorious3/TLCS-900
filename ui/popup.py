from kivy.uix.popup import Popup
from kivy.properties import NumericProperty, StringProperty

from .types import KWidget

class InvalidInsnPopup(KWidget, Popup):
    instruction = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_continue")
        self.register_event_type("on_close")

    def on_continue(self, *args):
        pass

    def on_close(self, *args):
        pass

class FunctionAnalyzerPopup(KWidget, Popup):
    max = NumericProperty(0)
    value = NumericProperty(0)
    current = StringProperty("")