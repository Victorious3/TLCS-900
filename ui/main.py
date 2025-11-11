from itertools import groupby
from pathlib import Path
import json, math, shutil, tempfile, sys, traceback, logging

from abc import ABC, abstractmethod
from typing import Any, Callable, Iterable, TypeVar, Type, Generator, Union, cast
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
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.treeview import TreeView, TreeViewLabel
from kivy.uix.scrollview import ScrollView
from kivy.event import EventDispatcher
from kivy.utils import get_color_from_hex
from kivy.properties import BooleanProperty

from disapi import insnentry_to_str
from tcls_900.tlcs_900 import Mem, Reg
from ui.kivytypes import KWidget


# Patch widget class TODO Handle on_leave when children move out of view
def on_mouse_move(self: Widget, pos):
    hovered = getattr(self, "_hovered", False)
    if self.collide_point(*pos):
        for child in self.children:
            child.on_mouse_move(self.to_local(*pos))

        if not hovered: self.on_enter() # type: ignore
        setattr(self, "_hovered", True)
    else:
        if hovered: self.on_leave() # type: ignore
        setattr(self, "_hovered", False)

Widget.on_mouse_move = on_mouse_move # type: ignore
Widget.on_enter = lambda self: None # type: ignore
Widget.on_leave = lambda self: None # type: ignore

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

def find_font_height() -> tuple[int, int]:
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = FONT_SIZE
    )
    label.texture_update()
    return label.texture_size # type: ignore

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

class NavigationListing(NavigationAction):
    def __init__(self, panel: "ListingPanel | None", offset: int):
        self.offset = offset
        self.panel = panel

    def navigate(self):
        try:
            app().switch_to_listing(self.panel)
            app().scroll_to_offset(self.offset, self.panel, history=False)
        except ValueError as e:
            pass # Invalid location

from .project import Instruction, Section, DATA_PER_ROW, Project, Function
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
from .call_graph import CallGraphPanel, CallGraphTab

class RenameInput(BoxLayout, EscapeTrigger):
    input: TextInput
    ep: int

    def on_kv_post(self, base_widget):
        self.input = self.children[0]
        self.input.bind(focus=self._on_focus) # type: ignore

    def _on_focus(self, instance, value):
        if not value:
            app().project.rename_label(self.ep, self.input.text)
            self.hide()

    def hide(self):
        self.opacity = 0
        self.disabled = True
        self.pos = (-1000, -1000)

    def show(self, ep: int, x: int, y: int):
        label = app().project.ob.label(ep)
        if not label: return
        app().main_dock.unfocus_all()
        self.ep = ep
        self.pos = (x, y)
        self.disabled = False
        self.opacity = 1
        self.input.text = label.name
        self.input.focus = True

    def on_escape(self, obj):
        self.hide()

class ListingPanel(RelativeLayout):
    is_root: bool = BooleanProperty(False)

    def __init__(self, **kw):
        self.rv: RV = cast(RV, None)
        self.minimap: Minimap = cast(Minimap, None)
        self.arrows: ArrowRenderer = cast(ArrowRenderer, None)
        self.scrollbar: ScrollBar = cast(ScrollBar, None)
        self.highlighted: int | None = None
        self.highlighted_list = []
        self.highlight_index = -1

        Window.bind(on_key_down=self._keydown)
        super().__init__(**kw)

    def toggle(self): pass

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if self.get_root_window() is None:
            return

        if not self.highlighted: return
        if keycode == 82: # Up
            self.select_next_highlight(-1)
        elif keycode == 81: # Down
            self.select_next_highlight(1)
        elif keycode == 41: # Escape
            self.end_highlight()

    def _set_selection_end(self):
        sections = self.get_sections()
        for s in sections: 
            for insn in s.instructions:
                if insn.entry.pc == self.rv.selection_start:
                    self.rv.selection_end = insn.entry.pc + insn.entry.length - 1
                    break

    def highlight(self, fun: Function, callee: int | None = None, caller: int | None = None):
        self.highlighted = callee if callee is not None else caller
        if callee:
            self.highlighted_list = list(set([index for index, callee in fun.callees if callee == self.highlighted]))
        elif caller:
            self.highlighted_list = list(set([index for index, _ in fun.callers]))
        
        logging.info("Highlighting %d occurrences of %s of function %s", len(self.highlighted_list), 
                     "callee" if callee is not None else "caller", fun.name)
        self.highlighted_list.sort()
        if len(self.highlighted_list) == 0:
            self.highlighted = None
            return

        self.highlight_index = 0
        self.rv.selection_start = self.rv.selection_end = self.highlighted_list[self.highlight_index]
        self._set_selection_end()
        
        self.rv.scroll_to_offset(self.rv.selection_start)
        self.minimap.redraw()
        self.rv.redraw_children()

    def end_highlight(self):
        self.highlighted = None
        self.highlight_index = -1
        self.highlighted_list = []
        self.minimap.redraw()
        self.rv.reset_selection()
        self.rv.redraw_children()

    def select_next_highlight(self, offset: int = 1):
        if self.highlighted is None: return
        self.highlight_index += offset
        self.highlight_index = min(max(self.highlight_index, 0), len(self.highlighted_list) - 1)
        self.rv.selection_start = self.rv.selection_end = self.highlighted_list[self.highlight_index]
        self._set_selection_end()
        self.rv.scroll_to_offset(self.rv.selection_start)
        self.rv.redraw_children()

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
    
    def get_sections(self) -> Iterable[Section]:
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

