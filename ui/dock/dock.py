from enum import Enum
from typing import Generator, cast
from abc import ABC, abstractmethod

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.splitter import Splitter
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.uix.gridlayout import GridLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.graphics import Rectangle, Color
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.properties import BooleanProperty, StringProperty, ObjectProperty
from kivy.clock import Clock

from ui.kivytypes import KWidget
from ui.buttons import XButton

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

class Child(Widget):
    @abstractmethod 
    def iterate_panels(self) -> "Generator[DockTab, None, None]" : pass

class DockSplitter(Splitter, Child):
    def __init__(self, sizable_from: str, **kwargs):
        super().__init__(sizable_from=sizable_from, keep_within_parent=True, max_size=dp(10e10), min_size=0, **kwargs)

    @property
    def dock(self) -> "BaseDock":
        return self.children[0]
    
    def iterate_panels(self) -> "Generator[DockTab, None, None]":
        return self.dock.iterate_panels()

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
        return super().on_touch_down(touch)

class DockPanel(KWidget, BoxLayout, Child):
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
                diffx = self._tab_strip.width - self._scroll_strip.width
                offx = self._scroll_strip.scroll_x * diffx if diffx > 0 else 0
                xpos = self.x - offx
                i = 0
                for tab in reversed(self._tab_strip.children):
                    if xpos <= x <= xpos + tab.width:
                        break
                    i += 1
                    xpos += tab.width
                    
                self.drop_tab = len(self._tab_strip.children) - i - 1

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

    def on_touch_down(self, touch):
        if touch.button == "left":
            self.drop_quadrant = None
            self.drop_tab = None
            if self._current_widget and self._current_widget.content:
                if self._current_widget.content.collide_point(touch.x, touch.y):
                    self._current_widget.select()
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        res = super().on_touch_up(touch)
        if touch.button != "left": return res
        self.draw_overlay()
        
        if not self.root: return
        dragged_panel = self.root.last_dragged_panel 
        if not dragged_panel: return
        if not dragged_panel.dock_panel: return
        if self.drop_tab is None and self.drop_quadrant is None: return

        index = dragged_panel.index()
        parent = dragged_panel.dock_panel

        dock_panel = dragged_panel.dock_panel
        dock_panel.remove_widget(dragged_panel)

        if self.drop_quadrant:
            self.parent_dock.split_quadrant(dragged_panel, self.drop_quadrant)
        elif self.drop_tab is not None:
            i = self.drop_tab
            # If we removed the panel from the same tab the index has to change
            if index > self.drop_tab and parent == self: i += 1 
            if parent != self: i += 1
            self.parent_dock.add_tab(dragged_panel, i)

        if dock_panel.parent_dock.parent_dock:
            dock_panel.parent_dock.parent_dock.purge_empty()

        return res

    def add_widget(self, widget: "DockTab", index: int = 0):
        widget.dock_panel = self
        self._tab_strip.add_widget(widget, index)
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

    def iterate_panels(self) -> "Generator[DockTab, None, None]":
        yield from self.tab_list
 
    
class TabStrip(GridLayout):
    def __init__(self, **kwargs):
        super().__init__(rows=1, **kwargs)

class DockButton(KWidget, ToggleButton):
    parent: "DockTab"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
    def on_press(self):
        if self.parent.dock_panel:
            self.parent.dock_panel.select_widget(self.parent)
        if self.parent.root:
            self.parent.root.active_panel = self.parent
            for panel in self.parent.root.iterate_panels():
                if panel.button == self: continue
                panel.button.state = "normal"
        self.state = "down"


    def on_touch_down(self, touch):
        if touch.button == "left" and self.parent.root:
            self.parent.root.dragged_panel = self.parent
            return super().on_touch_down(touch)
        return False

class TabXButton(XButton):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_press(self):
        parent: DockTab = self.parent
        if parent.dock_panel:
            dock_panel = parent.dock_panel
            parent.dock_panel.remove_widget(self.parent)
            if dock_panel.parent_dock.parent_dock:
                dock_panel.parent_dock.parent_dock.purge_empty()

            def select_last(_):
                if dock_panel._current_widget and dock_panel._current_widget.parent:
                    dock_panel._current_widget.select()
                elif dock_panel.parent_dock.parent_dock:
                    panel = next(dock_panel.parent_dock.parent_dock.iterate_panels(), None)
                    if panel and panel.dock_panel and panel.dock_panel._current_widget:
                        panel.dock_panel._current_widget.select()

            Clock.schedule_once(select_last, 0)

