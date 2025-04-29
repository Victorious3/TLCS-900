import math, time
from itertools import groupby, combinations
from functools import cache

from kivy.app import App
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.graphics.context_instructions import Translate
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import get_color_from_hex
from kivy.graphics.texture import Texture

from .project import Section, CodeSection, DataSection, DATA_PER_ROW, MAX_SECTION_LENGTH, Project, load_project
from disapi import Loc

FONT_SIZE = dp(15)
LABEL_HEIGHT = FONT_SIZE + dp(4)
FONT_NAME = "ui/FiraMono"

def find_font_height():
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = FONT_SIZE
    )
    label.texture_update()
    return label.texture_size

FONT_WDI, FONT_HEIGHT = find_font_height()

class MainWindow(FloatLayout): pass

class DisLabel(Label):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = None, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
        self.texture_update()
        self.size = self.texture_size

class LocationLabel(DisLabel):
    hover_labels = []
    any_hovared = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.original_color = self.color
        self.ctrl_down = False
        self.hovered = False

        LocationLabel.hover_labels.append(self)

        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
        Window.bind(on_mouse_up=self._on_mouse_up)
        Window.bind(on_mouse_move=self._on_mouse_move)
                

    @classmethod
    def on_mouse_move(cls, window, pos):
        cls.any_hovered = False
        label: LocationLabel
        for label in cls.hover_labels:
            if not label.get_root_window():
                label.hovered = False
                continue

            if label.collide_point(*label.to_widget(*pos)):
                label.hovered = True
                cls.any_hovered = True
            else:
                label.hovered = False
                
            label._on_update()

        cls.update_cursor()
        
    @classmethod
    def update_cursor(cls):
        if cls.any_hovered and app().ctrl_down:
            Window.set_system_cursor('hand')
        else:
            Window.set_system_cursor('arrow')

    def _on_mouse_move(self, window, x, y, modifiers):
        self.hovered = False
        if not self.get_root_window():
            return

        if self.collide_point(*self.to_widget(x, y)):
            self.hovered = True
            LocationLabel.any_hovered = True
        else:
            self.hovered = False
            
        self._on_update()

    def _on_mouse_up(self, window, x: int, y: int, button: str, modifiers):
        if self.hovered and self.ctrl_down and button == 'left':
            try:
                app().scroll_to_label(self.text)
            except ValueError: pass

    def _on_update(self):
        self.canvas.before.clear()

        if self.hovered and self.ctrl_down:
            color = get_color_from_hex("#64B5F6")
            self.color = color
            
            with self.canvas.before:
                Color(*color)
                Line(points=[
                    self.x, self.y + 1,
                    self.right, self.y + 1
                ], width=1)

        else: self.color = self.original_color

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if keycode == 224: 
            self.ctrl_down = True
            self._on_update()
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 224: 
            self.ctrl_down = False
            self._on_update()
        

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

        def cs_height(section): return len(section.instructions) * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)
        def ds_height(section): return math.ceil(section.length / DATA_PER_ROW) * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)

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