class ListingViewLabel(TreeViewLabel):
    parent: "FunctionListingDetails"

    def refresh(self): pass

class InOutViewLabelMem(ListingViewLabel):
    def __init__(self, mem_list: list[int], **kwargs):
        self.mem_list = mem_list
        super().__init__(**kwargs)
        self.refresh()

    def refresh(self):
        label = app().project.ob.label(self.mem_list[0])
        if len(self.mem_list) > 1:
            text = f"{self.mem_list[0]:X}-{self.mem_list[-1]:X}"
        else:
            text = f"{self.mem_list[0]:X}"

        if label: text = f"{label.name} ({text})"

        self.text = text

class ClobberViewLabel(ListingViewLabel):
    def __init__(self, ep: int, do_group: bool, **kwargs):
        self.ep = ep
        self.do_group = do_group
        super().__init__(**kwargs)
        self.refresh()

    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        app().scroll_to_offset(self.ep, main_panel=self.parent.container.listing, history=False)
        return True

class ClobberViewLabelCall(ClobberViewLabel):
    def __init__(self, ep: int, do_group: bool, call: Instruction, **kwargs):
        self.call = call
        super().__init__(ep, do_group, **kwargs)

    def refresh(self):
        self.text=f"{self.ep:X}: {insnentry_to_str(self.call.entry, app().project.ob)}"

class ClobberViewLabelMem(ClobberViewLabel):

    def __init__(self, ep: int, do_group: bool, mem_list: list[int], **kwargs):
        self.mem_list = mem_list
        super().__init__(ep, do_group, **kwargs)

    def refresh(self):
        label = app().project.ob.label(self.mem_list[0])
        if len(self.mem_list) > 1:
            text = f"{self.mem_list[0]:X}-{self.mem_list[-1]:X}"
        else:
            text = f"{self.mem_list[0]:X}"

        if label: text = f"{label.name} ({text})"
        if not self.do_group: text = f"{self.ep:X}: {text}"
        self.text = text

