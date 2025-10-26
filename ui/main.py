import math, shutil, tempfile, logging

from pathlib import Path
from abc import ABC, abstractmethod
from typing import Callable, TypeVar, Type, Generator, cast
from platformdirs import PlatformDirs
from configparser import ConfigParser

from kivy.app import App
from kivy.metrics import dp
from kivy.clock import Clock, ClockEvent
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.splitter import Splitter
from kivy.uix.textinput import TextInput
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.tabbedpanel import TabbedPanelItem
from kivy.event import EventDispatcher
from kivy.utils import get_color_from_hex
from kivy.metrics import Metrics

dirs = PlatformDirs(
    appname="PyDis",
    appauthor=False,
    ensure_exists=True
)

config_file = dirs.user_config_path / "dis.ini"
config: ConfigParser

FONT_SIZE = dp(15)
LABEL_HEIGHT = FONT_SIZE + dp(5)
FONT_NAME = "ui/resources/RobotoMono"
BG_COLOR = get_color_from_hex("#1F1F1F")

_graph_tmpfolder: str
def graph_tmpfolder() -> str:
    return _graph_tmpfolder

def app() -> "DisApp":
    return cast("DisApp", App.get_running_app())

def find_font_height():
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = FONT_SIZE
    )
    label.texture_update()
    return label.texture_size

FONT_WIDTH, FONT_HEIGHT = find_font_height()

R = TypeVar("R")
def iter_all_children_of_type(widget: Widget, widget_type: Type[R]) -> Generator[R, None, None]:
    if isinstance(widget, widget_type):
        yield widget
    if hasattr(widget, "children"):
        for child in widget.children:
            yield from iter_all_children_of_type(child, widget_type)

class NavigationAction(ABC):
    @abstractmethod
    def navigate(self): pass

class HideableTextInput(TextInput):
    def show(self):
        self.opacity = 1
        self.disabled = False
        self.text = ""
        self.focus = True

    def hide(self):
        self.opacity = 0
        self.disabled = True
        self.text = ""

class EscapeTrigger:
    def __init__(self):
        app().global_event_bus.bind(on_escape=self.on_escape)

    def on_escape(self, obj):
        pass

from tcls_900.tlcs_900 import Reg, Mem

from .project import Section, DATA_PER_ROW, MAX_SECTION_LENGTH, Project, new_project, Function
from .arrow import ArrowRenderer
from .minimap import Minimap
from .main_menu import build_menu
from .sections import RV
from .function_graph import FunctionTab, FunctionPanel
from .buttons import IconButton
from .analyzer import AnalyzerPanel, AnalyzerFilter
from .context_menu import ContextMenuBehavior
from .popup import FunctionAnalyzerPopup
from .dock.dock import DockTab, Dock, Orientation

class NavigationListing(NavigationAction):
    def __init__(self, offset: int):
        self.offset = offset

    def navigate(self):
        app().scroll_to_offset(self.offset, history=False)

class MainPanel(RelativeLayout):
    def __init__(self, **kw):
        self.rv = cast(RV, None)
        self.minimap = cast(Minimap, None)
        self.arrows = cast(ArrowRenderer, None)
        super().__init__(**kw)

    def on_kv_post(self, base_widget):
        self.rv = self.ids["rv"]
        self.minimap = self.ids["minimap"]
        self.arrows = self.ids["arrows"]

    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        return self.rv.on_touch_down_selection(touch)
    
    def on_touch_move(self, touch):
        if super().on_touch_move(touch): return True
        return self.rv.on_touch_move_section(touch)

class MainWindow(FloatLayout): pass

class GotoPosition(HideableTextInput, EscapeTrigger):
    def _on_focus(self, instance, value, *largs):
        if not value: self.hide()
        return super()._on_focus(instance, value, *largs)

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        if keycode[0] == 13:
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
        super().keyboard_on_key_down(window, keycode, text, modifiers)
    
    def on_escape(self, obj):
        self.hide()
    

class GlobalEventBus(EventDispatcher):
    def __init__(self, **kwargs):
        self.register_event_type("on_escape")
        super(GlobalEventBus, self).__init__(**kwargs)

    def on_escape(self, *args):
        pass

class MainDockTab(DockTab):
    content: MainPanel

