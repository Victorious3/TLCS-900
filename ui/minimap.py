import math
from itertools import groupby

from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.utils import get_color_from_hex

from .main import app, FONT_HEIGHT, LABEL_HEIGHT, BG_COLOR, KWidget
from .project import Section, CodeSection

class Minimap(KWidget, Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().minimap = self

        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):        
        sections = app().project.sections.values()
        if not app().rv: return
        total_height = app().rv.children[0].height
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
                    Rectangle(pos=(self.x, self.y + (1 - (offset / total_height)) * self.height), size=(self.width, height / total_height * self.height))

                offset += height