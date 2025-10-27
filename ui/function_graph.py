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
from kivy.graphics import Canvas
from kivy.metrics import Metrics

from .kivytypes import KWidget
from .project import Function, Section
from .main import graph_tmpfolder, app, FONT_NAME, NavigationAction
from .sections import section_to_markup, LocationLabel
from .context_menu import ContextMenuBehavior, show_context_menu, MenuItem, MenuHandler

from .dock.dock import DockTab

class NavigationGraph(NavigationAction):
    def __init__(self, fun: int, location: tuple[int, int] | int, zoom: float = 0):
        super().__init__()
        self.function = fun
        self.location = location
        self.zoom = zoom

    def navigate(self):
        functions = app().project.functions
        assert functions is not None
        fun = functions.get(self.function)
        if not fun: return
        app().open_function_graph(fun.name, rescale=False)
        dock = app().main_dock
        if not dock: return
        for tab in dock.iterate_panels():
            if isinstance(tab, GraphTab):
                if isinstance(self.location, int):
                    tab.content.move_to_location(self.location, history=False)
                else:
                    tab.content.move_to_coords(self.location, self.zoom)

class GraphTab(DockTab):
    content: "FunctionPanel"

def parse_pos(pos_str):
    parts = pos_str.split()
    points = []
    for i, part in enumerate(parts):
        if i == 0 and part.startswith('e,'):
            part = part[2:]  # remove 'e,'
        x, y = map(float, part.split(','))
        points.append((x, y))
    return points

type Point = tuple[float, float]
type Segment = tuple[Point, Point, Point, Point]

def cubic_bezier_point(seg: Segment, t: float):
    x = (1 - t)**3 * seg[0][0] + 3*(1 - t)**2 * t * seg[1][0] + 3*(1 - t)*t**2 * seg[2][0] + t**3 * seg[3][0]
    y = (1 - t)**3 * seg[0][1] + 3*(1 - t)**2 * t * seg[1][1] + 3*(1 - t)*t**2 * seg[2][1] + t**3 * seg[3][1]
    return (x, y)

def cubic_bezier_tangent(seg: Segment, t: float):
    dx = 3*(1 - t)**2 * (seg[1][0] - seg[0][0]) + 6*(1 - t)*t * (seg[2][0] - seg[1][0]) + 3*t**2 * (seg[3][0] - seg[2][0])
    dy = 3*(1 - t)**2 * (seg[1][1] - seg[0][1]) + 6*(1 - t)*t * (seg[2][1] - seg[1][1]) + 3*t**2 * (seg[3][1] - seg[2][1])
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


class CodeBlockRect:
    def __init__(self, ep: int, x: int, y: int, width: int, height: int):
        self.ep = ep
        self.x = x
        self.y = y
        self.width = width
        self.height = height

