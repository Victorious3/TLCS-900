import math
from itertools import groupby

from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.utils import get_color_from_hex
from kivy.clock import Clock

from . import main
from .types import KWidget
from .main import app, FONT_HEIGHT, LABEL_HEIGHT, BG_COLOR
from .project import Section, CodeSection

class Minimap(KWidget, Widget):
    parent: "main.MainPanel"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.bind(pos=self.redraw, size=self.redraw)

    def on_kv_post(self, base_widget):
        Clock.schedule_once(lambda dt: self.redraw(), 0)

    def redraw(self, *args):        
        sections = app().project.sections.values()
        if not self.parent.rv: return
        total_height = self.parent.rv.children[0].height
        if total_height == 0: return

        def section_height(section: Section): 
            return len(section.instructions) * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)
        
        self.canvas.after.clear()
        with self.canvas.after:
            Color(*BG_COLOR)
            Rectangle(pos=(self.x, self.y), size=(self.width, self.height))
            offset = 0
            Color(*get_color_from_hex("#66BB6A"))
            for key, group in groupby(sections, key=type):
                group = list(group)
                height = sum(map(section_height, group))
                if key == CodeSection:
                    Rectangle(pos=(self.x, self.y + (1 - ((offset + height) / total_height)) * self.height), size=(self.width, height / total_height * self.height))

                offset += height