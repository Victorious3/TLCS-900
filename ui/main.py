import math, weakref

from kivy.app import App
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.splitter import Splitter
from kivy.uix.textinput import TextInput
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.recycleview import RecycleView
from kivy.utils import get_color_from_hex, escape_markup
from kivy.effects.scroll import ScrollEffect
from kivy.properties import ListProperty, StringProperty, NumericProperty

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

def iter_all_children_of_type(widget: Widget, widget_type: type):
    if isinstance(widget, widget_type):
        yield widget
    for child in widget.children:
        yield from iter_all_children_of_type(child, widget_type)

from tcls_900.tlcs_900 import Reg, Mem

from .project import Section, DATA_PER_ROW, MAX_SECTION_LENGTH, Project, load_project
from .arrow import ArrowRenderer
from .minimap import Minimap
from .main_menu import build_menu
from .sections import SectionColumn, SectionAddresses, SectionData, SectionMnemonic
from .table.table import ResizableRecycleTable, DataTableRow, TableBody


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
    icon_height = NumericProperty(dp(20))

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

HEADER_NAMES = ["name", "address", "input", "clobber", "output"]
COLUMN_WIDTHS = [dp(100), dp(100), dp(250), dp(250), dp(250)]

class AnalyzerTableRow(DataTableRow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self.on_mouse_move)

    def on_touch_down(self, touch):
        inside = self.collide_point(touch.x, touch.y)
        if inside:
            if touch.button == "left":
                app().scroll_to_label(self.data[0])
                return True
        return super().on_touch_down(touch)
    
    def on_motion(self, etype, me):
        return super().on_motion(etype, me)
    
    def on_mouse_move(self, window, pos):
        inside = self.collide_point(*self.to_widget(*pos))
        if inside:
            # Ugly UI hack
            table: AnalyzerTable = next(iter_all_children_of_type(app().analyzer_panel, AnalyzerTable))
            if not table.is_pos_inside_of_body(pos): return

        if inside and not app().any_hovered:
            app().set_hover()
            Window.set_system_cursor('hand')
    
class AnalyzerPanel(RelativeLayout):
    def close_panel(self):
        app().content_panel.remove_widget(app().y_splitter)

class AnalyzerTable(ResizableRecycleTable):
    def __init__(self, **kwargs):
        super().__init__(headers = HEADER_NAMES, data = [], column_widths=COLUMN_WIDTHS, cols=5, **kwargs)
        self.viewclass = "AnalyzerTableRow"

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.update_data()

    def update_data(self):
        project = app().project
        self.data = []
        for fun in project.functions.values():
            if not fun.state: continue
            row = []
            # name
            row.append(fun.name)
            # address
            row.append(format(fun.ep, "X"))
            # callers
            #callers = set(map(lambda c: c[1], fun.callers))
            #row.append(", ".join(map(lambda c: c.name, callers)))
            # callees
            #callees = set(map(lambda c: c[1], fun.callers))
            #row.append(", ".join(map(lambda c: c.name, callees)))
            #input registers
            row.append(", ".join(map(str, filter(lambda r: isinstance(r, Reg), fun.state.input))))
            #clobber registers
            row.append(", ".join(map(lambda x: str(x[1]), filter(lambda r: isinstance(r[1], Reg), fun.state.clobbers))))
            #ouput registers
            row.append(", ".join(map(str, filter(lambda r: isinstance(r, Reg), fun.state.output))))

            self.data.append(row)

        self.body.update_data()

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
        for section in app().project.sections.values():
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
        return SectionColumn.on_touch_down_selection(touch)
    
    def on_touch_move(self, touch):
        if super().on_touch_move(touch): return True
        return SectionColumn.on_touch_move_section(touch)
    
    def on_touch_up(self, touch):
        if super().on_touch_up(touch): return True
        return SectionColumn.on_touch_up_selection(touch)

class DisApp(App):
    _any_hovered = False

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
        self.content_panel: BoxLayout = None
        self.y_splitter: Splitter = None
        self.analyzer_panel: AnalyzerPanel = None
        self.dis_panel: Widget = None

        self.last_position = -1
        self.position_history: list[int] = []
        self.position = 0

        self.ctrl_down = False
        self.shift_down = False

        Window.bind(mouse_pos=self.on_mouse_move)
        Window.bind(mouse_pos=SectionMnemonic.on_mouse_move)
        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
    
    def build(self):
        Window.clearcolor = BG_COLOR

        self.window = MainWindow()
        self.app_menu = self.window.ids["app_menu"]
        self.back_button = self.window.ids["back_button"]
        self.forward_button = self.window.ids["forward_button"]
        self.content_panel = self.window.ids["content_panel"]
        self.dis_panel = self.window.ids["dis_panel"]

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
        for section in self.project.sections.values():
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
    
    def open_function_graph(fun: str):
        pass

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
        
    def open_function_list(self):
        if not self.y_splitter:
            self.analyzer_panel = AnalyzerPanel()
            self.y_splitter = Splitter(
                keep_within_parent = True,
                min_size = dp(100),
                max_size = dp(10e10),
                sizable_from = "top"
            )
            self.y_splitter.add_widget(self.analyzer_panel)
        if self.y_splitter.get_root_window() is None:
            self.content_panel.add_widget(self.y_splitter)
    
    def on_mouse_move(self, window, pos):
        DisApp._any_hovered = False
        def post(dt):
            if not DisApp._any_hovered:
                Window.set_system_cursor('arrow')

        Clock.schedule_once(post, 0)

    def set_hover(self):
        DisApp._any_hovered = True

    @property
    def any_hovered(self):
        return DisApp._any_hovered

def main(path: str, ep: int, org: int):
    project = load_project(path, ep, org)

    window = DisApp(project)
    window.run()