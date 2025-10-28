from pathlib import Path
import json, math, shutil, tempfile, sys, traceback

from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar, Type, Generator, cast
from platformdirs import PlatformDirs
from configparser import ConfigParser

from kivy.app import App
from kivy.metrics import dp, Metrics
from kivy.clock import Clock, ClockEvent
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.splitter import Splitter
from kivy.uix.textinput import TextInput
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.event import EventDispatcher
from kivy.utils import get_color_from_hex

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
from .sections import RV, ScrollBar
from .function_graph import GraphTab, FunctionPanel
from .buttons import IconButton
from .analyzer import AnalyzerPanel, AnalyzerFilter, AnalyzerTab
from .context_menu import ContextMenuBehavior
from .popup import FunctionAnalyzerPopup
from .dock.dock import BaseDock, Dock, Orientation, SerializableTab, DockSplitter, DockPanel

class NavigationListing(NavigationAction):
    def __init__(self, panel: "MainPanel | None", offset: int):
        self.offset = offset
        self.panel = panel

    def navigate(self):
        app().scroll_to_offset(self.offset, self.panel, history=False)

class MainPanel(RelativeLayout):
    def __init__(self, **kw):
        self.rv: RV = cast(RV, None)
        self.minimap: Minimap = cast(Minimap, None)
        self.arrows: ArrowRenderer = cast(ArrowRenderer, None)
        self.scrollbar: ScrollBar = cast(ScrollBar, None)
        super().__init__(**kw)

    def on_kv_post(self, base_widget):
        self.rv = self.ids["rv"]
        self.minimap = self.ids["minimap"]
        self.arrows = self.ids["arrows"]
        self.scrollbar = self.ids["scrollbar"]

    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        return self.rv.on_touch_down_selection(touch)
    
    def on_touch_move(self, touch):
        if super().on_touch_move(touch): return True
        return self.rv.on_touch_move_section(touch)
    
    def get_sections(self):
        return app().project.sections.values()
    
    def serialize(self, data: dict):
        data["scroll_x"] = self.scrollbar.view.scroll_x
        data["scroll_y"] = self.rv.scroll_y
        data["selection_start"] = self.rv.selection_start
        data["selection_end"] = self.rv.selection_end
    
    def deserialize_post(self, data: dict):
        if "scroll_y" in data:
            self.rv.scroll_y = data["scroll_y"]
        if "scroll_x" in data:
            self.scrollbar.view.scroll_x = data["scroll_x"]
        if "selection_start" in data:  
            self.rv.selection_start = data["selection_start"]
        if "selection_end" in data:
            self.rv.selection_end = data["selection_end"]

        self.rv.redraw_children()

class MainWindow(FloatLayout): pass

class FunctionListing(MainPanel):
    def __init__(self, function: Function, **kwargs):
        self.fun = function
        self.sections: list[Section] | None = None
        super().__init__(**kwargs)

    def get_sections(self):
        if self.sections: return self.sections
        self.sections = list(
            sorted(map(lambda b: b.to_section(), self.fun.blocks.values()), 
                   key=lambda s: s.offset))
        return self.sections

class ListingTab(SerializableTab):
    content: FunctionListing

    def __init__(self, text: str, **kwargs):
        super().__init__(text=text, closeable=True, source="ui/resources/code-listing.png", **kwargs)

    def serialize(self) -> dict:
        res = super().serialize()
        res["function"] = self.content.fun.ep
        self.content.serialize(res)
        return res
    
    @classmethod
    def deserialize(cls, data: dict) -> "ListingTab":
        ep = data["function"]
        functions = app().project.functions
        assert functions
        fun = functions[ep]
        tab = ListingTab(fun.name)
        listing = FunctionListing(fun)
        tab.add_widget(listing)
        return tab

    def deserialize_post(self, data: dict):
        self.content.deserialize_post(data)

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

