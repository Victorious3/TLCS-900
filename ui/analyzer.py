
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.uix.relativelayout import RelativeLayout
from kivy.metrics import dp

from tcls_900.tlcs_900 import Reg

from .main import HideableTextInput, EscapeTrigger, app, iter_all_children_of_type
from .main_menu import MenuHandler, MenuItem
from .context_menu import show_context_menu
from .table.table import DataTableRow, ResizableRecycleTable

class AnalyzerFilter(HideableTextInput, EscapeTrigger):
    def on_escape(self, obj):
        if app().active == app().analyzer_panel:
            self.hide()

    def keyboard_on_textinput(self, window, text):
        super().keyboard_on_textinput(window, text)
        app().analyzer_panel.filter(self.text)


HEADER_NAMES = ["name", "address", "complexity", "input", "clobber", "output"]
COLUMN_WIDTHS = [dp(100), dp(100), dp(100), dp(250), dp(250), dp(250)]

class AnalyzerTableRow(DataTableRow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self.on_mouse_move)
    
    @property
    def first_label(self) -> Widget:
        return self.children[-1]

    def on_touch_up(self, touch):
        inside = self.first_label.collide_point(touch.x, touch.y)
        if inside:
            if touch.button == "right":
                data = self.data
                class Handler(MenuHandler):
                    def on_select(self, item):
                        if item == "goto": app().scroll_to_label(data[0])
                        elif item == "graph": app().open_function_graph(data[0])
                
                show_context_menu(Handler(), [
                    MenuItem("goto", "Go to function"),
                    MenuItem("graph", "Open function graph")
                ])
                return True
            
        return super().on_touch_up(touch)

    def on_touch_down(self, touch):
        inside = self.first_label.collide_point(touch.x, touch.y)
        if inside:
            if touch.button == "left":
                app().scroll_to_label(self.data[0])
                return True
        return super().on_touch_down(touch)
    
    def on_mouse_move(self, window, pos):
        if self.get_root_window() == None: return
        inside = self.first_label.collide_point(*self.first_label.to_widget(*pos))
        if inside:
            # Ugly UI hack
            table: AnalyzerTable = next(iter_all_children_of_type(app().analyzer_panel, AnalyzerTable))
            if not table.is_pos_inside_of_body(pos): return

        if inside and not app().any_hovered:
            app().set_hover()
            Window.set_system_cursor("hand")
    
class AnalyzerPanel(RelativeLayout):
    def on_touch_down(self, touch):
        if self.collide_point(touch.x, touch.y):
            app().active = self
        return super().on_touch_down(touch)

    def close_panel(self):
        app().active = app().dis_panel_container
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
            #complexity
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
            #ouput registers
            row.append(", ".join(map(str, filter(lambda r: isinstance(r, Reg), fun.state.output))))

            self.data.append(row)

        self.body.update_data()