class FunctionListingDetails(KWidget, TreeView):
    parent: ScrollView

    def __init__(self, function: Function, container: "FunctionListingContainer", **kwargs):
        self.fun = function
        self.container = container

        super().__init__(hide_root=True, size_hint=(1, None), **kwargs)

        node = TreeViewLabel(text="Name", is_open=True)
        self.add_node(node)
        self.name_node = TreeViewLabel(text=function.name)
        self.add_node(self.name_node, node)

        node = TreeViewLabel(text="Address", is_open=True)
        self.add_node(node)
        self.add_node(TreeViewLabel(text=format(function.ep, "X")), node)

        node = TreeViewLabel(text="Frequency", is_open=True)
        self.add_node(node)
        self.add_node(TreeViewLabel(text=str(function.frequency)), node)

        node = TreeViewLabel(text="Complexity", is_open=True)
        self.add_node(node)
        self.add_node(TreeViewLabel(text=str(len(function.blocks))), node)

        def group_mems(mems: list[int]) -> list[list[int]]:
            return [
                [num for _, num in g]  # extract only the value
                for _, g in groupby(enumerate(sorted(mems)), lambda x: x[1] - x[0])
            ]
        
        def is_call(ep: int) -> Instruction | None:
            for block in function.blocks.values():
                for inst in block.insn:
                    if inst.entry.pc == ep and inst.entry.opcode in ("CALL", "CALR"):
                        return inst
            return None

        assert function.state is not None

        def add_registers(name: str, registers: set[Union[Reg, int]]):
            node = TreeViewLabel(text=f"{name} Registers")
            self.add_node(node)
            for reg in sorted([reg for reg in registers if isinstance(reg, Reg)], key=lambda r: r.addr):
                self.add_node(TreeViewLabel(text=str(reg), font_name=FONT_NAME), node)

            node = TreeViewLabel(text=f"{name} Memory")
            self.add_node(node)

            mems = [mem for mem in registers if isinstance(mem, int)]
            for mem_list in group_mems(mems):
                self.add_node(InOutViewLabelMem(mem_list=mem_list, font_name=FONT_NAME), node)

        add_registers("Input", function.state.input)
        add_registers("Output", function.state.output)
        
        node = TreeViewLabel(text=f"Clobbers")
        self.add_node(node)
        for ep, group in groupby(sorted(function.state.clobbers, key=lambda e: e[2]), key=lambda e: e[2]):
            group = list(group)
            node2 = node
            do_group = False
            call = is_call(ep)
            if call:
                node2 = ClobberViewLabelCall(ep, do_group, call, font_name=FONT_NAME)
                self.add_node(node2, node)
                do_group = True
            
            regs: list[Reg] = []
            mems: list[int] = []
            for _, value, _ in group:
                if isinstance(value, Reg):
                    regs.append(value)
                else:
                    mems.append(value)

            for reg in regs:
                text = str(reg) 
                if not do_group: text = f"{ep:X}: {text}"
                self.add_node(ClobberViewLabel(ep, do_group, text=text, font_name=FONT_NAME), node2)

            for mem_list in group_mems(mems):
                self.add_node(ClobberViewLabelMem(ep, do_group, mem_list=mem_list, font_name=FONT_NAME), node2)

            self.bind(minimum_size=lambda _, value: setattr(self, 'height', value[1]))

    def toggle_node(self, node):
        super().toggle_node(node)
        self.refresh()

    def refresh(self):
        for label in iter_all_children_of_type(self, ListingViewLabel):
            label.refresh()

        self.name_node.text = self.fun.name

    def serialize(self, data: dict):
        open_state = []
        node: TreeViewLabel
        for node in self.iterate_all_nodes():
            open_state.append({
                "is_open": node.is_open
            })
        data["tree"] = {
            "open_state": open_state,
            "scroll_y": self.parent.scroll_y,
            "splitter_width": self.container.splitter.width,
            "toggled": self.container.listing.toggled
        }

    def deserialize_post(self, data: dict):
        if "tree" in data:
            tree = data["tree"]
            if "open_state" in tree:
                for node, node_data in zip(self.iterate_all_nodes(), tree["open_state"]):
                    node.is_open = node_data.get("is_open", node.is_open)
            if "scroll_y" in tree:
                self.parent.scroll_y = tree["scroll_y"]
            if "splitter_width" in tree:
                self.container.splitter.width = tree["splitter_width"]
            if "toggled" in tree:
                toggled = tree["toggled"]
                self.container.listing.toggled = toggled
                if toggled:
                    self.container.expand(True)
                

class FunctionListingContainer(BoxLayout):
    listing: "FunctionListing"

    def __init__(self, function: Function, **kwargs):
        self.fun = function
        super().__init__(**kwargs)

        self.details = FunctionListingDetails(function, self)
        self.splitter = Splitter(size_hint=(None, 1), width=dp(400), sizable_from='right')
        scrollview = ScrollView(size_hint=(1, 1))
        scrollview.add_widget(self.details)
        self.splitter.add_widget(scrollview)
        self.add_widget(self.splitter)

        self.listing = FunctionListing(function)
        self.add_widget(self.listing)

    def expand(self, toggled: bool):
        if toggled:
            self.remove_widget(self.splitter)
        else:
            self.add_widget(self.splitter, index=1)

class FunctionListing(ListingPanel):
    parent: FunctionListingContainer

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
    
    def toggle(self):
        self.toggled = not self.toggled
        self.parent.expand(self.toggled)