class DockTabIcon(Image): pass
            
class DockTab(KWidget, RelativeLayout):
    closeable = BooleanProperty(False)
    text = StringProperty("")
    button = ObjectProperty(None)
    source = StringProperty(None)

    def __init__(self, **kwargs):
        self.root: Dock | None = None
        self.dock_panel: DockPanel | None = None
        self.button = DockButton()
        self.xbutton = TabXButton()
        super().__init__(**kwargs)
        super().add_widget(self.button)
        super().add_widget(self.xbutton)
        super().add_widget(DockTabIcon())

    def add_widget(self, widget: Widget, *args, **kwargs):
        self.content = widget

    def remove_widget(self, *args, **kwargs):
        self.content = None

    def index(self) -> int:
        if not self.dock_panel: return -1
        return self.dock_panel._tab_strip.children.index(self)
    
    def select(self):
        self.button.on_press()

    def close(self):
        self.xbutton.on_press()

    def is_visible(self) -> bool:
        if not self.dock_panel: return False
        return self.dock_panel._current_widget == self

serializable_panels = {}
class SerializableTab(DockTab):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __init_subclass__(cls) -> None:
        serializable_panels[cls.__name__] = cls
        return super().__init_subclass__()

    @abstractmethod
    def serialize(self) -> dict:
        return {"type": self.__class__.__name__}

    @classmethod
    @abstractmethod
    def deserialize(cls, data: dict) -> "SerializableTab": pass

    def deserialize_post(self, data: dict): pass

    @staticmethod
    def deserialize_panel(data: dict) -> "SerializableTab":
        panel_type = data.get("type")
        if panel_type and panel_type in serializable_panels:
            panel_cls = serializable_panels[panel_type]
            panel = panel_cls.deserialize(data)
            return panel
        raise ValueError("Unknown panel type: " + str(panel_type))