class FunctionSvg(KWidget, ContextMenuBehavior, Widget):
    canvas: Canvas

    def __init__(self, fun: Function, panel: "FunctionPanel", **kwargs):
        super().__init__(**kwargs)
        self.fun = fun
        self.size_hint = (None, None)
        self.graphfile = fun.graph_json(graph_tmpfolder(), app().project.ob)
        self.labels: list[LocationLabel] = []
        self.hovered_label: LocationLabel | None = None
        self.panel = panel
        self.code_blocks: dict[int, CodeBlockRect] = {}
        self.first_block: CodeBlockRect | None = None
        self.current_block: CodeBlockRect | None = None

        self.bind(pos=self.update_graphics, size=self.update_graphics)
        Window.bind(mouse_pos=self.on_mouse_move)

    def trigger_context_menu(self, touch):
        if self.collide_point(touch.x, touch.y):
            if self.hovered_label:
                hovered_label = self.hovered_label
                class Handler1(MenuHandler):
                    def on_select(self, item):
                        if item == "goto": app().scroll_to_label(hovered_label.text)
                        elif item == "graph": 
                            if hovered_label.is_fun:
                                app().open_function_graph(hovered_label.text)
                            else:
                                app().open_function_graph_from_label(hovered_label.ep)
                        elif item == "listing": app().open_function_listing(hovered_label.text)
                
                show_context_menu(Handler1(), [
                    MenuItem("goto", f"Go to {'function' if hovered_label.is_fun else 'label'}"),
                    MenuItem("graph", "Open function graph")
                ] + [MenuItem("listing", "Open function listing")] if hovered_label.is_fun else [])
                return True
            else:
                for block in self.code_blocks.values():
                    if (block.x <= touch.x <= block.x + block.width and
                        block.y <= touch.y <= block.y + block.height):
                        class Handler2(MenuHandler):
                            def on_select(self, item):
                                if item == "goto": app().scroll_to_offset(block.ep)
                        
                        show_context_menu(Handler2(), [
                            MenuItem("goto", "Go to block"),
                        ])
                        return True

    def on_mouse_move(self, window, pos):
        if not self.panel.tab.is_visible(): return
            
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
            Window.set_system_cursor("hand")
            app().set_hover()

    def on_touch_down(self, touch):
        if touch.button == "left" and self.hovered_label is not None:
            try: 
                if self.hovered_label.is_fun: app().open_function_graph(self.hovered_label.text)
                else: self.panel.move_to_label(self.hovered_label.text)
                return True
            except ValueError: pass

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
        if self.current_block:
            with self.canvas.after:
                Color(*get_color_from_hex("#E69533"))
                Line(width=1.1, rectangle=(self.current_block.x, self.current_block.y, self.current_block.width, self.current_block.height))


    def update_graphics(self, *args):
        with open(self.graphfile) as fp:
            data = json.load(fp)

        _,_,gw,gh = data["bb"].split(",")
        self.width = float(gw)
        self.height = float(gh)

        def to_px(inches: float) -> int:
            return int(inches * 72)
        
        self.code_blocks = {}

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
                            pt = cubic_bezier_point(seg, t)
                            sampled_points.append(pt)

                    # Flatten for Kivy Line
                    flat_points = [coord for point in sampled_points for coord in point]

                    Line(points=flat_points, width=1.1)

                    # Draw arrowhead at endpoint using last segment
                    last_seg = segments[-1]
                    # Tangent at t=1 (end of last segment)
                    tx, ty = cubic_bezier_tangent(last_seg, 1)
                    tx, ty = normalize(tx, ty)

                    arrow_length = 12
                    arrow_width = 9

                    # Arrow tip is from Graphviz's 'e,x,y' position
                    tip_x, tip_y = endpoint  # This is from 'e,x,y'

                    # Tangent direction at t=1 from the last Bezier segment
                    tx, ty = cubic_bezier_tangent(last_seg, 1)
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
                for i, box in enumerate(data["objects"]):
                    x,y = map(float, box["pos"].split(","))
                    w,h = to_px(float(box["width"])), to_px(float(box["height"]))
                    x = self.x + x - w/2
                    y = self.y + y - h/2

                    ep = int(box["name"])
                    block = CodeBlockRect(ep, x, y, w, h)
                    self.code_blocks[ep] = block
                    if i == 0: self.first_block = block

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
        self.svg: FunctionSvg

    def on_touch_down(self, touch):
        if "multitouch_sim" in touch.profile: 
            touch.profile.remove("multitouch_sim")

        if touch.button == "scrollup" and self.collide_point(touch.x, touch.y):
            scale = 0.9
            self.apply_transform(Matrix().scale(scale, scale, scale), anchor=self.parent.to_widget(touch.x, touch.y))
            #self.svg.update_graphics()
        elif touch.button == "scrolldown" and self.collide_point(touch.x, touch.y):
            scale = 1.1
            self.apply_transform(Matrix().scale(scale, scale, scale), anchor=self.parent.to_widget(touch.x, touch.y))
            #self.svg.update_graphics()

        return super().on_touch_down(touch)
    
    def collide_point(self, x, y):
        return self.parent.collide_point(*self.parent.to_widget(x, y))

class FunctionPanel(BoxLayout):
    def __init__(self, fun: Function, tab: GraphTab, **kwargs):
        super().__init__(**kwargs)
        self.fun = fun

        self.tab = tab
        self.svg = FunctionSvg(self.fun, self)
        self.stencil = StencilView(size_hint=(1, 1))
        self.scatter = ScatterPlaneNoTouch(do_rotation=False, do_scale=True, do_translation=True, size_hint=(1, 1))
        self.scatter.svg = self.svg
        self.scatter.add_widget(self.svg)
        self.stencil.add_widget(self.scatter)
        self.add_widget(self.stencil)
        self.svg.update_graphics()

    def block_pos(self, block: CodeBlockRect) -> tuple[int, int]:
        x = self.stencil.x + self.stencil.width / 2 - (block.x + block.width / 2) * self.scatter.scale
        y = self.stencil.y + self.stencil.height / 2 - (block.y + block.height / 2) * self.scatter.scale
        return x, y
    
    def move_to_coords(self, location: tuple[int, int], zoom: float | None = None):
        if zoom: self.scatter._set_scale(zoom)
        self.scatter._set_pos(location)
    
    def move_to_initial_pos(self):
        self.scatter.apply_transform(Matrix().scale(Metrics.density, Metrics.density, Metrics.density))
        block = self.svg.first_block
        assert block is not None
        pos = self.block_pos(block)
        self.scatter._set_pos(pos)
        app().update_position_history(NavigationGraph(self.fun.ep, pos, self.scatter.scale))

    def move_to_location(self, ep: int, history = True):
        block = self.svg.code_blocks.get(ep)
        if block is None: return

        if history:
            app().update_position_history(NavigationGraph(self.fun.ep, ep))

        self.svg.current_block = block
        self.svg.render_hover()
        self.scatter._set_pos(self.block_pos(block))

    def move_to_label(self, label: str):
        ep = 0
        section: Section
        for section in app().project.sections.values():
            if section.labels and section.labels[0].name == label:
                ep = section.offset
                break
        else: return
        self.move_to_location(ep)