class ListingTab(SerializableTab):
    _content: FunctionListingContainer

    def __init__(self, text: str, **kwargs):
        super().__init__(text=text, closeable=True, source="ui/resources/code-listing.png", **kwargs)

    @property
    def content(self) -> FunctionListing:
        return self._content.listing

    def serialize(self) -> dict:
        res = super().serialize()
        res["function"] = self.content.fun.ep
        self.content.serialize(res)
        self._content.details.serialize(res)
        return res
    
    def refresh(self, **kwargs):
        self.content.rv.redraw_children()
        self._content.details.refresh()
        self.text = self.content.fun.name
    
    @classmethod
    def deserialize(cls, data: dict) -> "ListingTab":
        ep = data["function"]
        functions = app().project.functions
        assert functions
        fun = functions[ep]
        tab = ListingTab(fun.name)
        listing = FunctionListingContainer(fun)
        tab.add_widget(listing)
        return tab

    def deserialize_post(self, data: dict):
        self.content.deserialize_post(data)
        self._content.details.deserialize_post(data)

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
    content: ListingPanel

    def refresh(self, **kwargs):
        self.content.rv.redraw_children()

    def serialize(self) -> dict:
        res = super().serialize()
        self.content.serialize(res)
        return res
    
    @classmethod
    def deserialize(cls, dict) -> "MainDockTab":
        tab = MainDockTab(text=app().project.filename)
        panel = ListingPanel(is_root=True)
        tab.add_widget(panel)
        app().dis_panel = panel
        return tab
    
    def deserialize_post(self, dict):
        self.content.deserialize_post(dict)

