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

class Quadrant(Enum):
    LEFT = 0
    TOP = 1
    RIGHT = 2
    BOTTOM = 3
    CENTER = 4

class DockSplitter(Splitter):
    def __init__(self, sizable_from: str, **kwargs):
        super().__init__(sizable_from=sizable_from, keep_within_parent=True, max_size=dp(10e10), min_size=0, **kwargs)

    @property
    def dock(self) -> "BaseDock":
        return self.children[0]

class DockScrollView(ScrollView):
    SCROLL_STEP = 0.1

    def __init__(self, **kwargs):
        super().__init__(
            do_scroll_x=True, 
            do_scroll_y=False, 
            size_hint=(1, None), 
            height=dp(25), 
            always_overscroll=False, 
            scroll_timeout=0, 
            **kwargs
        )

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and touch.is_mouse_scrolling:
            direction = 1 if touch.button == 'scrolldown' else -1
            self.scroll_x = max(0., min(1., self.scroll_x + direction * self.SCROLL_STEP))
            return True
        return super().on_touch_down(touch)

class DockPanel(KWidget, BoxLayout):
    BORDER_OFFSET = dp(40)

    def __init__(self, root: "Dock", parent_dock: "BaseDock", **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._tab_strip = TabStrip(size_hint=(None, None), height=dp(25), width=dp(100))
        self._scroll_strip = DockScrollView()
        self._scroll_strip.add_widget(self._tab_strip)
        self._current_widget: DockTab | None = None
        self.root = root
        self.parent_dock = parent_dock
        super().add_widget(self._scroll_strip)

        self.drop_quadrant: Quadrant | None = None
        self.drop_tab: int | None = None

        Window.bind(mouse_pos=lambda *args: self.draw_overlay())

    def draw_overlay(self):
        self.canvas.after.clear()
        if not self.root: return
        panel = self.root.dragged_panel
        if not panel: return

        x, y = self.to_local(*Window.mouse_pos)

        self.drop_quadrant = None
        self.drop_tab = None

        if self.pos[0] <= x <= self.pos[0] + self.width:
            sh = self._scroll_strip.height
            if self.pos[1] + self.height - sh <= y <= self.pos[1] + self.height:
                xpos = self.x
                i = None
                for i, tab in enumerate(self._tab_strip.children):
                    if xpos <= x <= xpos + tab.width:
                        break
                    xpos += tab.width
                self.drop_tab = i

                with self.canvas.after:
                    Color(1, 1, 1, 1)
                    Rectangle(pos=(xpos, self.y + self.height - sh), size=(dp(4), sh))

            elif self.pos[1] <= y <= self.pos[1] + self.height:

                with self.canvas.after:
                    Color(*get_color_from_hex("#A1A1A1D0"))
                    if x < self.pos[0] + self.BORDER_OFFSET:
                        Rectangle(pos=(self.x, self.y), size=(self.width / 2, self.height - sh))
                        self.drop_quadrant = Quadrant.LEFT
                    elif x > self.pos[0] + self.width - self.BORDER_OFFSET:
                        Rectangle(pos=(self.x + self.width / 2, self.y), size=(self.width / 2, self.height - sh))
                        self.drop_quadrant = Quadrant.RIGHT
                    elif y < self.pos[1] + self.BORDER_OFFSET:
                        Rectangle(pos=(self.x, self.y), size=(self.width, (self.height / 2) - sh))
                        self.drop_quadrant = Quadrant.BOTTOM
                    elif y > self.pos[1] + self.height - self.BORDER_OFFSET:
                        Rectangle(pos=(self.x, self.y + self.height / 2), size=(self.width, (self.height / 2) - sh))
                        self.drop_quadrant = Quadrant.TOP
                    else:
                        Rectangle(pos=(self.x, self.y), size=(self.width, self.height - sh))
                        self.drop_quadrant = Quadrant.CENTER

    def on_touch_up(self, touch):
        res = super().on_touch_up(touch)
        self.draw_overlay()
        
        if not self.root: return
        dragged_panel = self.root.last_dragged_panel 
        if not dragged_panel: return
        if not dragged_panel.dock_panel: return
        if self.drop_quadrant is None: return

        dock_panel = dragged_panel.dock_panel
        dock_panel.remove_widget(dragged_panel)
        self.parent_dock.split_quadrant(dragged_panel, self.drop_quadrant)
        dock_panel.try_collapse_panel()

        return res

    def add_widget(self, widget: "DockTab", quadrant: Quadrant | None = None, index: int | None = None):
        widget.dock_panel = self
        self._tab_strip.add_widget(widget)
        if self._current_widget:
            super().remove_widget(self._current_widget.content)
        self._current_widget = widget
        super().add_widget(self._current_widget.content)
        self._calculate_tab_size()

    def remove_widget(self, widget: "DockTab"):
        assert widget.dock_panel == self
        widget.dock_panel = None
        index = self.tab_list.index(widget)
        self._tab_strip.remove_widget(widget)

        # If we currently select said widget we need to switch to the previous one if possible
        if self._current_widget == widget:
            super().remove_widget(widget.content)
            tab_list = self.tab_list
            if len(tab_list) > 0:
                self._current_widget = tab_list[max(0, index - 1)]
                super().add_widget(self._current_widget.content)

        self._calculate_tab_size()
    
    def try_collapse_panel(self):
        # Remove from parent
        if len(self.tab_list) == 0:
            self.parent_dock.remove_panel(self)

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

class DockTab(KWidget, ToggleButton):
    def __init__(self, **kwargs):
        self.root: Dock | None = None
        self.dock_panel: DockPanel | None = None
        super().__init__(**kwargs)

    def add_widget(self, widget: Widget, *args, **kwargs):
        self.content = widget

    def remove_widget(self, widget: Widget, *args, **kwargs):
        self.content = None

    def on_press(self):
        if self.dock_panel:
            self.dock_panel.select_widget(self)
        if self.root:
            self.root.active_panel = self
            for panel in self.root.iterate_panels():
                if panel == self: continue
                panel.state = "normal"
        self.state = "down"


    def on_touch_down(self, touch):
        if self.root:
            self.root.dragged_panel = self

        return super().on_touch_down(touch)

class BaseDock(BoxLayout):
    def __init__(self, root: "Dock | None", **kwargs):
        super().__init__(**kwargs)
        self.first_panel: DockPanel | BaseDock = DockPanel(root or cast(Dock, self), self)
        self.second_panel: DockSplitter | None = None
        self.root = root

        super().add_widget(self.first_panel)

    def iterate_panels(self) -> Generator[DockTab, None, None]:
        if isinstance(self.first_panel, BaseDock):
            yield from self.first_panel.iterate_panels()
        else: yield from self.first_panel.tab_list
        
        if self.second_panel:
            yield from self.second_panel.dock.iterate_panels()

    @property
    def active_panel(self) -> DockTab | None:
        if self.root: return self.root.active_panel

    @active_panel.setter
    def active_panel(self, value: DockTab):
        if self.root: self.root.active_panel = value

    def add_tab(self, panel: DockTab):
        if self.second_panel:
            second_panel = self.second_panel.children[0]
            if isinstance(second_panel, BaseDock):
                second_panel.add_tab(panel)
            elif isinstance(second_panel, DockPanel):
                panel.root = self.root or cast(Dock, self)
                second_panel.add_widget(panel)
                panel.on_press()
        else:
            panel.root = self.root or cast(Dock, self)
            self.first_panel.add_widget(panel)
            panel.on_press()

    def remove_panel(self, panel: DockPanel):
        assert panel.parent_dock == self
        first_panel = self.first_panel
        print(panel, first_panel, self.second_panel)
        if panel == first_panel:
            if self.second_panel:
                # Swap second and first panel
                self.remove_widget(first_panel)
                self.first_panel = self.second_panel.dock
                self.second_panel.remove_widget(self.second_panel.dock)
                self.add_widget(first_panel)
                self.remove_widget(self.second_panel)
                self.second_panel = None
            else:

                # This is the first panel, remove it from parent 
                splitter = self.parent
                parent = splitter.parent
                if isinstance(splitter, DockSplitter) and isinstance(parent, BaseDock):
                    parent.second_panel = None
                    parent.remove_widget(splitter)

    def add_primary_widget(self, widget: DockTab):
        if isinstance(self.first_panel, BaseDock):
            self.first_panel.add_primary_widget(widget)
        elif isinstance(self.first_panel, DockPanel):
            self.first_panel.add_widget(widget)

    def split_quadrant(self, panel: DockTab, quadrant = Quadrant.CENTER):
        if quadrant == Quadrant.CENTER:
            if isinstance(self.first_panel, BaseDock):
                self.first_panel.add_primary_widget(panel)
            else: self.first_panel.add_widget(panel)
            return

        if isinstance(self.first_panel, DockPanel):
            if quadrant == Quadrant.RIGHT or quadrant == Quadrant.BOTTOM:
                self.remove_widget(self.first_panel)
                self.second_panel = DockSplitter("left" if quadrant == Quadrant.RIGHT else "top")
                if quadrant == Quadrant.BOTTOM:
                    self.orientation = "vertical"

                right_child = ChildDock(self.root or cast(Dock, self))
                right_child.add_primary_widget(panel)
                self.second_panel.add_widget(right_child)
                self.add_widget(self.second_panel)
                self.add_widget(self.first_panel, index=1)
            else:
                self.remove_widget(self.first_panel)
                dock = ChildDock(self.root or cast(Dock, self))
                dock.remove_widget(dock.first_panel)
                dock.first_panel = DockPanel(self.root or cast(Dock, self), self)
                dock.first_panel.add_widget(panel)
                dock.add_widget(dock.first_panel)

                dock.second_panel = DockSplitter("left" if quadrant == Quadrant.LEFT else "top")
                if quadrant == Quadrant.TOP:
                    dock.orientation = "vertical"
                
                right_child = ChildDock(self.root or cast(Dock, self))
                right_child.remove_widget(right_child.first_panel)
                self.first_panel.parent_dock = right_child
                right_child.first_panel = self.first_panel
                right_child.add_widget(right_child.first_panel)

                dock.second_panel.add_widget(right_child)
                dock.add_widget(dock.second_panel)

                self.first_panel = dock
                self.add_widget(self.first_panel, index=1)

        else: 
            self.first_panel.split_quadrant(panel, quadrant)

    def split(self, panel: DockTab, orientation = Orientation.HORIZONTAL):
        if self.second_panel:
            second_panel = self.second_panel
            if isinstance(second_panel, DockSplitter):
                second_panel = second_panel.dock
                second_panel.split(panel, orientation)
        else:
            if isinstance(self.first_panel, DockPanel):
                if len(self.first_panel.tab_list) == 0:
                    self.first_panel.add_widget(panel)
                    return

            root = self.root or cast(Dock, self)
            new_second = ChildDock(root)
            panel.root = root
            new_second.add_tab(panel)
            panel.on_press() # This selects the current panel

            sizable_from = "left" if orientation == Orientation.HORIZONTAL else "top"
            if orientation == Orientation.VERTICAL:
                self.orientation = "vertical"

            self.second_panel = DockSplitter(sizable_from)
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
        self.last_dragged_panel: DockTab | None = None
        Window.bind(mouse_pos=lambda *args: self.draw_dragged_panel())

    def draw_dragged_panel(self):
        self.canvas.after.clear()
        if not self.dragged_panel: return
        with self.canvas.after:
            Color(*get_color_from_hex("#585858D0"))
            Rectangle(pos=(Window.mouse_pos[0], Window.mouse_pos[1] - self.dragged_panel.height), size=self.dragged_panel.size)

    def on_touch_up(self, touch):
        self.last_dragged_panel = self.dragged_panel
        self.dragged_panel = None
        self.draw_dragged_panel()
    
        res = super().on_touch_up(touch)
        self.last_dragged_panel = None
        return res

    @property
    def active_panel(self) -> DockTab | None:
        return self._active_panel

    @active_panel.setter
    def active_panel(self, value: DockTab):
        self._active_panel = value