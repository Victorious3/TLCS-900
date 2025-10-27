import math

from typing import cast
from functools import cache
from dataclasses import dataclass

from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.uix.widget import Widget
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.graphics import Color, Line, StencilPush, StencilPop, StencilUse, StencilUnUse, Rectangle
from kivy.clock import Clock

def clear_cache():
    ArrowRenderer.get_offset.cache_clear()

from . import main
from .kivytypes import KWidget
from .project import Section, CodeSection, get_jump_location
from .main import LABEL_HEIGHT, app, FONT_HEIGHT
from disapi import Loc

MAX_OFFSET = 15
COLORS =  [get_color_from_hex("#80FFCC"), 
           get_color_from_hex("#A080FF"), 
           get_color_from_hex("#FFB380"), 
           get_color_from_hex("#809FFF"), 
           get_color_from_hex("#FF80F0"), 
           get_color_from_hex("#8CFF80"),
           get_color_from_hex("#FFE080"),
           get_color_from_hex("#FF8080"),
           get_color_from_hex("#80FFFF"),
           get_color_from_hex("#D580FF"),
           get_color_from_hex("#80CCFF"),
           get_color_from_hex("#F0FF80"),
           get_color_from_hex("#80FF9F"),
           get_color_from_hex("#808CFF"),
           get_color_from_hex("#BFFF80"),
           get_color_from_hex("#FF80B3")]

# TODO This doesn't seem to work reliably
#def DashedLine(points, dash_length = dp(5), dash_offset = dp(2), width = dp(1)):
#    Line(points=points, dash_length=dash_length, dash_offset=dash_offset, width=width)

