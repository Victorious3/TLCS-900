import math, weakref
from itertools import groupby

from kivy.app import App
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import get_color_from_hex, escape_markup
from kivy.core.text import Label as CoreLabel
from kivy.effects.scroll import ScrollEffect
from kivy.effects.dampedscroll import DampedScrollEffect

FONT_SIZE = dp(15)
LABEL_HEIGHT = FONT_SIZE + dp(5)
FONT_NAME = "ui/FiraMono"
BG_COLOR = get_color_from_hex("#1F1F1F")

def app() -> "DisApp":
    return App.get_running_app()

def find_font_height():
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = FONT_SIZE
    )
    label.texture_update()
    return label.texture_size

FONT_WIDTH, FONT_HEIGHT = find_font_height()

from .project import Section, CodeSection, DataSection, DATA_PER_ROW, MAX_SECTION_LENGTH, Project, load_project
from .arrow import ArrowRenderer
from .minimap import Minimap
from disapi import Loc

class MainWindow(FloatLayout): pass

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
        self.multiline = False

class SectionColumn(Label):
    selection_start = 0
    selection_end = 0

    def __init__(self, section: Section, **kwargs):
        super().__init__(**kwargs)
        self.section = section
        self.size_hint = None, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
        self.__class__.objects.add(self)

    def resize(self):
        self.texture_update()
        self.height = self.texture_size[1]
        self.text_size = self.size

    def on_touch_down(self, touch):
        return
    
    def __init_subclass__(cls):
        cls.objects: set[SectionColumn] = weakref.WeakSet()

    def calculate_selection(pos: tuple[int, int]):
        for panel in SectionData.objects:
            x, y = panel.to_window(panel.x, panel.y)
            if y <= pos[1] <= y + panel.height:
                section = panel.section
                y1 = y - pos[1]
                rows = len(section.instructions)
                row = math.floor(rows + y1 / FONT_HEIGHT)
                offset = section.instructions[row].entry.pc

                return offset
                
        return -1

    @classmethod
    def on_touch_move_section(cls, window, pos):
        end = cls.calculate_selection((pos.x, pos.y))
        if end > 0: cls.selection_end = end
        print(format(cls.selection_end, "X"))
    
    @classmethod
    def on_mouse_down(cls, window, x, y, button, modifiers):
        selection_end = cls.calculate_selection((x, y))
        cls.selection_end = selection_end
        cls.selection_start = selection_end