def partition(pred, iterable):
    matches = []
    nones  = []
    for item in iterable:
        (matches if pred(item) else nones).append(item)
    return matches, nones

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
                if insn.entry.opcode == "JP":
                    if len(insn.entry.instructions) == 1:
                        location = insn.entry.instructions[0]
                elif insn.entry.opcode == "JR":
                    location = insn.entry.instructions[1]

                if not location: continue
                arrows.append((min(insn.entry.pc, location.loc), max(insn.entry.pc, location.loc), insn.entry.pc < location.loc))

        arrows = sorted(arrows, key = lambda x: x[0])

        arrow_offsets = {}
        active_arrows = []
        for a1 in arrows:
            l = len(active_arrows)
            if l > 0:
                mn = active_arrows[-1][1]
            else: mn = 0

            #if a1[0] == 0xF2BAA2: print(list(map(lambda a: hex(a[0]) + " -> " + hex(a[1]) + " " + str(arrow_offsets.get(a, 0)), active_arrows)))
            
            filtered = []
            width = 0
            i = l - 1
            while i >= 0:
                cur = active_arrows[i]
                w = arrow_offsets.get(cur, 0)
                if cur[1] >= mn:
                    if w >= width:
                        filtered.append(cur) 
                        width = w

                    mn = min(mn, cur[0])
                i -= 1

            active_arrows = list(reversed(filtered))

            merge = False
            for a in active_arrows:
                if (a[0] == a1[0] and a[2] == a[2] == False or
                    a[1] == a1[1] and a[2] == a[2] == True):
                        arrow_offsets[a1] = arrow_offsets.get(a, 0)
                        merge = True
                        break
            
            if not merge:
                for a in active_arrows:
                    next = arrow_offsets.get(a, 0) + 1
                    if next > MAX_OFFSET:
                        arrow_offsets[a] = -1
                    else: arrow_offsets[a] = next
                
                arrow_offsets[a1] = 0
                
            active_arrows.append(a1)
            
        self.arrows = list(arrows)
        self.arrow_offsets = arrow_offsets

    def redraw(self):
        rv = app().rv
        layout_manager = rv.layout_manager
        vstart, vend = rv.get_visible_range()

        if len(layout_manager.children) == 0: return

        start_index = layout_manager.get_view_index_at((0, vstart))
        end_index = layout_manager.get_view_index_at((0, vend))

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
                        if isinstance(section, CodeSection):
                            for i in section.instructions:
                                if i.entry.pc <= pc < i.entry.pc + i.entry.length:
                                    return offset
                                offset += FONT_HEIGHT
                        elif isinstance(section, DataSection):
                            offset += math.ceil((pc - section.offset) / DATA_PER_ROW) * FONT_HEIGHT
                            return offset

                    offset += data["height"]
                return offset

            arrows_to_render = []
            for arrow in self.arrows:
                if arrow[0] > first.length + last.offset: continue
                if arrow[1] < first.offset: continue
                arrows_to_render.append(arrow)
        
            for a in arrows_to_render:
                y_start = self.height - get_offset(a[0]) + (vstart - self.height)
                y_end = self.height - get_offset(a[1]) + (vstart - self.height)

                y_start = max(-50, min(self.height + 50, y_start)) - LABEL_HEIGHT / 2
                y_end = max(-500, min(self.height + 50, y_end)) - LABEL_HEIGHT / 2

                w = self.arrow_offsets.get(a, 0) - 1
                
                if w < 0:
                    Color(*COLORS[15])
                    offset = (MAX_OFFSET + 1) * 8
                    if a[2]:
                        Line(points=[self.right, y_start, 
                                     self.right - offset - 5, y_start,
                                     self.right - offset - 5, y_start - LABEL_HEIGHT / 2])
                        
                        Line(points=[self.right - offset - 0, y_start - LABEL_HEIGHT / 2 + 5, 
                                     self.right - offset - 5, y_start - LABEL_HEIGHT / 2,
                                     self.right - offset - 10, y_start - LABEL_HEIGHT / 2 + 5])
                    else:
                        Line(points=[self.right, y_end, 
                                     self.right - offset - 5, y_end,
                                     self.right - offset - 5, y_end + LABEL_HEIGHT / 2])
                        
                        Line(points=[self.right - offset - 0, y_end + LABEL_HEIGHT / 2 - 5, 
                                     self.right - offset - 5, y_end + LABEL_HEIGHT / 2,
                                     self.right - offset - 10, y_end + LABEL_HEIGHT / 2 - 5])
                    continue
                
                Color(*COLORS[w])
                left = self.right - w*8 - 15
                
                Line(points=[self.right, y_start, 
                             left, y_start, 
                             left, y_end,
                             self.right, y_end])
                
                if not a[2]:
                    Line(points=[self.right - 5, y_start - 5,
                                 self.right, y_start,
                                 self.right - 5, y_start + 5])
                    
                    if y_start > self.height and y_end < self.height:
                        Line(points=[left - 5, self.height - 5,
                                     left, self.height,
                                     left + 5, self.height - 5])
                else:
                    Line(points=[self.right - 5, y_end - 5,
                                 self.right, y_end,
                                 self.right - 5, y_end + 5])
                    
                    if y_end < 0 and y_start > 9:
                        Line(points=[left - 5, 5,
                                     left, 0,
                                     left + 5, 5])
                            


