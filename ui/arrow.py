import math

from functools import cache
from dataclasses import dataclass

from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line

from .project import Section, CodeSection
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

def DashedLine(points, dash_length = dp(5), space_length = dp(2), width = dp(1)):
    space_length *= width
    for i in range(0, len(points) - 2, 2):
        x1, y1 = points[i], points[i + 1]
        x2, y2 = points[i + 2], points[i + 3]

        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx**2 + dy**2)
        if length == 0: continue

        total_dash = dash_length + space_length
        unit_dx = dx / length
        unit_dy = dy / length

        dist_covered = 0
        while dist_covered < length:
            start_x = x1 + unit_dx * dist_covered
            start_y = y1 + unit_dy * dist_covered

            dash_end = min(dash_length, length - dist_covered)
            end_x = start_x + unit_dx * dash_end
            end_y = start_y + unit_dy * dash_end

            Line(points=[start_x, start_y, end_x, end_y], width=width)
            dist_covered += dash_length + space_length

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

class ArrowRenderer(Widget):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().arrows = self

        self.arrows: list[tuple[int, int]] = []
        self.arrow_offsets = {}

        self.recompute_arrows()

    def recompute_arrows(self):
        arrows = []
        for section in app().project.sections:
            if not isinstance(section, CodeSection): continue
            for insn in section.instructions:
                location: Loc = None
                cond = False
                if insn.entry.opcode == "JP":
                    if len(insn.entry.instructions) == 1:
                        location = insn.entry.instructions[0]
                elif insn.entry.opcode == "JR" or insn.entry.opcode == "JRL":
                    cc = insn.entry.instructions[0]
                    if cc != "T": cond = True
                    elif cc == "F": continue
                    location = insn.entry.instructions[1]

                if not location: continue
                arrows.append(Arrow(min(insn.entry.pc, location.loc), max(insn.entry.pc, location.loc), insn.entry.pc < location.loc, [], cond))

        arrows = sorted(arrows, key = lambda x: x.start)
        
        arrows2 = []
        active_arrows: list = []
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

        arrow_offsets = {}
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

    def redraw(self):
        rv = app().rv
        layout_manager = rv.layout_manager
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
            @cache
            def get_offset(pc):
                offset = 0
                for data in rv.data:
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

            arrows_to_render = []
            for arrow in self.arrows:
                if arrow.start > first.length + last.offset: continue
                if arrow.end < first.offset: continue
                arrows_to_render.append(arrow)
        
            def calc_offset(x):
                e = self.height - get_offset(x) + (vstart - self.height)
                return e - LABEL_HEIGHT / 2

            for a in arrows_to_render:
                y_start = calc_offset(a.start)
                y_end = calc_offset(a.end)

                w = self.arrow_offsets.get(a, 0)
                if a.cond: line = DashedLine
                else: line = Line

                tip_length = dp(5)
                
                if w < 0:
                    Color(*COLORS[15])
                    offset = (MAX_OFFSET + 1) * dp(8)
                    if a.direction:
                        def render(y): 
                            line(points=[self.right, y, 
                                 self.right - offset - tip_length, y,
                                 self.right - offset - tip_length, y - LABEL_HEIGHT / 2], width=dp(1))
                            
                            Line(points=[self.right - offset - 0, y - LABEL_HEIGHT / 2 + tip_length, 
                                         self.right - offset - tip_length, y - LABEL_HEIGHT / 2,
                                         self.right - offset - 2*tip_length, y - LABEL_HEIGHT / 2 + tip_length], width=dp(1))
                            
                        render(y_start)
                        for tip in a.tips:
                            render(calc_offset(tip))
                        
                    else:
                        def render(y):
                            line(points=[self.right, y, 
                                        self.right - offset - tip_length, y,
                                        self.right - offset - tip_length, y + LABEL_HEIGHT / 2], width=dp(1))
                            
                            Line(points=[self.right - offset - 0, y + LABEL_HEIGHT / 2 - tip_length, 
                                        self.right - offset - tip_length, y + LABEL_HEIGHT / 2,
                                        self.right - offset - 2*tip_length, y + LABEL_HEIGHT / 2 - tip_length], width=dp(1))
                        render(y_end)
                        for tip in a.tips:
                            render(calc_offset(tip))

                    continue
                
                Color(*COLORS[w])
                left = self.right - w*dp(8) - dp(15)
                
                line(points=[self.right, y_start, 
                             left, y_start, 
                             left, y_end,
                             self.right, y_end], width=dp(1))
                
                for tip in a.tips:
                    o = calc_offset(tip)
                    line(points=[self.right, o, 
                                 left, o], width=dp(1))
                
                if not a.direction:
                    Line(points=[self.right - tip_length, y_start - tip_length,
                                 self.right, y_start,
                                 self.right - tip_length, y_start + tip_length], width=dp(1))
                    
                    if y_start > self.height and y_end < self.height:
                        Line(points=[left - tip_length, self.height - tip_length,
                                     left, self.height,
                                     left + tip_length, self.height - tip_length], width=dp(1))
                else:
                    Line(points=[self.right - tip_length, y_end - tip_length,
                                 self.right, y_end,
                                 self.right - tip_length, y_end + tip_length], width=dp(1))
                    
                    if y_end < 0 and y_start > 0:
                        Line(points=[left - tip_length, tip_length,
                                     left, 0,
                                     left + tip_length, tip_length], width=dp(1))
                            