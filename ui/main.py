import math

from kivy.app import App
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior

from .project import Section, CodeSection, DataSection, DATA_PER_ROW, Project, load_project

FONT_SIZE = 16
FONT_NAME = "ui/FiraMono"

def find_font_height():
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = FONT_SIZE
    )
    label.texture_update()
    return label.texture_size[1]

FONT_HEIGHT = find_font_height()

class MainWindow(FloatLayout): pass

class LabelRow(TextInput):
    def __init__(self, section: Section, label: str, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = 1, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
        self.height = dp(32)
        self.section = section
        self.background_color = 0, 0, 0, 0
        self.foreground_color = 1, 1, 1, 1
        self.text = label

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

class SectionMnemonic(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(**kwargs)
        self.width = dp(200)
        self.section = section
        self.halign = "left"

        lines = []
        if isinstance(section, CodeSection):
            for insn in section.instructions:
                lines.append(insn.entry.opcode + " " + ", ".join(map(str, insn.entry.instructions)))
        elif isinstance(section, DataSection):
            i = 0
            while i < section.length:
                next = min(i + DATA_PER_ROW, section.length)
                data = section.data[i:next].copy()
                res = data.decode("ascii", "replace")
                res = "".join(x if 0x6F > ord(x) > 0x20 else "." for x in res)

                lines.append(f'.db "{res}"')

                i += DATA_PER_ROW
            
        self.text = "\n".join(lines)
        self.resize()

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
            except ValueError:
                return

            self.opacity = 0
            self.disabled = True
            self.text = ""

            app().scroll_to_offset(offset)
            return
        
        super()._key_down(key, repeat)

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

            data.append({"section": section, "height": columns * FONT_HEIGHT + (dp(32) if section.labels else 0)})

        self.data = data

class DisApp(App):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.goto_position: GotoPosition = None
        self.rv: RV = None
    
    def build(self):
        window = MainWindow()
        return window
    
    def scroll_to_offset(self, offset: int):
        scroll_pos = 0
        for i in range(len(self.rv.data)):
            last_height = self.rv.data[-1]["height"]
            data = self.rv.data[i]
            section: Section = data["section"]
            if section.offset <= offset < section.offset + section.length:
                self.rv.scroll_y = 1 - (scroll_pos / (self.rv.children[0].height - self.rv.height))
                break

            scroll_pos += data["height"]

        print(sum(map(lambda d: d["height"], self.rv.data)), self.rv.children[0].height)
    
def app() -> DisApp:
    return App.get_running_app()

def main(path: str, ep: int, org: int):
    project = load_project(path, ep, org)

    window = DisApp(project)
    window.run()