class SectionAddresses(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(section, **kwargs)
        self.width = dp(240)
        self.halign = "right"
        self.text = "\n".join(format(x, "X") for x in map(lambda i: i.entry.pc, section.instructions))
        self.resize()

class SectionData(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(section, **kwargs)
        self.width = DATA_PER_ROW * dp(40)
        self.halign = "left"
        self.padding = [dp(30), 0, 0, 0]
        self.color = get_color_from_hex("#B5CEA8")

        lines = []
        for insn in section.instructions:
            data = section.data[
                insn.entry.pc - section.offset :
                insn.entry.pc + insn.entry.length - section.offset]
            lines.append(" ".join(format(x, "0>2X") for x in data))

        self.text = "\n".join(lines)
        self.resize()


def loc_to_str(insn: Loc):
    ob = app().project.ob
    label = ob.label(insn.loc)
    if label is not None:
        return str(label)
    return str(insn.loc)

class LocationLabel:
    def __init__(self, text, x, y, width, height):
        self.hovered = False
        self.text = text
        self.x = x
        self.y = y
        self.width = width
        self.height = height

class SectionMnemonic(SectionColumn):
    any_hovered = False

    def __init__(self, section: Section, **kwargs):
        super().__init__(section, **kwargs)
        self.width = dp(200)
        self.size_hint = None, 1
        self.halign = "left"
        self.labels: list[LocationLabel] = []
        self.ctrl_down = False
        self.markup = True

        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
        Window.bind(on_mouse_up=self._on_mouse_up)
        Window.bind(mouse_pos=self._on_mouse_move)
        
        text = []
        for insn in section.instructions:
            row_width = len(insn.entry.opcode) + 1
            row = f"[color=#569CD6]{insn.entry.opcode}[/color] "
            for i in range(len(insn.entry.instructions)):
                param = insn.entry.instructions[i]
                if isinstance(param, Loc):
                    label_text = loc_to_str(param)
                    t = f"[color=#DCDCAA]{label_text}[/color]"
                    self.labels.append(
                        LocationLabel(label_text, row_width * FONT_WIDTH, len(text) * FONT_HEIGHT, len(label_text) * FONT_WIDTH, FONT_HEIGHT))
                    row += t
                    row_width += len(label_text)
                elif isinstance(param, bytearray):
                    res = param.decode("ascii", "replace")
                    res = "".join(x if 0x6F > ord(x) > 0x20 else "." for x in res)
                    row += '"' + escape_markup(res) + '"'
                    row_width += len(res) + 2
                else:
                    insn_text = str(param)
                    row += escape_markup(insn_text)
                    row_width += len(insn_text)
                if i < len(insn.entry.instructions) - 1:
                    row += ", "
                    row_width += 2

            text.append(row)

        self.text = "\n".join(text)
        self.resize()

    @classmethod
    def on_mouse_move(cls, window, pos):
        cls.any_hovered = False
        
    @classmethod
    def update_cursor(cls):
        if cls.any_hovered and app().ctrl_down:
            Window.set_system_cursor('hand')
        else:
            Window.set_system_cursor('arrow')

    def _on_mouse_move(self, window, pos):
        x, y = pos
        sx, sy = self.to_window(self.x, self.y)
        for label in self.labels:
            label.hovered = False
            if (sx + label.x <= x <= sx + label.x + label.width and
                sy + self.height - label.y - label.height <= y <= sy + self.height - label.y):
                SectionMnemonic.any_hovered = True
                label.hovered = True
               

        self._on_update()
        SectionMnemonic.update_cursor()

    def _on_mouse_up(self, window, x: int, y: int, button: str, modifiers):
        for label in self.labels:
            if label.hovered and self.ctrl_down and button == 'left':
                try:
                    app().scroll_to_label(label.text)
                except ValueError: pass

    def _on_update(self):
        self.canvas.after.clear()

        for label in self.labels:
            if label.hovered and self.ctrl_down:
                color = get_color_from_hex("#64B5F6")

                cl = CoreLabel(text = label.text, font_size = FONT_SIZE, font_name = FONT_NAME)
                cl.refresh()
                              
                with self.canvas.after:
                    Color(*color)
                    Rectangle(texture = cl.texture, pos = (self.x + label.x, self.y + self.height - label.y - label.height), size = cl.texture.size)
                    Line(points=[
                        self.x + label.x, self.y + self.height - label.y - label.height + 1,
                        self.x + label.x + label.width, self.y + self.height - label.y - label.height + 1
                    ], width=dp(1))

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if keycode == 224: 
            self.ctrl_down = True
            self._on_update()
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 224: 
            self.ctrl_down = False
            self._on_update()

class SectionPanel(BoxLayout, RecycleDataViewBehavior):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.section: Section = None

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)

        section: Section = data["section"]
        self.section = section

        self.clear_widgets()
        for label in section.labels:
            self.add_widget(LabelRow(section, label.name))

        rows = BoxLayout(orientation = "horizontal", size_hint=(None, 1))
        rows.add_widget(SectionAddresses(section))
        rows.add_widget(SectionData(section))
        rows.add_widget(SectionMnemonic(section))

        self.add_widget(rows)
        

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
        self.effect_x = ScrollEffect()
        self.effect_y = DampedScrollEffect()

        project: Project = app().project

        data = []
        for section in project.sections:
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

        Window.bind(mouse_pos=SectionMnemonic.on_mouse_move)
        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
        Window.bind(on_touch_move=SectionColumn.on_touch_move_section)
        Window.bind(on_mouse_down=SectionColumn.on_mouse_down)
    
    def build(self):
        Window.clearcolor = BG_COLOR

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
                scroll_pos += math.ceil((offset - section.offset) / DATA_PER_ROW) * FONT_HEIGHT
                self.rv.scroll_y = 1 - (scroll_pos / total_height)
                return

            scroll_pos += data["height"]
        raise ValueError("Invalid location")

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if keycode == 224: 
            self.ctrl_down = True
            SectionMnemonic.update_cursor()
        elif keycode == 41: 
            self.goto_position.hide()
            return True
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 224: 
            self.ctrl_down = False
            SectionMnemonic.update_cursor()
        elif keycode == 41:
            return True

def main(path: str, ep: int, org: int):
    project = load_project(path, ep, org)

    window = DisApp(project)
    window.run()