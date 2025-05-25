import math, json

from kivy.uix.tabbedpanel import TabbedPanelItem, TabbedPanel, TabbedPanelStrip
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scatter import ScatterPlane
from kivy.uix.stencilview import StencilView
from kivy.uix.label import Label
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Triangle, Color, Line, Rectangle
from kivy.metrics import dp
from kivy.utils import colormap, get_color_from_hex
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.core.text.markup import MarkupLabel
from kivy.graphics.transformation import Matrix

from .project import Function
from .main import graph_tmpfolder, app, FONT_NAME
from .sections import section_to_markup, LocationLabel
from .buttons import XButton

class FunctionTabPanel(TabbedPanel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tab_width = None

    def close_tab(self, item):
        index = self.tab_list.index(item)
        self.remove_widget(item)
        if len(self.tab_list) == 1:
            # Removed the last tab, collapse tabbed pane
            self.clear_widgets()
            app().dis_panel_container.remove_widget(self)
            app().dis_panel_container.add_widget(app().dis_panel)
        else:
            Clock.schedule_once(lambda dt: self.switch_to(self.tab_list[index - 1 if index - 1 >= 0 else 0]))

class FunctionTabItem(TabbedPanelItem, FloatLayout):
    def __init__(self, fun: Function, **kwargs):
        super().__init__(**kwargs)
        self.text = fun.name
        self.fun = fun
        self.add_widget(FunctionPanel(fun, self))
        box = BoxLayout(size_hint=(None, None), width=dp(22.5), height=dp(20), padding=(0, 0, dp(2.5), 0), pos_hint={"right": 1, "center_y": 0.5})
        box.add_widget(XButton(on_press=lambda *_: self.close_tab()))
        super(FloatLayout, self).add_widget(box)

    def close_tab(self):
        panel: FunctionTabPanel = self.parent.tabbed_panel
        panel.close_tab(self)

    def move_to_initial_pos(self):
        self.content.move_to_initial_pos()

def parse_pos(pos_str):
    parts = pos_str.split()
    points = []
    for i, part in enumerate(parts):
        if i == 0 and part.startswith('e,'):
            part = part[2:]  # remove 'e,'
        x, y = map(float, part.split(','))
        points.append((x, y))
    return points

def cubic_bezier_point(p0, p1, p2, p3, t):
    x = (1 - t)**3 * p0[0] + 3*(1 - t)**2 * t * p1[0] + 3*(1 - t)*t**2 * p2[0] + t**3 * p3[0]
    y = (1 - t)**3 * p0[1] + 3*(1 - t)**2 * t * p1[1] + 3*(1 - t)*t**2 * p2[1] + t**3 * p3[1]
    return (x, y)

def cubic_bezier_tangent(p0, p1, p2, p3, t):
    dx = 3*(1 - t)**2 * (p1[0] - p0[0]) + 6*(1 - t)*t * (p2[0] - p1[0]) + 3*t**2 * (p3[0] - p2[0])
    dy = 3*(1 - t)**2 * (p1[1] - p0[1]) + 6*(1 - t)*t * (p2[1] - p1[1]) + 3*t**2 * (p3[1] - p2[1])
    return (dx, dy)

def normalize(vx, vy):
    length = (vx**2 + vy**2) ** 0.5
    if length == 0:
        return (0, 0)
    return (vx/length, vy/length)


def find_font_height():
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = 14 * SCALE_FACTOR
    )
    label.texture_update()
    return label.texture_size

SCALE_FACTOR = 4
SVG_FONT_WIDTH, SVG_FONT_HEIGHT = find_font_height()


