from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.stencilview import StencilView
from kivy.uix.label import Label
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.properties import ListProperty, NumericProperty, StringProperty, ObjectProperty
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.metrics import dp

from ui.main import app

Builder.load_file("ui/table/table.kv")

class ColumnLabel(Label): pass

class SortableHeader(ButtonBehavior, Label):
    col_index = NumericProperty(0)
    direction = NumericProperty(0)

    def __init__(self, table, **kwargs):
        super().__init__(**kwargs)
        self.table = table

    def on_press(self):
        self.table.sort_by_column(self.col_index)
        
class ColumnResizer(ButtonBehavior, Widget):
    col_index = NumericProperty(0)
    _hovered: bool = False

    def __init__(self, table: "ResizableRecycleTable", **kwargs):
        super().__init__(**kwargs)
        self.table = table
        self.size_hint_x = None
        self.width = dp(5)
        self._start_x = None

    def on_mouse_move(self, pos):
        super().on_mouse_move(pos) # type: ignore
        if self._hovered and not app().any_hovered:
            app().set_hover()
            Window.set_system_cursor("size_we")  # horizontal resize cursor

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._start_x = touch.x
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._start_x is not None:
            delta = touch.x - self._start_x
            self._start_x = touch.x
            self.table.resize_column(self.col_index, delta)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        self._start_x = None
        return super().on_touch_up(touch)
    
class DataTableRow(RecycleDataViewBehavior, BoxLayout):
    data = ListProperty(None)
    row = NumericProperty(0)
    column_widths = ListProperty(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initialized = False

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)
        if not self.initialized:
            for i, column in enumerate(self.data):
                self.add_widget(self.new_data_cell(i))
            self.initialized = True

    def new_data_cell(self, index) -> Widget:
        return DataTableCell(column=index)
    
class DataTableCell(Label):
    column = NumericProperty(0)
        
class TableBody(RecycleView):
    def update_data(self):
        data = []
        for i, row in enumerate(self.parent.parent.data):
            data.append({"data": row, "row": i, "column_widths": self.parent.parent.column_widths})

        self.data = data

class TableHeader(BoxLayout): pass

class ResizableRecycleTable(StencilView, BoxLayout):
    column_widths = ListProperty([])
    cols = NumericProperty(0)
    viewclass = StringProperty("DataTableRow")

    def __init__(self, headers, data, column_widths = None, **kwargs):
        super().__init__(orientation='vertical', **kwargs)
        self.headers = headers
        self.data = data
        self.column_widths = column_widths or [dp(150) for _ in headers]

        self.header_row = self._build_header()
        self.add_widget(self.header_row, index=1)

        self.reverse = -1
        self.ordered_by = -1

    def is_pos_inside_of_body(self, pos):
        return self.body.parent.collide_point(*self.body.parent.to_widget(*pos))

    @property
    def body(self) -> TableBody:
        return self.children[0].children[0]

    def _build_header(self):
        header = TableHeader()
        for i, header_text in enumerate(self.headers):
            header.add_widget(SortableHeader(text=header_text, col_index=i, table=self, size_hint_x=None, width=self.column_widths[i]))
            if i < len(self.headers) - 1:
                header.add_widget(ColumnResizer(self, col_index=i))
        return header

    def resize_column(self, index, delta):
        # Only adjust if not the last column
        if index >= len(self.column_widths) - 1:
            return

        new_width = self.column_widths[index] + delta
        next_width = self.column_widths[index + 1] - delta

        # Prevent columns from being too narrow
        if new_width < dp(50) or next_width < dp(50):
            return

        self.column_widths[index] = new_width
        self.column_widths[index + 1] = next_width
        
        self._update_header()
        self.body.refresh_from_data()

    def _update_ui(self):
        self._update_header()
        self.body.update_data()

    def _update_header(self):
        i = 0
        for widget in reversed(self.header_row.children):
            if isinstance(widget, SortableHeader):
                widget.width = self.column_widths[i]
                if self.ordered_by == i:
                    widget.direction = -1 if self.reverse == i else 1
                else: widget.direction = 0
                i += 1

    def sort_data(self):
        self.data.sort(key=lambda row: str(row[self.ordered_by]), reverse=self.reverse == -1)
        self._update_ui()

    def sort_by_column(self, col_index):
        self.data.sort(key=lambda row: str(row[col_index]), reverse=self.reverse == col_index)
        self.reverse = -1 if self.reverse == col_index else col_index
        self.ordered_by = col_index
        self._update_ui()