class DisApp(App):
    _any_hovered = False

    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        
        self.goto_position = cast(GotoPosition, None)
        self.window = cast(MainWindow, None)
        self.back_button = cast(IconButton, None)
        self.forward_button = cast(IconButton, None)
        self.y_splitter = cast(Splitter, None)
        self.analyzer_panel: AnalyzerPanel | None = None
        self.dis_panel = cast(MainPanel, None)
        self.analyzer_filter = cast(AnalyzerFilter, None)
        self.main_dock = cast(Dock, None)

        self.last_position = -1
        self.position_history: list[NavigationAction] = []
        self.position = 0

        self.ctrl_down = False
        self.shift_down = False
        self.active: Widget

        self.global_event_bus = GlobalEventBus()

        Window.bind(mouse_pos=self.on_mouse_move)
        Window.bind(on_mouse_up=ContextMenuBehavior.on_mouse_up)
        Window.bind(on_mouse_down=ContextMenuBehavior.on_mouse_down)
        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
    
    def build(self):
        Window.clearcolor = BG_COLOR

        self.window = MainWindow()
        self.app_menu = self.window.ids["app_menu"]
        self.back_button = self.window.ids["back_button"]
        self.forward_button = self.window.ids["forward_button"]
        self.goto_position = self.window.ids["goto_position"]
        self.main_dock: Dock = self.window.ids["main_dock"]

        self.dis_panel = MainPanel()
        tab = MainDockTab(text="el9900.rom")
        tab.add_widget(self.dis_panel)
        self.main_dock.add_tab(tab)

        self.back_button.bind(on_press=lambda w: self.go_back())
        self.forward_button.bind(on_press=lambda w: self.go_forward())

        self.active = self.dis_panel

        build_menu()
        return self.window
    
    def scroll_to_label(self, label: str):
        for section in self.project.sections.values():
            if section.labels and section.labels[0].name == label:
                print("Goto label:", label, "at", format(section.offset, "X"))
                self.scroll_to_offset(section.offset)

                #tab_panel = self.dis_panel_container.children[0]
                #if isinstance(tab_panel, FunctionTabPanel):
                #    Clock.schedule_once(lambda dt: tab_panel.switch_to(tab_panel.tab_list[-1]))
                
                return
        raise ValueError("Invalid label")
    
    def update_position_history(self, action: NavigationAction):
        if self.position > 0:
            ln = len(self.position_history)
            self.position_history = self.position_history[:ln - self.position]
            self.position = 0

        self.position_history.append(action)
        self.update_position_buttons()

    def update_position_buttons(self):
        self.forward_button.disabled = self.position == 0
        self.back_button.disabled = self.position >= len(self.position_history) - 1

    def go_back(self):
        if self.position < len(self.position_history) - 1:
            self.position += 1

        position = self.position_history[len(self.position_history) - self.position - 1]
        position.navigate()
        self.update_position_buttons()

    def go_forward(self):
        if self.position > 0:
            self.position -= 1

        position = self.position_history[len(self.position_history) - self.position - 1]
        position.navigate()
        self.update_position_buttons()
    
    def scroll_to_offset(self, offset: int, history = True):
        rv = self.dis_panel.rv

        self.swich_to_listing()
        scroll_pos = 0
        for i in range(len(rv.data)):
            total_height = rv.children[0].height - rv.height
            data = rv.data[i]
            section: Section = data["section"]
            if section.offset <= offset < section.offset + section.length:
                if section.labels: scroll_pos += LABEL_HEIGHT
                scroll_pos += math.ceil((offset - section.offset) / DATA_PER_ROW) * FONT_HEIGHT
                rv.scroll_y = 1 - (scroll_pos / total_height)                
                rv.reset_selection()
                if history: self.update_position_history(NavigationListing(offset))
                self.last_position = offset
                
                return

            scroll_pos += data["height"]
        raise ValueError("Invalid location")
    
    def swich_to_listing(self):
        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, MainDockTab):
                tab.select()
                break
    
    def open_function_graph_from_label(self, ep: int):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_graph_from_label(ep))
            return
        for fun in self.project.functions.values():
            if ep in fun.blocks:
                self.open_function_graph(fun.name, callback=lambda panel: panel.content.move_to_location(ep))
                return

    
    def open_function_graph(self, fun_name: str, rescale=True, callback: Callable[[FunctionTab], None] | None = None):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_graph(fun_name, rescale))
            return

        fun = next(filter(lambda f: f.name == fun_name, self.project.functions.values()), None)
        if not fun: return

        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, FunctionTab) and tab.content.fun == fun:
                tab.select()
                return
        
        # Otherwise we open a new tab
        tab = FunctionTab(text=fun.name, closeable=True)
        panel = FunctionPanel(fun, tab)
        tab.add_widget(panel)

        app().main_dock.add_tab(tab, reverse=True)

        def after(dt):
            panel.move_to_initial_pos()
            if callback: callback(tab)

        Clock.schedule_once(after, 0)
        self.active = self.dis_panel


    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if "ctrl" in modifiers: # ctrl + g
            if keycode == 10:
                self.goto_position.show()
            elif keycode == 9:
                if self.active == self.analyzer_panel:
                    self.analyzer_filter.show()

        if keycode == 225: self.shift_down = True
        elif keycode == 224: 
            self.ctrl_down = True
            RV.update_cursor()
        elif keycode == 41: 
            self.global_event_bus.dispatch("on_escape")
            return True
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 225: self.shift_down = False
        if keycode == 224: 
            self.ctrl_down = False
            RV.update_cursor()
        elif keycode == 41:
            return True
        
    def close_tabs(self):
        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, FunctionTab):
                tab.close()
        
    def load_project(self, project: Project):
        self.project = project

        # Clear history
        self.position = 0
        self.position_history.clear()
        self.update_position_buttons()

        # Close views
        if self.analyzer_panel:
            self.analyzer_panel.tab.close()
            self.analyzer_panel = None

        self.close_tabs()

        # Update data FIXME All
        self.dis_panel.rv.update_data()
        self.dis_panel.arrows.recompute_arrows()
        self.dis_panel.arrows.redraw()
        self.dis_panel.minimap.redraw()
        
    def analyze_functions(self, callback):
        wait: ClockEvent = None
        total_amount = 0
        popup: FunctionAnalyzerPopup

        def interval(dt):
            Window.set_system_cursor("wait")
            app().set_hover()

        def finish(dt):
            wait.cancel()
            Window.set_system_cursor("arrow")
            popup.dismiss()
            callback()

        def progress(i: int, fun: str):
            popup.value = i
            popup.current = fun

        wait = Clock.schedule_interval(interval, 0)
        total_amount = app().project.analyze_functions(
            lambda: Clock.schedule_once(finish, 0),
            lambda c, fun: Clock.schedule_once(lambda dt: progress(c, fun), 0)
        )
        popup = FunctionAnalyzerPopup(max=total_amount)
        popup.open()
        
    def open_function_list(self):
        tab = DockTab(text="Functions", closeable=True)

        if not self.analyzer_panel:
            self.analyzer_panel = AnalyzerPanel(tab=tab)
            self.analyzer_filter = self.analyzer_panel.ids["analyzer_filter"]
            self.active = self.analyzer_panel

        elif self.analyzer_panel.tab.get_root_window():
            self.analyzer_panel.tab.select()
            return
        
        tab.add_widget(self.analyzer_panel)
        self.main_dock.split(tab, Orientation.VERTICAL)
        tab.select()

    
    def on_mouse_move(self, window, pos):
        DisApp._any_hovered = False
        def post(dt):
            if not DisApp._any_hovered:
                Window.set_system_cursor("arrow")

        Clock.schedule_once(post, 0)

    def set_hover(self):
        DisApp._any_hovered = True

    @property
    def any_hovered(self):
        return DisApp._any_hovered
    
    def on_stop(self):
        try:
            shutil.rmtree(_graph_tmpfolder)
        except FileNotFoundError: pass

        window = {}
        window["width"] = str(Window.size[0])
        window["height"] = str(Window.size[1])
        window["left"] = str(Window.left)
        window["top"] = str(Window.top)
        config["window"] = window

        with open(config_file, "w") as fp:
            config.write(fp)

        super().on_stop()

def main(path: Path, ep: int | list[int], org: int):
    global config
    config = ConfigParser()
    config.read(config_file)

    project = new_project(path, ep, org)
    global _graph_tmpfolder
    _graph_tmpfolder = tempfile.mkdtemp()
    
    logging.info(f"PyDis: Config file: {config_file}")
    
    if "window" in config:
        window = config["window"]
        if "width" in window and "height" in window:
            Window.size = (
                int(window["width"]) / Metrics.density, 
                int(window["height"]) / Metrics.density
            )
        if "left" in window and "top" in window:
            Window.left = int(window["left"])
            Window.top = int(window["top"])

    app = DisApp(project)
    app.run()