class FunctionSvg(Widget):
    def __init__(self, fun: Function, panel: FunctionTabItem, **kwargs):
        super().__init__(**kwargs)
        self.fun = fun
        self.size_hint = (None, None)
        self.graphfile = fun.graph_json(graph_tmpfolder(), app().project.ob)
        self.labels: list[LocationLabel] = []
        self.hovered_label = None
        self.panel = panel

        self.bind(pos=self.update_graphics, size=self.update_graphics)
        Window.bind(mouse_pos=self.on_mouse_move)

    def on_mouse_move(self, window, pos):
        tab_panel = app().tab_panel
        if tab_panel: 
            if tab_panel.current_tab != self.panel: 
                return
            
        x, y = self.to_widget(*pos)

        last = self.hovered_label
        self.hovered_label = None
        for label in self.labels:
            if (label.x <= x <= label.x + label.width and
                label.y <= y <= label.y + label.height):

                self.hovered_label = label
                break
        if last != self.hovered_label: self.render_hover()
        if self.hovered_label is not None and not app().any_hovered:
            Window.set_system_cursor('hand')
            app().set_hover()

    def on_touch_down(self, touch):
        if touch.button == "left" and self.hovered_label is not None:
            try: app().open_function_graph(self.hovered_label.text)
            except ValueError: pass
            return True

        return super().on_touch_down(touch)
     
    def render_hover(self):
        self.canvas.after.clear()
        if self.hovered_label:
            with self.canvas.after:
                Color(*get_color_from_hex("#64B5F6"))
                label = CoreLabel(font_size=14 * SCALE_FACTOR, font_name=FONT_NAME)
                label.text = self.hovered_label.text
                label.refresh()

                Rectangle(texture=label.texture, size=(label.texture.size[0] / SCALE_FACTOR, label.texture.size[1] / SCALE_FACTOR), pos=(self.hovered_label.x, self.hovered_label.y))
                Line(points=[
                        self.hovered_label.x, self.hovered_label.y - 0.5,
                        self.hovered_label.x + self.hovered_label.width, self.hovered_label.y - 0.5
                    ], width=0.5)


    def update_graphics(self, *args):
        with open(self.graphfile) as fp:
            data = json.load(fp)

        _,_,gw,gh = data["bb"].split(",")
        self.width = float(gw)
        self.height = float(gh)

        def to_px(inches: float) -> float:
            return inches * 72
        
        self.canvas.clear()
        self.labels.clear()
        with self.canvas:
            if "edges" in data:
                for line in data["edges"]:
                    points = parse_pos(line["pos"])

                    if line["color"] == "black":
                        Color(1, 1, 1, 1)
                    else: Color(*colormap[line["color"]])

                    points = [(x + self.x, y + self.y) for x, y in points]

                    endpoint = points[0]
                    control_points = points[1:]

                    n = len(control_points)
                    if (n - 1) % 3 != 0:
                        raise ValueError("Non cubic spline!")

                    # Split control points into cubic Bezier segments
                    segments = []
                    k = (n - 1) // 3
                    for i in range(k):
                        seg = control_points[i*3 : i*3 + 4]  # 4 points per segment
                        segments.append(seg)

                    # Sample points for all segments
                    sampled_points = []
                    steps = 30
                    for seg in segments:
                        for t_i in range(steps + 1):
                            t = t_i / steps
                            pt = cubic_bezier_point(*seg, t)
                            sampled_points.append(pt)

                    # Flatten for Kivy Line
                    flat_points = [coord for point in sampled_points for coord in point]

                    Line(points=flat_points, width=1.1)

                    # Draw arrowhead at endpoint using last segment
                    last_seg = segments[-1]
                    # Tangent at t=1 (end of last segment)
                    tx, ty = cubic_bezier_tangent(*last_seg, 1)
                    tx, ty = normalize(tx, ty)

                    arrow_length = 12
                    arrow_width = 9

                    # Arrow tip is from Graphviz's 'e,x,y' position
                    tip_x, tip_y = endpoint  # This is from 'e,x,y'

                    # Tangent direction at t=1 from the last Bezier segment
                    tx, ty = cubic_bezier_tangent(*last_seg, 1)
                    tx, ty = normalize(tx, ty)

                    # Base center of the arrowhead
                    base_x = tip_x - arrow_length * tx
                    base_y = tip_y - arrow_length * ty

                    # Perpendicular vector to tangent for arrow base width
                    perp_x = -ty
                    perp_y = tx

                    # Two base corners of the arrowhead triangle
                    left_x = base_x + arrow_width/2 * perp_x
                    left_y = base_y + arrow_width/2 * perp_y

                    right_x = base_x - arrow_width/2 * perp_x
                    right_y = base_y - arrow_width/2 * perp_y

                    Triangle(points=[tip_x, tip_y, left_x, left_y, right_x, right_y])

            Color(1, 1, 1, 1)
            if "objects" in data:

                for box in data["objects"]:
                    x,y = map(float, box["pos"].split(","))
                    w,h = to_px(float(box["width"])), to_px(float(box["height"]))
                    x = self.x + x - w/2
                    y = self.y + y - h/2
                    
                    ep = int(box["name"])
                    block = self.fun.blocks[ep]
                    lines, labels = [], []
                    section_to_markup(block.insn, lines, labels)
                    for label in labels:
                        label.x = x + label.x * SVG_FONT_WIDTH / SCALE_FACTOR + 8
                        label.y = y + ((len(lines) - label.y - 1) * SVG_FONT_HEIGHT * 1.05) / SCALE_FACTOR + 8
                        label.width = label.width * SVG_FONT_WIDTH / SCALE_FACTOR
                        label.height = label.height * SVG_FONT_HEIGHT / SCALE_FACTOR

                    self.labels.extend(labels)

                    for i, line in enumerate(lines):
                        label = MarkupLabel(markup=True, font_size=14 * SCALE_FACTOR, font_name=FONT_NAME)
                        label.text = line
                        label.refresh()

                        Rectangle(texture=label.texture, size=(label.texture.size[0] / SCALE_FACTOR, label.texture.size[1] / SCALE_FACTOR), pos=(x + 8, y + (len(lines) - i - 1) * SVG_FONT_HEIGHT * 1.05 / SCALE_FACTOR + 8))
                        
                    Line(width=1.1, rectangle=(x, y, w, h))