class MainDockTab(SerializableTab):
    content: MainPanel

    def serialize(self) -> dict:
        res = super().serialize()
        self.content.serialize(res)
        return res
    
    @classmethod
    def deserialize(cls, dict) -> "MainDockTab":
        tab = MainDockTab(text=app().project.filename)
        tab.add_widget(MainPanel())
        return tab
    
    def deserialize_post(self, dict):
        self.content.deserialize_post(dict)

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
    
        self.back_button.bind(on_press=lambda w: self.go_back())
        self.forward_button.bind(on_press=lambda w: self.go_forward())

        build_menu()
        if not self.load_ui_state():
            tab = MainDockTab(text=self.project.filename)
            tab.add_widget(self.dis_panel)
            self.main_dock.add_tab(tab)

        return self.window
    
    def load_ui_state(self) -> bool:
        file = self.get_project_ui_file()
        if not file.exists(): return False

        try:
            with open(file, "r") as fp:
                data = json.load(fp)

            Window.left = data.get("left", Window.left)
            Window.top = data.get("top", Window.top)

            if "width" in data and "height" in data:
                w, h = data["width"] / Metrics.density, data["height"] / Metrics.density
                Window.size = (w, h)

            active_tab: SerializableTab | None = None
            def deserialize(root: Dock, dock: BaseDock, data: dict[str, Any]):
                if "orientation" in data:
                    dock.orientation = data["orientation"]

                if "first" in data:
                    dock.first_panel = BaseDock(root, dock)
                    dock.add_widget(dock.first_panel)
                    deserialize(root, dock.first_panel, data["first"])
                
                if "splitter_pos" in data:
                    dock.splitter = DockSplitter("left" if dock.orientation == "horizontal" else "top")
                    dock.splitter.width = data["splitter_pos"]
                    dock.add_widget(dock.splitter)
                
                if "tab" in data:
                    dock.panel = DockPanel(root, dock)
                    dock.add_widget(dock.panel)

                    tab_index = data.get("tab_index", 0)
                    for i, tab_data in enumerate(reversed(data["tab"])):
                        tab = SerializableTab.deserialize_panel(tab_data)
                        if tab:
                            tab.root = root
                            dock.panel.add_widget(tab)
                            tab.deserialize_post(tab_data)
                            if i == tab_index: tab.select()
                            if tab_data.get("active", False):
                                nonlocal active_tab
                                active_tab = tab

                if "second" in data:
                    assert dock.splitter
                    dock.second_panel = BaseDock(root, dock)
                    dock.splitter.add_widget(dock.second_panel)
                    deserialize(root, dock.second_panel, data["second"])
                

            deserialize(self.main_dock, self.main_dock, data)
            if active_tab: active_tab.select()
            return True
        except:
            print("Error loading UI state:")
            traceback.print_exc()

        return False # FIXME Loading not implemented yet

    def save_ui_state(self):
        file = self.get_project_ui_file()
        file.parent.mkdir(parents=True, exist_ok=True)

        def serialize(panel: BaseDock) -> dict[str, Any]:
            res = {}

            if panel.first_panel:
                res["first"] = serialize(panel.first_panel)
            if panel.second_panel:
                res["second"] = serialize(panel.second_panel)

            if panel.panel:
                tabs = []
                for tab in panel.panel.iterate_panels():
                    if isinstance(tab, SerializableTab):
                        data = tab.serialize()
                        if tab.root and tab.root.active_panel == tab:
                            data["active"] = True
                        tabs.append(data)
                res["tab"] = tabs
                res["tab_index"] = panel.panel._tab_strip.children.index(panel.panel._current_widget)

            res["orientation"] = panel.orientation
            if panel.splitter:
                res["splitter_pos"] = panel.splitter.width

            return res

        with open(file, "w") as fp:
            data = serialize(self.main_dock)

            data["left"] = Window.left
            data["top"] = Window.top
            data["width"] = Window.width
            data["height"] = Window.height

            json.dump(data, fp)

    def get_project_ui_file(self) -> Path:
        return dirs.user_config_path / self.project.get_project_id() / "ui_state.json"
    
    def scroll_to_label(self, label: str, main_panel: MainPanel | None = None):
        sections = main_panel.get_sections() if main_panel else self.project.sections.values()
        for section in sections:
            if section.labels and section.labels[0].name == label:
                print("Goto label:", label, "at", format(section.offset, "X"))
                self.scroll_to_offset(section.offset, main_panel)
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
    
    def scroll_to_offset(self, offset: int, main_panel: MainPanel | None = None, history = True):
        rv = main_panel.rv if main_panel else self.dis_panel.rv

        self.switch_to_listing(main_panel)
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
                if history: self.update_position_history(NavigationListing(main_panel, offset))
                self.last_position = offset
                
                return

            scroll_pos += data["height"]
        raise ValueError("Invalid location")
    
    def switch_to_listing(self, main_panel: MainPanel | None = None):
        if main_panel:
            for tab in self.main_dock.iterate_panels():
                if tab.content == main_panel:
                    tab.select()
                    break
        else:
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

    def find_function(self, fun_name: str):
        if not self.project.functions: return None
        return next(filter(lambda f: f.name == fun_name, self.project.functions.values()), None)

    def open_function_listing(self, fun_name: str):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_listing(fun_name))
            return
        
        fun = self.find_function(fun_name)
        if not fun: return

        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, ListingTab) and tab.content.fun == fun:
                tab.select()
                return
        
        tab = ListingTab(text=fun.name)
        panel = FunctionListing(fun)
        tab.add_widget(panel)

        app().main_dock.add_tab(tab, reverse=True)
    
    def open_function_graph(self, fun_name: str, rescale=True, callback: Callable[[GraphTab], None] | None = None):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_graph(fun_name, rescale))
            return

        fun = self.find_function(fun_name)
        if not fun: return

        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, GraphTab) and tab.content.fun == fun:
                tab.select()
                return
        
        # Otherwise we open a new tab
        tab = GraphTab(fun.name)
        panel = FunctionPanel(fun, tab)
        tab.add_widget(panel)

        app().main_dock.add_tab(tab, reverse=True)

        def after(dt):
            panel.move_to_initial_pos()
            if callback: callback(tab)

        Clock.schedule_once(after, 0)


    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if "ctrl" in modifiers:
            if keycode == 10: # ctrl + g
                self.goto_position.show()

        if ("meta" in modifiers and sys.platform == "darwin" or "ctrl" in modifiers) and keycode == 9:
            if self.analyzer_panel and self.main_dock.active_content == self.analyzer_panel:
                self.analyzer_filter.show()

        # TODO Dynamic resizing is complicated
        #if ("meta" in modifiers and sys.platform == "darwin" or 
        #    "ctrl" in modifiers and sys.platform != "darwin"):
        #    if keycode == 48: # ctrl + '+'
        #        Metrics.density += 1
        #    elif keycode == 56: # ctrl + '-'
        #        Metrics.density -= 1

        if keycode == 225: self.shift_down = True
        elif keycode == 227 and sys.platform == "darwin" or keycode == 224: 
            self.ctrl_down = True
            RV.update_cursor()
        elif keycode == 41: 
            self.global_event_bus.dispatch("on_escape")
            return True
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 225: self.shift_down = False
        if keycode == 227 and sys.platform == "darwin" or keycode == 224: 
            self.ctrl_down = False
            RV.update_cursor()
        elif keycode == 41:
            return True
        
    def close_tabs(self):
        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, (GraphTab, ListingTab)):
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
        tab = AnalyzerTab()

        if not self.analyzer_panel:
            self.analyzer_panel = AnalyzerPanel(tab=tab)
            self.analyzer_filter = self.analyzer_panel.ids["analyzer_filter"]

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
        self.save_ui_state()
        super().on_stop()

def main(project: Project):
    global config
    config = ConfigParser()
    config.read(config_file)

    global _graph_tmpfolder
    _graph_tmpfolder = tempfile.mkdtemp()

    app = DisApp(project)
    app.run()