class LabelRow(TextInput):
    def __init__(self, section: Section, label: str, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = 1, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
        self.height = LABEL_HEIGHT
        self.section = section
        self.background_color = 0, 0, 0, 0
        self.foreground_color = 1, 1, 1, 1
        self.text = label
        self.padding = [dp(100), 0, 0, 0]

class SectionColumn(Label):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = None, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME

    def resize(self):
        self.texture_update()
        self.height = self.texture_size[1]
        self.text_size = self.size

class SectionAddresses(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(**kwargs)
        self.width = dp(240)
        self.section = section
        self.halign = "right"

        if isinstance(section, CodeSection):
            self.text = "\n".join(format(x, "X") + ":" for x in map(lambda i: i.entry.pc, section.instructions))
        elif isinstance(section, DataSection):
            self.text = "\n".join(format(x + section.offset, "X") + ":" for x in range(0, section.length, DATA_PER_ROW))

        self.resize()

class SectionData(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(**kwargs)
        self.width = DATA_PER_ROW * dp(40)
        self.section = section
        self.halign = "left"
        self.padding = [dp(30), 0, 0, 0]

        lines = []
        if isinstance(section, CodeSection):
            for insn in section.instructions:
                data = section.data[
                    insn.entry.pc - section.offset :
                    insn.entry.pc + insn.entry.length - section.offset]
                lines.append(" ".join(format(x, "0>2X") for x in data))
        elif isinstance(section, DataSection):
            i = 0
            while i < section.length:
                next = min(i + DATA_PER_ROW, section.length)
                data = section.data[i:next]
                lines.append(" ".join(format(x, "0>2X") for x in data))

                i += DATA_PER_ROW

        self.text = "\n".join(lines)
        self.resize()


def loc_to_str(insn: Loc):
    ob = app().project.ob
    label = ob.label(insn.loc)
    if label is not None:
        return str(label)
    return str(insn.loc)

class SectionMnemonic(BoxLayout):
    def __init__(self, section: Section, **kwargs):
        super().__init__(**kwargs)
        self.section = section
        self.width = dp(200)
        self.size_hint = None, 1
        self.orientation = "vertical"
        
        if isinstance(section, CodeSection):
            for insn in section.instructions:
                row = BoxLayout(orientation = "horizontal")
                row.add_widget(DisLabel(text = insn.entry.opcode + " "))
                for i in range(len(insn.entry.instructions)):
                    param = insn.entry.instructions[i]
                    if isinstance(param, Loc):
                        row.add_widget(LocationLabel(text = loc_to_str(param)))
                    else:
                        row.add_widget(DisLabel(text = str(param)))
                    if i < len(insn.entry.instructions) - 1:
                        row.add_widget(DisLabel(text = ", "))

                self.add_widget(row)

        elif isinstance(section, DataSection):
            lines = []
            i = 0
            while i < section.length:
                next = min(i + DATA_PER_ROW, section.length)
                data = section.data[i:next].copy()
                res = data.decode("ascii", "replace")
                res = "".join(x if 0x6F > ord(x) > 0x20 else "." for x in res)

                lines.append(f'.db "{res}"')

                i += DATA_PER_ROW
            
            for line in lines:
                self.add_widget(DisLabel(text = line))
        

class SectionPanel(BoxLayout, RecycleDataViewBehavior):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scheduled_update = None
        self.section: Section = None

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)

        section: Section = data["section"]
        self.section = section

        def update(dt):
            if not self.is_visible(): 
                self.canvas.clear()
                return

            self.clear_widgets()
            for label in section.labels:
                self.add_widget(LabelRow(section, label.name))

            rows = BoxLayout(orientation = "horizontal", size_hint=(None, 1))
            rows.add_widget(SectionAddresses(section))
            rows.add_widget(SectionData(section))
            rows.add_widget(SectionMnemonic(section))

            self.add_widget(rows)
        
        if self.scheduled_update:
            self.scheduled_update.cancel()
        self.scheduled_update = Clock.schedule_once(update, 0.05)

    def is_visible(self):
        visible_range = app().rv.get_visible_range()   
        window = MAX_SECTION_LENGTH * FONT_HEIGHT     
        return self.y + self.height >= visible_range[0] - window and self.y <= visible_range[1] + window

class GotoPosition(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().goto_position = self

    def _key_down(self, key, repeat=False):
        if key[2] == "enter":
            try:
                offset = int(self.text, base=16)
                try:
                    app().scroll_to_offset(offset)
                except ValueError: return
            except ValueError:
                try:
                    app().scroll_to_label(self.text)
                except ValueError: return

            
            self.hide()
            return
        
        super()._key_down(key, repeat)
    
    def hide(self):
        self.opacity = 0
        self.disabled = True
        self.text = ""

class Keyboard(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_key_down=self._keydown)

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if "ctrl" in modifiers and keycode == 10: # ctrl + g
            app().goto_position.disabled = False
            app().goto_position.opacity = 1
            app().goto_position.focus = True

class RV(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().rv = self

        project: Project = app().project

        data = []
        for section in project.sections:
            if isinstance(section, DataSection):
                columns = math.ceil(section.length / DATA_PER_ROW)
            elif isinstance(section, CodeSection):
                columns = len(section.instructions)

            data.append({"section": section, 
                         "height": columns * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0),
                         "width": dp(1500) })

        self.data = data

    def update_from_scroll(self, *largs):
        super().update_from_scroll(*largs)
        app().arrows.redraw()

    def get_visible_range(self):
        content_height = self.children[0].height - self.height
        scroll_pos = self.scroll_y * content_height

        return scroll_pos, scroll_pos + self.height

class DisApp(App):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        
        self.goto_position: GotoPosition = None
        self.rv: RV = None
        self.minimap: Minimap = None
        self.arrows: ArrowRenderer = None

        self.ctrl_down = False

        Window.bind(mouse_pos=LocationLabel.on_mouse_move)
        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
    
    def build(self):
        Window.clearcolor = get_color_from_hex("#1F1F1F")

        window = MainWindow()
        return window
    
    def after_layout_is_ready(self, dt):
        self.minimap.redraw()
        self.arrows.redraw()

    def on_start(self):
        super().on_start()
        Clock.schedule_once(self.after_layout_is_ready, 0)
    
    def scroll_to_label(self, label: str):
        for section in self.project.sections:
            if section.labels and section.labels[0].name == label:
                print("Goto label:", label, "at", hex(section.offset))
                self.scroll_to_offset(section.offset)
                return
        raise ValueError("Invalid label")
    
    def scroll_to_offset(self, offset: int):
        scroll_pos = 0
        for i in range(len(self.rv.data)):
            total_height = self.rv.children[0].height - self.rv.height
            data = self.rv.data[i]
            section: Section = data["section"]
            if section.offset <= offset < section.offset + section.length:
                if section.labels: scroll_pos += LABEL_HEIGHT
                if isinstance(section, DataSection):
                    scroll_pos += math.ceil((offset - section.offset) / DATA_PER_ROW) * FONT_HEIGHT
                elif isinstance(section, CodeSection):
                    for insn in section.instructions:
                        if offset > insn.entry.pc: scroll_pos += FONT_HEIGHT
                        else: break
                

                self.rv.scroll_y = 1 - (scroll_pos / total_height)
                return

            scroll_pos += data["height"]
        raise ValueError("Invalid location")

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if keycode == 224: 
            self.ctrl_down = True
            LocationLabel.update_cursor()
        elif keycode == 41: 
            self.goto_position.hide()
            return True
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 224: 
            self.ctrl_down = False
            LocationLabel.update_cursor()
        elif keycode == 41:
            return True

def app() -> DisApp:
    return App.get_running_app()

def main(path: str, ep: int, org: int):
    project = load_project(path, ep, org)

    window = DisApp(project)
    window.run()