class ScatterPlaneNoTouch(ScatterPlane):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.svg: FunctionSvg = None

    def on_touch_down(self, touch):
        if "multitouch_sim" in touch.profile: 
            touch.profile.remove("multitouch_sim")

        if touch.button == "scrollup" and self.collide_point(touch.x, touch.y):
            scale = 0.9
            self.apply_transform(Matrix().scale(scale, scale, scale), anchor=self.parent.to_widget(touch.x, touch.y))
            self.svg.update_graphics()
        elif touch.button == "scrolldown" and self.collide_point(touch.x, touch.y):
            scale = 1.1
            self.apply_transform(Matrix().scale(scale, scale, scale), anchor=self.parent.to_widget(touch.x, touch.y))
            self.svg.update_graphics()

        return super().on_touch_down(touch)
    
    def collide_point(self, x, y):
        return self.parent.collide_point(*self.parent.to_widget(x, y))

class FunctionPanel(BoxLayout):
    def __init__(self, fun: Function, tab: FunctionTabItem, **kwargs):
        super().__init__(**kwargs)
        self.fun = fun

        self.svg = FunctionSvg(self.fun, tab)
        self.stencil = StencilView(size_hint=(1, 1))
        self.scatter = ScatterPlaneNoTouch(do_rotation=False, do_scale=True, do_translation=True, size_hint=(1, 1))
        self.scatter.svg = self.svg
        self.scatter.add_widget(self.svg)
        self.stencil.add_widget(self.scatter)
        self.add_widget(self.stencil)
        self.svg.update_graphics()
    
    def move_to_initial_pos(self):
        self.scatter._set_pos((0, -self.svg.height + self.stencil.y + self.stencil.height))