from dataclasses import dataclass
import math
from itertools import groupby

from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.utils import get_color_from_hex
from kivy.clock import Clock
from kivy.metrics import dp

from . import main
from .kivytypes import KWidget
from .main import app, FONT_HEIGHT, LABEL_HEIGHT, BG_COLOR
from .project import Section, CodeSection

@dataclass
class CacheEntry:
    y: float
    height: float

class Minimap(KWidget, Widget):
    parent: "main.ListingPanel"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.cache: list[list[CacheEntry]] = [[], []]
        self.bind(pos=self.redraw, size=self.redraw)

    def on_kv_post(self, base_widget):
        Clock.schedule_once(lambda dt: self.update(), 0)

    @staticmethod
    def section_height(section: Section): 
        return len(section.instructions) * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)

    def update(self):
        self.cache[0].clear()
        self.cache[1].clear()

        sections = self.parent.get_sections()
        if not self.parent.rv: return
        
        if self.parent.highlighted is not None:
            highlighted_set = self.parent.highlighted_set

        offset = 0
        for key, group in groupby(sections, key=type):
            group = list(group)
            height = sum(map(self.section_height, group))
            if key == CodeSection and not isinstance(self.parent, main.FunctionListing):
                self.cache[0].append(CacheEntry(y=offset, height=height))

            if self.parent.highlighted is not None:
                offset_in_group = 0
                for section in group:
                    for insn in section.instructions:
                        if insn.entry.pc in highlighted_set:
                            self.cache[1].append(CacheEntry(y=offset + offset_in_group, height=FONT_HEIGHT))
                        offset_in_group += FONT_HEIGHT

            offset += height

        self.redraw()

    def redraw(self, *args):
        if not self.parent.rv: return
        total_height = self.parent.rv.children[0].height
        if total_height == 0: return

        self.canvas.after.clear()
        with self.canvas.after:
            Color(*BG_COLOR)
            Rectangle(pos=(self.x, self.y), size=(self.width, self.height))
            
            def draw(entries: list[CacheEntry]):
                y = 0
                for entry in entries:
                    new_y = int(self.y + (1 - ((entry.y + entry.height) / total_height)) * self.height)
                    if new_y == y: continue
                    y = new_y

                    height = (entry.height / total_height) * self.height
                    Rectangle(pos=(self.x, y), size=(self.width, max(height, dp(1))))

            Color(*get_color_from_hex("#66BB6A"))
            draw(self.cache[0])
            Color(*get_color_from_hex("#EF5350"))
            draw(self.cache[1])


