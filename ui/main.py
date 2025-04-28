import math
from itertools import groupby

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

from .project import Section, CodeSection, DataSection, DATA_PER_ROW, Project, load_project
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
            Color(1, 0, 0, 1)
            for key, group in groupby(sections, key=type):
                group = list(group)
                if key == DataSection:
                    height = sum(map(ds_height, group))
                else:
                    height = sum(map(cs_height, group))
                    Rectangle(pos=(self.x, self.y + (1 - (offset / total_height)) * self.height), size=(self.width, height / total_height * self.height))

                offset += height


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
        self.padding = 0

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
        self.width = dp(120)
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
    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)

        section: Section = data["section"]

        self.clear_widgets()
        for label in section.labels:
            self.add_widget(LabelRow(section, label.name))

        rows = BoxLayout(orientation = "horizontal", size_hint=(None, None))
        rows.add_widget(SectionAddresses(section))
        rows.add_widget(SectionData(section))
        rows.add_widget(SectionMnemonic(section))
        rows.do_layout()
        rows.height = rows.minimum_height

        self.add_widget(rows)
        self.height = self.minimum_height

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

            data.append({"section": section, "height": columns * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0)})

        self.data = data

class DisApp(App):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        
        self.goto_position: GotoPosition = None
        self.rv: RV = None
        self.minimap: Minimap = None

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
            total_height = self.rv.children[0].height
            data = self.rv.data[i]
            section: Section = data["section"]
            if section.offset <= offset < section.offset + section.length:
                scroll_pos += LABEL_HEIGHT
                if isinstance(section, DataSection):
                    scroll_pos += math.ceil((offset - section.offset) / DATA_PER_ROW) * FONT_HEIGHT
                elif isinstance(section, CodeSection):
                    for insn in section.instructions:
                        if offset > insn.entry.pc: scroll_pos += FONT_HEIGHT
                        else: break

                self.rv.scroll_y = 1 - (scroll_pos / (total_height - self.rv.height))
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