def DashedLine(points, dash_length = dp(5), dash_offset = dp(5), width = dp(1)):
    for i in range(0, len(points) - 2, 2):
        x1, y1 = points[i], points[i + 1]
        x2, y2 = points[i + 2], points[i + 3]

        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        steps = int(dist // (dash_length + dash_offset))
        if dist == 0:
            continue

        for j in range(steps + 1):
            start_ratio = ((dash_length + dash_offset) * j) / dist
            end_ratio = ((dash_length + dash_offset) * j + dash_length) / dist
            if end_ratio > 1:
                end_ratio = 1
            sx = x1 + dx * start_ratio
            sy = y1 + dy * start_ratio
            ex = x1 + dx * end_ratio
            ey = y1 + dy * end_ratio
            Line(points=[sx, sy, ex, ey], width=width)

@dataclass
class Arrow:
    start: int
    end: int
    direction: bool
    tips: list[int]
    cond: bool

    def __hash__(self):
        return id(self)
    
    def __str__(self):
        return f"{self.start:X} -> {self.end:X}"

class ArrowRenderer(KWidget, Widget):
    parent: "main.MainPanel"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().arrows = self

        self.arrows: list[Arrow] = []
        self.arrow_offsets = {}

    def on_kv_post(self, base_widget):
        self.recompute_arrows()
        Clock.schedule_once(lambda dt: self.redraw(), 0)

    def recompute_arrows(self):
        arrows : list[Arrow] = []
        for section in self.parent.get_sections():
            if not isinstance(section, CodeSection): continue
            for insn in section.instructions:
                location = get_jump_location(insn)
                
                cond = False
                if (insn.entry.opcode == "JR" or insn.entry.opcode == "JRL" or 
                    (insn.entry.opcode == "JP" and len(insn.entry.instructions) == 2)):
                    cc = insn.entry.instructions[0]
                    if cc != "T": cond = True
                    elif cc == "F": continue
                elif insn.entry.opcode == "DJNZ": 
                    cond = True

                if not location: continue
                arrows.append(Arrow(min(insn.entry.pc, location.loc), max(insn.entry.pc, location.loc), insn.entry.pc < location.loc, [], cond))

        arrows = sorted(arrows, key = lambda x: x.start)
        
        arrows2: list[Arrow] = []
        active_arrows: list[Arrow] = []
        for a1 in arrows:
            active_arrows = list(filter(lambda a: a.end >= a1.start, active_arrows))

            for a in active_arrows:
                if a.cond == a1.cond:
                    if a.end == a1.end and a.direction == a1.direction == True:
                        a.tips.append(a1.start)
                        a.start = min(a1.start, a.start)
                        break
                    elif a.start == a1.start and a.direction == a1.direction == False:
                        a.tips.append(a1.end)
                        a.end = max(a1.end, a.end)
                        break
            else:
                arrows2.append(a1)
                
            active_arrows.append(a1)

        arrows = arrows2

        arrow_offsets: dict[Arrow, int] = {}
        active_arrows = []
        for a1 in arrows:
            l = len(active_arrows)
            #if l > 0:
            #    mn = active_arrows[-1].end
            #else: mn = 0
            mn = a1.start
            
            filtered = []
            width = 0
            i = l - 1
            while i >= 0:
                cur = active_arrows[i]
                w = arrow_offsets.get(cur, 0)
                if cur.end >= mn:
                    if w >= width:
                        filtered.append(cur) 
                        width = w

                    mn = min(mn, cur.start)
                i -= 1

            active_arrows = list(reversed(filtered))
            active_offsets = set(map(lambda x: arrow_offsets.get(x, 0), active_arrows))
            max_offset = max(active_offsets, default = 0)

            last_offset = arrow_offsets.get(active_arrows[-1], 0) if len(active_arrows) > 0 else 0
            if last_offset == 0:
                for a in reversed(active_arrows):
                    next = arrow_offsets.get(a, 0)
                    if next + 1 > MAX_OFFSET:
                        arrow_offsets[a] = -1
                        break

                    if next < 0: continue
                    if next + 1 not in active_offsets and next <= max_offset:
                        arrow_offsets[a] = next + 1
                        break

                    arrow_offsets[a] = next + 1
                    active_offsets.add(next + 1)
            
            arrow_offsets[a1] = 0
            active_arrows.append(a1)
            
        self.arrows = list(arrows)
        self.arrow_offsets = arrow_offsets

    @cache
    def get_offset(self, pc: int):
        offset = 0
        for data in self.parent.rv.data:
            section: Section = data["section"]
            if section.offset <= pc < section.length + section.offset:
                if section.labels: 
                    offset += LABEL_HEIGHT
                for i in section.instructions:
                    if i.entry.pc <= pc < i.entry.pc + i.entry.length:
                        return offset
                    offset += FONT_HEIGHT

            offset += data["height"]
        return offset

    def redraw(self):
        rv = self.parent.rv
        layout_manager = cast(RecycleBoxLayout, rv.layout_manager)
        vstart, vend = rv.get_visible_range()

        if len(layout_manager.children) == 0: return

        start_index = min(layout_manager.get_view_index_at((0, vstart)) + 1, len(rv.data) - 1)
        end_index = max(layout_manager.get_view_index_at((0, vend)) - 1, 0)

        vstart = rv.children[0].height - vstart
        vend = rv.children[0].height - vend

        first: Section = rv.data[end_index]["section"]
        last: Section = rv.data[start_index]["section"]

        self.canvas.after.clear()

        with self.canvas.after:
            StencilPush()
            Rectangle(pos=self.pos, size=self.size)
            StencilUse()

            arrows_to_render: list[Arrow] = []
            for arrow in self.arrows:
                if arrow.start > first.length + last.offset: continue
                if arrow.end < first.offset: continue
                arrows_to_render.append(arrow)
        
            def calc_offset(x):
                e = self.height - self.get_offset(x) + (vstart - self.height)
                return e - LABEL_HEIGHT / 2

            for a in arrows_to_render:
                y_start = calc_offset(a.start)
                y_end = calc_offset(a.end)

                w = self.arrow_offsets.get(a, 0)
                if a.cond: line = DashedLine
                else: line = Line

                tip_length = dp(5)

                right = self.right + rv.xoffset
                
                if w < 0:
                    Color(*COLORS[15])
                    offset = (MAX_OFFSET + 1) * dp(8)
                    if a.direction:
                        def render(y): 
                            line(points=[right, y, 
                                 right - offset - tip_length, y,
                                 right - offset - tip_length, y - LABEL_HEIGHT / 2], width=dp(1))
                            
                            Line(points=[right - offset - 0, y - LABEL_HEIGHT / 2 + tip_length, 
                                         right - offset - tip_length, y - LABEL_HEIGHT / 2,
                                         right - offset - 2*tip_length, y - LABEL_HEIGHT / 2 + tip_length], width=dp(1))
                            
                        render(y_start)
                        for tip in a.tips:
                            render(calc_offset(tip))
                        
                    else:
                        def render(y):
                            line(points=[right, y, 
                                        right - offset - tip_length, y,
                                        right - offset - tip_length, y + LABEL_HEIGHT / 2], width=dp(1))
                            
                            Line(points=[right - offset - 0, y + LABEL_HEIGHT / 2 - tip_length, 
                                        right - offset - tip_length, y + LABEL_HEIGHT / 2,
                                        right - offset - 2*tip_length, y + LABEL_HEIGHT / 2 - tip_length], width=dp(1))
                        render(y_end)
                        for tip in a.tips:
                            render(calc_offset(tip))

                    continue
                
                Color(*COLORS[w])
                left = right - w*dp(8) - dp(15)
                
                line(points=[right, y_start, 
                             left, y_start, 
                             left, y_end,
                             right, y_end], width=dp(1))
                
                for tip in a.tips:
                    o = calc_offset(tip)
                    line(points=[right, o, 
                                 left, o], width=dp(1))
                
                if not a.direction:
                    Line(points=[right - tip_length, y_start - tip_length,
                                 right, y_start,
                                 right - tip_length, y_start + tip_length], width=dp(1))
                    
                    if y_start > self.height and y_end < self.height:
                        Line(points=[left - tip_length, self.height - tip_length,
                                     left, self.height,
                                     left + tip_length, self.height - tip_length], width=dp(1))
                else:
                    Line(points=[right - tip_length, y_end - tip_length,
                                 right, y_end,
                                 right - tip_length, y_end + tip_length], width=dp(1))
                    
                    if y_end < 0 and y_start > 0:
                        Line(points=[left - tip_length, tip_length,
                                     left, 0,
                                     left + tip_length, tip_length], width=dp(1))
            StencilUnUse()
            StencilPop()
                            