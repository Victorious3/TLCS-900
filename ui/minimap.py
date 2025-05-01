import math
from itertools import groupby

from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.utils import get_color_from_hex

from .main import app, FONT_HEIGHT, LABEL_HEIGHT, DATA_PER_ROW
from .project import DataSection, CodeSection

class Minimap(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().minimap = self

        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *args):        
        sections = app().project.sections
        if not app().rv: return
        total_height = app().rv.children[0].height
        if total_height == 0: return

        def cs_height(section: CodeSection): 
            return len(section.instructions) * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)
        def ds_height(section: DataSection): 
            return math.ceil(section.length / DATA_PER_ROW) * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)

        self.canvas.after.clear()
        with self.canvas.after:
            offset = 0
            Color(*get_color_from_hex("#66BB6A"))
            for key, group in groupby(sections, key=type):
                group = list(group)
                if key == DataSection:
                    height = sum(map(ds_height, group))
                else:
                    height = sum(map(cs_height, group))
                    Rectangle(pos=(self.x, self.y + (1 - (offset / total_height)) * self.height), size=(self.width, height / total_height * self.height))

                offset += height