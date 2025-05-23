import math, json

from kivy.uix.tabbedpanel import TabbedPanelItem
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scatter import Scatter
from kivy.graphics import Triangle, Color, Line
from kivy.metrics import dp
from kivy.utils import colormap

from .project import Function
from .main import graph_tmpfolder, app

class FunctionTabItem(TabbedPanelItem):
    def __init__(self, fun: Function, **kwargs):
        super().__init__(**kwargs)
        self.text = fun.name
        self.fun = fun
        self.add_widget(FunctionPanel(fun))

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


class FunctionSvg(Widget):
    def __init__(self, fun: Function, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.graphfile = fun.graph_json(graph_tmpfolder, app().project.ob)
        self.bind(pos=self.update_graphics, size=self.update_graphics)
     
    def update_graphics(self, *args):
        with open(self.graphfile) as fp:
            data = json.load(fp)

        _,_,gw,gh = data["bb"].split(",")
        self.width = dp(float(gw))
        self.height = dp(float(gh))

        def to_px(inches: float) -> float:
            return inches * 72

        self.canvas.clear()
        with self.canvas:
            if "edges" in data:
                for line in data["edges"]:
                    points = parse_pos(line["pos"])

                    Color(*colormap[line["color"]])

                    points = [(dp(x) + self.x, dp(y) + self.y) for x, y in points]

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

                    Line(points=flat_points, width=dp(1))

                    # Draw arrowhead at endpoint using last segment
                    last_seg = segments[-1]
                    # Tangent at t=1 (end of last segment)
                    tx, ty = cubic_bezier_tangent(*last_seg, 1)
                    tx, ty = normalize(tx, ty)

                    arrow_length = dp(15)
                    arrow_width = dp(10)

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
                    Line(width=dp(1), rectangle=(self.x + dp(x) - dp(w)/2, self.y + dp(y) - dp(h)/2, dp(w), dp(h)))

class FunctionPanel(BoxLayout):
    def __init__(self, fun: Function, **kwargs):
        super().__init__(**kwargs)
        self.fun = fun
        #self.scatter = Scatter(do_rotation=False, do_scale=True, do_translation=True, size_hint=(1, 1))
        #self.scatter.add_widget(FunctionSvg(self.fun))
        self.add_widget(FunctionSvg(self.fun))