class BaseDock(BoxLayout, Child):
    def __init__(self, root: "Dock | None", parent: "BaseDock | None" = None, panel: DockPanel | None = None, **kwargs):
        super().__init__(**kwargs)
        self.parent_dock = parent
        self.panel: DockPanel | None = panel
        self.first_panel: BaseDock | None = None
        self.second_panel: BaseDock | None = None
        self.splitter: DockSplitter | None = None
        self.root = root

        if panel:
            panel.parent_dock = self
            super().add_widget(panel)

    def iterate_panels(self) -> Generator[DockTab, None, None]:
        if self.panel:
            yield from self.panel.iterate_panels()
        else:
            if self.first_panel:
                yield from self.first_panel.iterate_panels()        
            if self.second_panel:
                yield from self.second_panel.iterate_panels()

    @property
    def active_panel(self) -> DockTab | None:
        if self.root: return self.root.active_panel

    @active_panel.setter
    def active_panel(self, value: DockTab):
        if self.root: self.root.active_panel = value

    def add_widget(self, widget, *args, index: int = 0, **kwargs):
        if isinstance(widget, DockTab):
            self.add_tab(widget, index)
        else: super().add_widget(widget, *args, **kwargs)

    def add_tab(self, panel: DockTab, index: int = 0, reverse = False):
        panel.root = self.root or cast(Dock, self)

        first, second = self.first_panel, self.second_panel
        if reverse: first, second = second, first

        if second:
            second.add_tab(panel, index)
        elif first:
            first.add_tab(panel, index)
        elif self.panel:
            self.panel.add_widget(panel, index=index)
        else:
            self.panel = DockPanel(self.root or cast(Dock, self), self)
            self.panel.add_widget(panel)
            super().add_widget(self.panel)

        panel.select()

    def purge_empty(self):
        if self.first_panel:
            if len(list(self.first_panel.iterate_panels())) == 0:
                super().remove_widget(self.first_panel)
                self.first_panel = None
                if self.second_panel and self.splitter: 
                    self.first_panel = self.second_panel
                    self.splitter.remove_widget(self.second_panel)
                    super().remove_widget(self.splitter)
                    super().add_widget(self.first_panel)
                    self.splitter = None
                    self.second_panel = None
        if self.second_panel:
            if len(list(self.second_panel.iterate_panels())) == 0:
                if self.splitter:
                    super().remove_widget(self.splitter)
                self.splitter = None
                self.second_panel = None

        # Flatten heirarchy, if first or second panel contain only one element they should be
        # pulled up into this panel, but only if there is no other child present
        if self.second_panel and self.second_panel.panel and not self.first_panel:
            dock_panel = self.second_panel.panel
            self.second_panel.remove_widget(dock_panel)
            if self.splitter:
                super().remove_widget(self.splitter)
                self.splitter = None
            
            super().add_widget(dock_panel)
            dock_panel.parent_dock = self
            self.panel = dock_panel
            self.first_panel = None
            self.second_panel = None
        
        if self.first_panel and self.first_panel.panel and not self.second_panel:
            dock_panel = self.first_panel.panel
            self.first_panel.remove_widget(dock_panel)
            super().remove_widget(self.first_panel)
            super().add_widget(dock_panel)
            dock_panel.parent_dock = self
            self.panel = dock_panel
            self.first_panel = None
            self.second_panel = None
                

    def split_quadrant(self, panel: DockTab, quadrant = Quadrant.CENTER):
        orientation = Orientation.VERTICAL if quadrant in (Quadrant.TOP, Quadrant.BOTTOM) else Orientation.HORIZONTAL

        if quadrant == Quadrant.LEFT or quadrant == Quadrant.TOP:
            if self.first_panel:
                self.first_panel.split_quadrant(panel, quadrant)
            elif self.panel:
                panel.root = self.root or cast(Dock, self)
                super().remove_widget(self.panel)
                self.second_panel = BaseDock(self.root or cast(Dock, self), self, self.panel)
                self.panel.parent_dock = self.second_panel
                self.panel = None
                
                if orientation == Orientation.VERTICAL:
                    self.orientation = "vertical"
                else: self.orientation = "horizontal"
                    
                self.splitter = DockSplitter("left" if orientation == Orientation.HORIZONTAL else "top")
                self.splitter.add_widget(self.second_panel)
                super().add_widget(self.splitter)

                if self.second_panel:
                    dock_panel = DockPanel(self.root or cast(Dock, self), self)
                    dock_panel.add_widget(panel)
                    self.first_panel = BaseDock(self.root or cast(Dock, self), self, panel=dock_panel)

                    super().add_widget(self.first_panel, 1)
            elif self.second_panel: 
                self.second_panel.split_quadrant(panel, quadrant)
        elif quadrant == Quadrant.CENTER:
            if self.panel: self.panel.add_widget(panel)
            elif self.first_panel: self.first_panel.add_tab(panel)
        else:
            self.split(panel, orientation)

    def split(self, panel: DockTab, orientation = Orientation.HORIZONTAL):
        if self.second_panel:
            self.second_panel.split(panel, orientation)
            return
        
        if self.panel:
            panel.root = self.root or cast(Dock, self)
            super().remove_widget(self.panel)
            self.first_panel = BaseDock(self.root or cast(Dock, self), self, self.panel)
            self.panel.parent_dock = self.first_panel
            self.panel = None
            super().add_widget(self.first_panel)

        if self.first_panel:
            dock_panel = DockPanel(self.root or cast(Dock, self), self)
            dock_panel.add_widget(panel)
            self.second_panel = BaseDock(self.root or cast(Dock, self), self, panel=dock_panel)
            
            if orientation == Orientation.VERTICAL:
                self.orientation = "vertical"
            else: self.orientation = "horizontal"

            self.splitter = DockSplitter("left" if orientation == Orientation.HORIZONTAL else "top")
            self.splitter.add_widget(self.second_panel)

            super().add_widget(self.splitter)


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
            label = CoreLabel(text=self.dragged_panel.text, color=(1, 1, 1, 1), font_size=self.dragged_panel.button.font_size)
            label.refresh()

            pos = (Window.mouse_pos[0], Window.mouse_pos[1] - self.dragged_panel.height)
            Color(*get_color_from_hex("#585858D0"))
            Rectangle(pos=pos, size=self.dragged_panel.size)
            Color(1, 1, 1, 1)
            Rectangle(texture=label.texture, pos=
                      (pos[0] + self.dragged_panel.width / 2 - label.width / 2, 
                       pos[1] + self.dragged_panel.height / 2 - label.height / 2), 
                       size=label.texture.size)

    def on_touch_up(self, touch):
        if touch.button == "left":
            self.last_dragged_panel = self.dragged_panel
            self.dragged_panel = None
            self.draw_dragged_panel()
        
            res = super().on_touch_up(touch)
            self.last_dragged_panel = None
            return res
        else: return super().on_touch_up(touch)

    @property
    def active_panel(self) -> DockTab | None:
        return self._active_panel
    
    @property
    def active_content(self) -> Widget | None:
        if self._active_panel: return self._active_panel.content
        return None

    @active_panel.setter
    def active_panel(self, value: DockTab):
        self._active_panel = value
