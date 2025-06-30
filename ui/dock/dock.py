from enum import Enum
from typing import Generator, cast

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.splitter import Splitter
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock

from ui.main import KWidget

Builder.load_file("ui/dock/dock.kv")

class Orientation(Enum):
    VERTICAL = 0
    HORIZONTAL = 1

class DockPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._tab_strip = TabStrip(size_hint=(None, None), height=dp(25), width=dp(100))
        self._scroll_strip = ScrollView(do_scroll_x=True, do_scroll_y=False, size_hint=(1, None), height=dp(25), always_overscroll=False, scroll_timeout=0)
        self._scroll_strip.add_widget(self._tab_strip)
        self._current_widget: DockTab | None = None
        super().add_widget(self._scroll_strip)

    def add_widget(self, widget: "DockTab"):
        widget.dock_panel = self
        self._tab_strip.add_widget(widget)
        if self._current_widget:
            super().remove_widget(self._current_widget.content)
        self._current_widget = widget
        super().add_widget(self._current_widget.content)
        self._calculate_tab_size()

    def remove_widget(self, widget: "DockTab"):
        widget.dock_panel = None
        # If we currently select said widget we need to switch to the previous one if possible
        if self._current_widget == widget:
            super().remove_widget(widget.content)
            tab_list = self.tab_list
            index = tab_list.index(widget)
            if len(tab_list) > 1:
                self._current_widget = tab_list[max(0, index - 1)]
                super().add_widget(self._current_widget.content)

        self._tab_strip.remove_widget(widget)
        self._calculate_tab_size()

    def select_widget(self, widget: "DockTab"):
        assert widget.dock_panel == self
        if self._current_widget:
            super().remove_widget(self._current_widget.content)
        self._current_widget = widget
        super().add_widget(self._current_widget.content)

    def _calculate_tab_size(self):
        w = 0
        for tab in self.tab_list:
            w += tab.width
        self._tab_strip.width = w

    @property
    def tab_list(self) -> "list[DockTab]":
        return self._tab_strip.children 
    
class TabStrip(GridLayout):
    def __init__(self, **kwargs):
        super().__init__(rows=1, **kwargs)

class DockTab(ToggleButton):
    def __init__(self, **kwargs):
        self.root: Dock | None = None
        self.dock_panel: DockPanel | None = None
        super().__init__(**kwargs)

    def add_widget(self, widget: Widget):
        self.content = widget

    def remove_widget(self, widget: Widget):
        self.content = None

    def on_press(self):
        if self.dock_panel:
            self.dock_panel.select_widget(self)
        if self.root:
            self.root.active_panel = self
            for panel in self.root.iterate_panels():
                if panel == self: continue
                panel.state = "normal" # This value doesn't actually change anything, it just causes a refresh of the property

    def on_touch_down(self, touch):
        if self.root:
            self.root.dragged_panel = self

        return super().on_touch_down(touch)
    
    def on_touch_up(self, touch):
        if self.root:
            self.root.dragged_panel = None
            self.root.draw_dragged_panel()

        return super().on_touch_up(touch)

class BaseDock(BoxLayout):
    def __init__(self, root: "Dock | None", **kwargs):
        super().__init__(**kwargs)
        self.first_panel: DockPanel = DockPanel()
        self.second_panel: Splitter | None = None
        self.root = root

        super().add_widget(self.first_panel)

    def iterate_panels(self) -> Generator[DockTab, None, None]:
        yield from self.first_panel.tab_list
        if self.second_panel:
            second_panel = self.second_panel.children[0]
            if isinstance(second_panel, BaseDock):
                yield from second_panel.iterate_panels()
            elif isinstance(second_panel, DockPanel):
                yield from second_panel.tab_list

    @property
    def active_panel(self) -> DockTab | None:
        if self.root: return self.root.active_panel

    @active_panel.setter
    def active_panel(self, value: DockTab):
        if self.root: self.root.active_panel = value

    def add_panel(self, panel: DockTab):
        if self.second_panel:
            second_panel = self.second_panel.children[0]
            if isinstance(second_panel, BaseDock):
                second_panel.add_panel(panel)
            elif isinstance(second_panel, DockPanel):
                panel.root = self.root or cast(Dock, self)
                second_panel.add_widget(panel)
                panel.on_press()
        else:
            panel.root = self.root or cast(Dock, self)
            self.first_panel.add_widget(panel)
            panel.on_press()

    def split(self, panel: DockTab, orientation = Orientation.HORIZONTAL):
        if self.second_panel:
            second_panel = self.second_panel.children[0]
            if isinstance(second_panel, BaseDock):
                second_panel.split(panel, orientation)
            elif isinstance(second_panel, DockPanel):
                second = second_panel
                self.second_panel.remove_widget(second)
                
                new_second = ChildDock(self.root or cast(Dock, self))
                new_second.remove_widget(new_second.first_panel)

                new_second.first_panel = second
                new_second.add_widget(second)
                new_second.split(panel, orientation)

                self.second_panel.add_widget(new_second)
        else:
            new_second = DockPanel()
            panel.root = self.root or cast(Dock, self)
            new_second.add_widget(panel)
            panel.on_press() # This selects the current panel

            sizable_from = "left" if orientation == Orientation.HORIZONTAL else "top"
            if orientation == Orientation.VERTICAL:
                self.orientation = "vertical"

            self.second_panel = Splitter(sizable_from=sizable_from, keep_within_parent=True, max_size=dp(10e10))
            self.second_panel.add_widget(new_second)
            self.add_widget(self.second_panel)

class ChildDock(BaseDock):
    def __init__(self, root: "Dock", **kwargs):
        super().__init__(root, **kwargs)

class Dock(KWidget, BaseDock):
    def __init__(self, **kwargs):
        super().__init__(None, **kwargs)
        self._active_panel: DockTab | None = None
        self.dragged_panel: DockTab | None = None
        Window.bind(mouse_pos=lambda *args: self.draw_dragged_panel())
        Window.bind(on_mouse_up=self._on_mouse_up)

    def draw_dragged_panel(self):
        self.canvas.after.clear()
        if not self.dragged_panel: return
        with self.canvas.after:
            Color(*get_color_from_hex("#585858D0"))
            Rectangle(pos=Window.mouse_pos, size=(dp(150), dp(50)))

    def _on_mouse_up(self, window, x, y, button, modifiers):
        self.dragged_panel = None

    @property
    def active_panel(self) -> DockTab | None:
        return self._active_panel

    @active_panel.setter
    def active_panel(self, value: DockTab):
        self._active_panel = value