class DisApp(App):
    _any_hovered = False

    def __init__(self, project: Project):
        super().__init__()
        self.project = project

        self.goto_position: GotoPosition
        self.window: MainWindow
        self.back_button: IconButton
        self.forward_button: IconButton
        self.y_splitter: Splitter
        self.analyzer_panel: AnalyzerPanel | None = None
        self.dis_panel: ListingPanel
        self.analyzer_filter: AnalyzerFilter
        self.main_dock: Dock
        self.rename_input: RenameInput

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
        self.main_dock = self.window.ids["main_dock"]
        self.rename_input = self.window.ids["rename_input"]
    
        self.back_button.bind(on_press=lambda w: self.go_back())
        self.forward_button.bind(on_press=lambda w: self.go_forward())

        build_menu()
        if not self.load_ui_state():
            self.main_dock.clear_widgets()
            self.dis_panel = ListingPanel(is_root=True)
            tab = MainDockTab(text=self.project.filename)
            tab.add_widget(self.dis_panel)
            self.main_dock.add_tab(tab)

        return self.window
    
    def load_ui_state(self) -> bool:
        file = self.get_project_ui_file()
        if not file.exists(): return False
        logging.info("Config: Loading ui state from %s", file)

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
                    BoxLayout.add_widget(dock, dock.first_panel)
                    deserialize(root, dock.first_panel, data["first"])
                
                if "splitter_pos" in data:
                    dock.splitter = DockSplitter("left" if dock.orientation == "horizontal" else "top")
                    BoxLayout.add_widget(dock, dock.splitter)
                
                if "tab" in data:
                    dock.panel = DockPanel(root, dock)
                    BoxLayout.add_widget(dock, dock.panel)

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

                    if dock.orientation == "horizontal":
                        dock.splitter.width = data["splitter_pos"]
                    else:
                        dock.splitter.height = data["splitter_pos"]

            deserialize(self.main_dock, self.main_dock, data)
            if active_tab: active_tab.select()
            return True
        except:
            logging.error("Error loading UI state:")
            traceback.print_exc()

        return False

    def save_ui_state(self):
        file = self.get_project_ui_file()
        logging.info("Config: Saving ui state to %s", file)
        file.parent.mkdir(parents=True, exist_ok=True)

        def serialize(panel: BaseDock) -> dict[str, Any]:
            res = {}
            # TODO This is a hack to avoid extra nesting
            if panel.first_panel and not panel.second_panel:
                panel = panel.first_panel

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
                if panel.orientation == "horizontal":
                    res["splitter_pos"] = panel.splitter.width
                else:
                    res["splitter_pos"] = panel.splitter.height

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
    
    def scroll_to_label(self, label: int | str, main_panel: ListingPanel | None = None):
        sections = self.project.sections.values()
        section: Section
        for section in sections:
            if section.labels:
                if (type(label) is int and section.offset == label) or (type(label) is str and section.labels[0].name == label):
                    logging.info("Goto label: %s at %s", label, format(section.offset, "X"))
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
    
    def scroll_to_offset(self, offset: int, main_panel: ListingPanel | None = None, history = True):
        rv = main_panel.rv if main_panel else self.dis_panel.rv

        self.switch_to_listing(main_panel)
        found_pos = rv.scroll_to_offset(offset, history=history)
        rv.reset_selection()
        
        # Try again with main panel if we can't find the symbol in the current panel
        if not found_pos:
            if main_panel: 
                self.scroll_to_offset(offset, None, history=history)
            else:
                raise ValueError("Invalid location")
            
    def find_main_panel(self) -> MainDockTab:
        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, MainDockTab):
                return tab
        assert False, "No main panel found"
        
    def switch_to_listing(self, main_panel: ListingPanel | None = None):
        if main_panel:
            for tab in self.main_dock.iterate_panels():
                if tab.content == main_panel:
                    tab.select()
                    break
            else: 
                if isinstance(main_panel, FunctionListing):
                    tab = ListingTab(text=main_panel.fun.name)
                    tab.add_widget(main_panel.parent)
                    self.main_dock.add_tab(tab, reverse=True)
        else:
            self.find_main_panel().select()
    
    def open_function_graph_from_label(self, ep: int):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_graph_from_label(ep))
            return
        for fun in self.project.functions.values():
            if ep in fun.blocks:
                self.open_function_graph(fun.ep, callback=lambda panel: panel.content.move_to_location(ep))
                return
            
    def open_function_listing_from_label(self, ep: int):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_listing_from_label(ep))
            return
        for fun in self.project.functions.values():
            if ep in fun.blocks:
                self.open_function_listing(fun.ep)
                return

    def find_function(self, fun_name: str | int):
        if not self.project.functions: return None
        if type(fun_name) is int:
            return self.project.functions.get(fun_name, None)
        else:
            return next(filter(lambda f: f.name == fun_name, self.project.functions.values()), None)

    def open_function_listing(self, ep: int, highlight_callee: int | None = None, highlight_caller: int | None = None):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_listing(ep, highlight_callee, highlight_caller))
            return
        
        if highlight_caller is not None:
            # Callers require going over multiple functions so we can't open them in a function listing
            main_panel = self.find_main_panel()
            main_panel.select()
            fun = self.find_function(ep)
            if not fun: return
            main_panel.content.highlight(fun, highlight_callee, highlight_caller)
            return
        
        fun = self.find_function(ep)
        if not fun: return

        panel: FunctionListingContainer | None = None
        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, ListingTab) and tab.content.fun == fun:
                tab.content.highlight(fun, highlight_callee, highlight_caller)
                tab.select()
                panel = tab.content.parent
                break
        
        if not panel:
            tab = ListingTab(text=fun.name)
            panel = FunctionListingContainer(fun)
            if highlight_callee is not None or highlight_caller is not None:
                Clock.schedule_once(lambda dt: panel.listing.highlight(fun, highlight_callee, highlight_caller), 0)
            tab.add_widget(panel)

            app().main_dock.add_tab(tab, reverse=True)

        app().update_position_history(NavigationListing(panel.listing, fun.ep))
    
    def open_function_graph(self, ep: int, rescale=True, callback: Callable[[GraphTab], None] | None = None):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_function_graph(ep, rescale, callback))
            return

        fun = self.find_function(ep)
        if not fun: return

        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, GraphTab) and tab.content.fun == fun:
                tab.select()
                return
        
        tab = GraphTab(fun.name)
        panel = FunctionPanel(fun, tab)
        tab.add_widget(panel)

        app().main_dock.add_tab(tab, reverse=True)

        def after(dt):
            panel.move_to_initial_pos()
            if callback: callback(tab)

        Clock.schedule_once(after, 0)

    def open_call_graph(self, ep: int):
        if not self.project.functions:
            self.analyze_functions(lambda: self.open_call_graph(ep))
            return

        fun = self.find_function(ep)
        if not fun: return

        for tab in self.main_dock.iterate_panels():
            if isinstance(tab, CallGraphTab) and tab.fun == fun:
                tab.select()
                return
        
        tab = CallGraphTab(fun)
        panel = CallGraphPanel(fun, tab)
        tab.add_widget(panel)
        Clock.schedule_once(lambda dt: panel.move_to_initial_pos(), 0)

        app().main_dock.add_tab(tab, reverse=True)

    def open_rename(self, ep: int, x: int, y: int):
        label = self.project.ob.label(ep)
        if not label: return
        self.rename_input.show(ep, x, y)

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
        elif keycode == 227 and sys.platform == "darwin" or keycode == 224 and sys.platform != "darwin": 
            self.ctrl_down = True
            RV.update_cursor()
        elif keycode == 41: 
            self.global_event_bus.dispatch("on_escape")
            return True
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 225: self.shift_down = False
        if keycode == 227 and sys.platform == "darwin" or keycode == 224 and sys.platform != "darwin":
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

        on_mouse_move(self.window, pos)
        RV.global_mouse_move(window, pos)

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
