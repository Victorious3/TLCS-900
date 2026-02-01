from typing import Iterable, Union, cast
from itertools import groupby
from pytreemap import TreeSet
import logging

from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.splitter import Splitter
from kivy.uix.textinput import TextInput
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.treeview import TreeView, TreeViewLabel
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.properties import BooleanProperty, ObjectProperty

from disapi import insnentry_to_str
from tcls_900.tlcs_900 import Mem, Reg

from .kivytypes import KWidget
from .minimap import Minimap
from .project import Function, Section, Instruction
from .sections import RV, ScrollBar, SearchInput
from .main import app, FONT_NAME, iter_all_children_of_type
from .arrow import ArrowRenderer

from .dock.dock import SerializableTab

class ListingPanelBase(Widget):
    is_root: bool = BooleanProperty(False)

    def __init__(self, **kw):
        self.rv: RV = cast(RV, None)
        self.arrows: ArrowRenderer = cast(ArrowRenderer, None)
        self.scrollbar: ScrollBar = cast(ScrollBar, None)
        self.search_input: SearchInput = cast(SearchInput, None)
        self.search_spinner: Spinner = cast(Spinner, None)

        self.search_item: str | bytes | None = None
        self.highlighted: int | None = None
        self.highlighted_list: list[int] = []
        self.highlighted_set: TreeSet = TreeSet()
        self.highlight_index = -1

        Window.bind(on_key_down=self._keydown)
        super().__init__(**kw)

    def toggle(self): pass

    def update(self): pass

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
        if isinstance(self.search_item, bytearray):
            self.rv.selection_end = self.rv.selection_start + len(self.search_item) - 1
        else:
            sections = self.get_sections()
            for s in sections: 
                for insn in s.instructions:
                    if insn.entry.pc == self.rv.selection_start:
                        self.rv.selection_end = insn.entry.pc + insn.entry.length - 1
                        break

    def highlight_list(self, highlights: list[int], search_string: str | bytearray):
        if len(highlights) == 0:
            self.end_highlight()
            return

        self.highlighted = highlights[0]
        self.highlighted_list = highlights
        self.search_item = search_string
        self._highlight_post()

    def highlight(self, fun: Function, callee: int | None = None, caller: int | None = None):
        self.search_item = None
        self.highlighted = callee if callee is not None else caller
        if callee:
            self.highlighted_list = list(set([index for index, callee in fun.callees if callee == self.highlighted]))
        elif caller:
            self.highlighted_list = list(set([index for index, _ in fun.callers]))

        logging.info("Highlighting %d occurrences of %s of function %s", len(self.highlighted_list), 
                     "callee" if callee is not None else "caller", fun.name)
        self._highlight_post()
        
    def _highlight_post(self):
        self.highlighted_set = TreeSet()
        self.highlighted_list.sort()
        if len(self.highlighted_list) == 0:
            self.highlighted = None
            return
        
        for i in self.highlighted_list:
            self.highlighted_set.add(i)

        self.highlight_index = 0
        self.rv.selection_start = self.rv.selection_end = self.highlighted_list[self.highlight_index]
        self._set_selection_end()
        
        self.rv.scroll_to_offset(self.rv.selection_start)
        self.update()
        self.rv.redraw_children()

    def end_highlight(self):
        self.search_item = None
        self.highlighted = None
        self.highlight_index = -1
        self.highlighted_list = []
        self.highlighted_set.clear()
        self.update()
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
        self.arrows = self.ids["arrows"]
        self.scrollbar = self.ids["scrollbar"]

        search = self.ids["search_container"]
        self.search_input = search.ids["search_input"]
        self.search_spinner = search.ids["search_spinner"]

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

class ListingPanel(ListingPanelBase, RelativeLayout):
    minimap: Minimap = ObjectProperty(None)

    def __init__(self, **kw):
        super().__init__(**kw)

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.minimap = self.ids["minimap"]

    def update(self):
        self.minimap.update()

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
