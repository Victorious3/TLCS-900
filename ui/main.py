import math, weakref

from kivy.app import App
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.window.window_sdl2 import WindowSDL
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import get_color_from_hex, escape_markup
from kivy.core.text import Label as CoreLabel
from kivy.effects.scroll import ScrollEffect
from kivy.properties import ListProperty, StringProperty

from kivy_garden.contextmenu import AppMenu

FONT_SIZE = dp(15)
LABEL_HEIGHT = FONT_SIZE + dp(5)
FONT_NAME = "ui/RobotoMono"
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

from .project import Section, DATA_PER_ROW, MAX_SECTION_LENGTH, Project, load_project
from .arrow import ArrowRenderer
from .minimap import Minimap
from .context_menu import show_context_menu
from .main_menu import MenuHandler, MenuItem, build_menu
from disapi import Loc

def iter_all_children_of_type(widget: Widget, widget_type: type):
    if isinstance(widget, widget_type):
        yield widget
    for child in widget.children:
        yield from iter_all_children_of_type(child, widget_type)

class Icon(Image):
    def on_touch_down(self, touch):
        return False
    def on_touch_up(self, touch):
        return False

class IconButton(Button):
    icon_color = ListProperty([1, 1, 1, 1])
    default_color = ListProperty([0.2, 0.2, 0.2, 1])
    hover_color = ListProperty([0.25, 0.25, 0.25, 1])
    source = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = self.default_color
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, widget, pos):
        if self.get_root_window():
            inside = self.collide_point(*self.to_widget(*pos))
            if inside and not self.disabled:
                self.background_color = self.hover_color
            else:
                self.background_color = self.default_color

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
        self.padding = [dp(250), 0, 0, 0]
        self.multiline = False

class SectionColumn(Label):
    selection_start = 0
    selection_end = 0
    outside_bounds = False

    def __init__(self, section: Section, **kwargs):
        super().__init__(**kwargs)
        self.section = section
        self.size_hint = None, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME

    def resize(self):
        self.texture_update()
        self.height = self.texture_size[1]
        self.text_size = self.size
    
    def redraw(self): pass

    @classmethod
    def calculate_selection(cls, pos: tuple[int, int]):
        for panel in cls.find_children():
            x, y = panel.to_window(panel.x, panel.y)
            if pos[0] > x + panel.width: x1 = 0
            else: x1 = math.floor((pos[0] - x) / (FONT_WIDTH * 3))
            if y <= pos[1] < y + panel.height:
                section = panel.section
                y1 = y - pos[1]
                rows = len(section.instructions)
                row = math.floor(rows + y1 / FONT_HEIGHT)
                if row >= len(section.instructions): continue
                insn = section.instructions[row]
                x1 = min(insn.entry.length - 1, max(x1, 0))
                offset = insn.entry.pc + x1
                return offset
                
        return -1
    
    @classmethod
    def find_children(cls):
        yield from iter_all_children_of_type(app().rv.children[0], SectionData)
    
    @classmethod
    def reset_selection(cls):
        cls.selection_start = 0
        cls.selection_end = 0
        cls.redraw_children()

    @classmethod
    def redraw_children(cls):
        for panel in cls.find_children():
            panel.redraw()

    @classmethod
    def on_touch_move_section(cls, touch):
        if cls.outside_bounds: return
        if touch.button != "left": return
        tx, ty = app().rv.to_window(touch.x, touch.y)

        panel = next(cls.find_children())
        x, y = panel.to_window(panel.x, panel.y)
        if touch.x > x + panel.width:
            end = cls.calculate_selection((x + panel.width, ty))
        else:
            end = cls.calculate_selection((tx, ty))

        if end > 0:
            cls.selection_end = end

        cls.redraw_children()
    
    @classmethod
    def on_touch_down_selection(cls, touch):
        if touch.button != "left": return
        cls.outside_bounds = touch.x > app().minimap.x
        if cls.outside_bounds: return
        tx, ty = app().rv.to_window(touch.x, touch.y)

        panel = next(cls.find_children())
        x, y = panel.to_window(panel.x, panel.y)
        if touch.x > x + panel.width:
            selection_end = cls.calculate_selection((x + panel.width, ty))
            selection_start = cls.calculate_selection((x, ty))
        else:
            selection_end = cls.calculate_selection((tx, ty))
            selection_start = selection_end

        if not app().shift_down: 
            cls.selection_end = selection_end
            cls.selection_start = selection_start
        else:
            start = cls.selection_start
            end = cls.selection_end
            if start > end:
                if selection_end < start: cls.selection_end = selection_end
                else: cls.selection_start = selection_start
            else:
                if selection_end < end: cls.selection_start = selection_start
                else: cls.selection_end = selection_end

        cls.redraw_children()

    @classmethod
    def on_touch_up_selection(cls, touch):
        if (touch.button == "right" and 
            touch.x < app().rv.width - app().minimap.width):

            class Handler(MenuHandler):
                def on_select(self, item):
                    if item == "dis": 
                        a = app()
                        def callback():
                            a.rv.update_data()
                            a.minimap.redraw()
                            a.arrows.recompute_arrows()
                            a.arrows.redraw()
                            Clock.schedule_once(lambda dt: a.scroll_to_offset(cls.selection_start), 0)
                
                        a.project.disassemble(cls.selection_start, callback)
                        
            show_context_menu(Handler(), [
                MenuItem("label", "Insert Label"),
                MenuItem("dis", "Disassemble from here"),
                MenuItem("dis_oneshot", "Disassemble oneshot"),
                MenuItem("dis_selected", "Disassemble selected"),
            ])

