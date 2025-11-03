
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.clock import Clock

from tcls_900.tlcs_900 import Reg

from .main import HideableTextInput, EscapeTrigger, app, iter_all_children_of_type
from .main_menu import MenuHandler, MenuItem
from .context_menu import show_context_menu, ContextMenuBehavior
from .table.table import DataTableRow, ResizableRecycleTable
from .dock.dock import DockTab, SerializableTab

class AnalyzerTab(SerializableTab):
    content: "AnalyzerPanel"

    def __init__(self, **kwargs):
        super().__init__(text="Functions", closeable=True, source="ui/resources/functions.png", **kwargs)

    def serialize(self) -> dict:
        data = super().serialize()
        data["scroll_x"] = self.content.scrollview.scroll_x
        data["scroll_y"] = self.content.table.body.scroll_y
        data["ordered_by"] = self.content.table.ordered_by
        data["reverse"] = self.content.table.reverse

        return data

    def deserialize_post(self, data: dict):
        self.content.scrollview.scroll_x = data.get("scroll_x", 0)
        self.content.table.body.scroll_y = data.get("scroll_y", 1)

        self.content.table.ordered_by = data.get("ordered_by", -1)
        self.content.table.reverse = data.get("reverse", -1)
        self.content.table.sort_data()

        app().analyzer_filter = self.content.ids["analyzer_filter"]
        
    @classmethod
    def deserialize(cls, data: dict) -> "AnalyzerTab":
        tab = AnalyzerTab()
        analyzer = AnalyzerPanel(tab)
        app().analyzer_panel = analyzer
        tab.add_widget(analyzer)
        return tab

class AnalyzerFilter(HideableTextInput, EscapeTrigger):
    def on_escape(self, obj):
        if app().analyzer_panel and app().main_dock.active_content == app().analyzer_panel:
            self.hide()
            panel = app().analyzer_panel
            assert panel
            panel.ids["analyzer_table"].filter()

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        panel = app().analyzer_panel
        assert panel
        super().keyboard_on_key_down(window, keycode, text, modifiers)
        Clock.schedule_once(lambda dt: panel.ids["analyzer_table"].filter(self.text), 0)


HEADER_NAMES = ["name", "navigation", "address", "frequency", "complexity", "input", "clobber", "output", "stack"]
COLUMN_WIDTHS = [dp(100), dp(100), dp(100), dp(100), dp(100), dp(200), dp(200), dp(200), dp(100)]

class AnalyzerButtons(RelativeLayout):
    parent: "AnalyzerTableRow"
    def __init__(self, column: int, **kw):
        self.column = column
        super().__init__(**kw)

    def on_press(self, action: str):
        data = self.parent.data
        if action == "goto":
            app().scroll_to_label(data[0])
        elif action == "graph":
            app().open_function_graph(data[0])
        elif action == "listing":
            app().open_function_listing(data[0])
        elif action == "calls":
            app().open_call_graph(data[0])

class AnalyzerTableRow(ContextMenuBehavior, DataTableRow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    @property
    def first_label(self) -> Widget:
        return self.children[-1]

    def new_data_cell(self, index) -> Widget:
        if index == 1: return AnalyzerButtons(index)
        return super().new_data_cell(index)
    
class AnalyzerPanel(RelativeLayout):
    def __init__(self, tab: DockTab, **kw):
        self.tab = tab
        self.table: AnalyzerTable
        self.scrollview: ScrollView
        super().__init__(**kw)

    def on_kv_post(self, base_widget):
        self.scrollview = self.ids["scroll_view"]
        self.table = self.ids["analyzer_table"]

class AnalyzerTable(ResizableRecycleTable):
    def __init__(self, **kwargs):
        super().__init__(headers = HEADER_NAMES, data = [], column_widths=COLUMN_WIDTHS, cols=5, **kwargs)
        self.viewclass = "AnalyzerTableRow"
        self.original_data = []

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.update_data()

    def update_data(self):
        project = app().project
        assert project.functions is not None
        self.original_data = []
        for fun in project.functions.values():
            if not fun.state: continue
            row = []
            # name
            row.append(fun.name)
            # Row for buttons, no data
            row.append(0)
            # address
            row.append(format(fun.ep, "X"))
            # frequency
            row.append(len(fun.callers))
            # complexity
            row.append(len(fun.blocks))
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
            #output registers
            row.append(", ".join(map(str, filter(lambda r: isinstance(r, Reg), fun.state.output))))
            #stack
            if fun.underflow:
                row.append("underflow")
            elif len(fun.state.stack) == 0:
                row.append("empty")
            else:
                row.append("overflow")

            self.original_data.append(row)

        self.data = self.original_data.copy()
        self.body.update_data()

    def filter(self, text: str | None = None):
        self.data = self.original_data.copy()
        if text is not None: 
            self.data = list(filter(lambda row: any(map(lambda r: text.casefold() in str(r).casefold(), row)), self.data))
        self.body.update_data()