class SectionAddresses(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(section, **kwargs)
        self.width = dp(240)
        self.pos = (0, 0)
        self.halign = "right"
        self.text = "\n".join(format(x, "X") for x in map(lambda i: i.entry.pc, section.instructions))
        self.resize()

    @classmethod
    def redraw_children(cls):
        for panel in iter_all_children_of_type(app().rv.children[0], SectionAddresses):
            panel.redraw()
    
    def redraw(self):
        super().redraw()
        self.canvas.before.clear()

        last_position = app().last_position
        if self.section.offset <= last_position < self.section.offset + self.section.length:
            # Draw background on location that has been jumped to
            for i, insn in enumerate(self.section.instructions):
                if insn.entry.pc + insn.entry.length > last_position:
                    width = len(format(insn.entry.pc, "X")) * FONT_WIDTH
                    with self.canvas.before:
                        Color(*get_color_from_hex("#E69533"))
                        Rectangle(pos=(self.x + self.width - width, self.y + (self.height - i * FONT_HEIGHT) - FONT_HEIGHT), size=(width, FONT_HEIGHT))
                    break
        

class SectionData(SectionColumn):
    def __init__(self, section: Section, **kwargs):
        super().__init__(section, **kwargs)
        self.width = DATA_PER_ROW * dp(40)
        self.halign = "left"
        self.pos = (dp(270), 0)
        self.color = get_color_from_hex("#B5CEA8")

        lines = []
        for insn in section.instructions:
            data = section.data[
                insn.entry.pc - section.offset :
                insn.entry.pc + insn.entry.length - section.offset]
            lines.append(" ".join(format(x, "0>2X") for x in data))

        self.text = "\n".join(lines)
        self.resize()

    def redraw(self):
        start, end = SectionColumn.selection_start, SectionColumn.selection_end
        if end < start: start, end = end, start

        self.canvas.before.clear()

        if (self.section.offset <= start <= self.section.offset + self.section.length or
            self.section.offset <= end <= self.section.offset + self.section.length or
            start < self.section.offset and end > self.section.offset + self.section.length):

            row_start = len(self.section.instructions)
            row_end = 0
            start_column = 0
            end_column = 0
            for i, insn in enumerate(self.section.instructions):
                if insn.entry.pc > start:
                    last = self.section.instructions[i - 1]
                    start_column = last.entry.length - insn.entry.pc + start
                    row_start = i
                    break
            else: 
                start_column = self.section.instructions[-1].entry.length - (self.section.offset + self.section.length - start)

            end_length = 0
            for i, insn in reversed(list(enumerate(self.section.instructions))):
                if insn.entry.pc <= end: 
                    end_column = end - insn.entry.pc + 1
                    end_length = insn.entry.length
                    row_end = i
                    break

            with self.canvas.before:
                Color(*get_color_from_hex("#264F78"))

                start_x = start_column * 3 * FONT_WIDTH
                end_x = end_column * 3 * FONT_WIDTH
                width = app().rv.width - app().minimap.width

                if self.section.offset <= start < self.section.offset + self.section.length and row_start - 1 == row_end and end_column < end_length:
                    if start_column == 0:
                        Rectangle(pos=(self.parent.x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(self.x + 3 * FONT_WIDTH, FONT_HEIGHT))
                    Rectangle(pos=(self.x + start_x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(end_x - start_x, FONT_HEIGHT))
                else:
                    if self.section.offset <= start < self.section.offset + self.section.length: 
                        if start_column == 0:
                            Rectangle(pos=(self.parent.x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(width, FONT_HEIGHT))
                        else:
                            Rectangle(pos=(self.x + start_x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(width - start_x - self.x, FONT_HEIGHT))
                    if self.section.offset <= end < self.section.offset + self.section.length and row_end >= row_start:
                        if end_column < end_length:
                            Rectangle(pos=(self.parent.x, self.y + self.height - ((row_end + 1) * FONT_HEIGHT)), size=(self.x + end_x, FONT_HEIGHT))
                        else:
                            Rectangle(pos=(self.parent.x, self.y + self.height - ((row_end + 1) * FONT_HEIGHT)), size=(width, FONT_HEIGHT))


                    if row_start <= row_end:
                        off_y = 0
                        if end >= self.section.offset + self.section.length: off_y = 1
                        Rectangle(pos=(self.parent.x, self.y + self.height - ((row_end + off_y) * FONT_HEIGHT)), size=(width, (row_end + off_y - row_start) * FONT_HEIGHT))



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
        self.pos = (dp(550), 0)
        self.width = dp(400)
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
                    res = "".join(x if 0x7E >= ord(x) >= 0x20 else "." for x in res)
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

        rows = RelativeLayout(size_hint=(1, 1))
        rows.add_widget(SectionData(section))
        rows.add_widget(SectionAddresses(section))
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
 
class RV(RecycleView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app().rv = self
        self.effect_x = ScrollEffect()
        self.update_data()
        self.bind(size=lambda *args: SectionColumn.redraw_children())

    def update_data(self):
        data = []
        for section in app().project.sections:
            columns = len(section.instructions)
            data.append({"section": section, 
                         "height": columns * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0),
                         "width": dp(1500) })

        self.data = data

    def update_from_scroll(self, *largs):
        super().update_from_scroll(*largs)

        def update(dt):
            SectionAddresses.redraw_children()
            SectionData.redraw_children()

        Clock.schedule_once(update, 0)
        
        app().arrows.redraw()

    def get_visible_range(self):
        content_height = self.children[0].height - self.height
        scroll_pos = self.scroll_y * content_height

        return scroll_pos, scroll_pos + self.height
    
    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        SectionColumn.on_touch_down_selection(touch)
    
    def on_touch_move(self, touch):
        if super().on_touch_move(touch): return True
        SectionColumn.on_touch_move_section(touch)
    
    def on_touch_up(self, touch):
        if super().on_touch_up(touch): return True
        SectionColumn.on_touch_up_selection(touch)

class DisApp(App):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        
        self.goto_position: GotoPosition = None
        self.rv: RV = None
        self.minimap: Minimap = None
        self.arrows: ArrowRenderer = None
        self.window: MainWindow = None
        self.app_menu: AppMenu = None
        self.back_button: IconButton = None
        self.forward_button: IconButton = None

        self.last_position = -1
        self.position_history: list[int] = []
        self.position = 0

        self.ctrl_down = False
        self.shift_down = False

        Window.bind(mouse_pos=SectionMnemonic.on_mouse_move)
        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
    
    def build(self):
        Window.clearcolor = BG_COLOR

        self.window = MainWindow()
        self.app_menu = self.window.ids["app_menu"]
        self.back_button = self.window.ids["back_button"]
        self.forward_button = self.window.ids["forward_button"]

        self.back_button.bind(on_press=lambda w: self.go_back())
        self.forward_button.bind(on_press=lambda w: self.go_forward())

        build_menu()
        return self.window
    
    def after_layout_is_ready(self, dt):
        self.minimap.redraw()
        self.arrows.redraw()

    def on_start(self):
        super().on_start()
        Clock.schedule_once(self.after_layout_is_ready, 0)
    
    def scroll_to_label(self, label: str):
        for section in self.project.sections:
            if section.labels and section.labels[0].name == label:
                print("Goto label:", label, "at", format(section.offset, "X"))
                self.scroll_to_offset(section.offset)
                return
        raise ValueError("Invalid label")
    
    def update_position_history(self, offset):
        if self.position > 0:
            ln = len(self.position_history)
            self.position_history = self.position_history[:ln - self.position]
            self.position = 0

        self.position_history.append(offset)
        self.update_position_buttons()

    def update_position_buttons(self):
        self.forward_button.disabled = self.position == 0
        self.back_button.disabled = self.position == len(self.position_history) - 1

    def go_back(self):
        if self.position < len(self.position_history) - 1:
            self.position += 1
        self.scroll_to_offset(self.position_history[len(self.position_history) - self.position - 1], history=False)
        self.update_position_buttons()

    def go_forward(self):
        if self.position > 0:
            self.position -= 1
        self.scroll_to_offset(self.position_history[len(self.position_history) - self.position - 1], history=False)
        self.update_position_buttons()
    
    def scroll_to_offset(self, offset: int, history = True):
        scroll_pos = 0
        for i in range(len(self.rv.data)):
            total_height = self.rv.children[0].height - self.rv.height
            data = self.rv.data[i]
            section: Section = data["section"]
            if section.offset <= offset < section.offset + section.length:
                if section.labels: scroll_pos += LABEL_HEIGHT
                scroll_pos += math.ceil((offset - section.offset) / DATA_PER_ROW) * FONT_HEIGHT
                self.rv.scroll_y = 1 - (scroll_pos / total_height)                
                SectionData.reset_selection()
                if history: self.update_position_history(offset)
                self.last_position = offset
                
                return

            scroll_pos += data["height"]
        raise ValueError("Invalid location")

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if "ctrl" in modifiers and keycode == 10: # ctrl + g
            self.goto_position.disabled = False
            self.goto_position.opacity = 1
            self.goto_position.focus = True

        elif keycode == 225: self.shift_down = True
        elif keycode == 224: 
            self.ctrl_down = True
            SectionMnemonic.update_cursor()
        elif keycode == 41: 
            self.goto_position.hide()
            return True
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 225: self.shift_down = False
        if keycode == 224: 
            self.ctrl_down = False
            SectionMnemonic.update_cursor()
        elif keycode == 41:
            return True

def main(path: str, ep: int, org: int):
    project = load_project(path, ep, org)

    window = DisApp(project)
    window.run()