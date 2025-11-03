from dataclasses import dataclass
from ui.dock.dock import SerializableTab
from ui.function_graph import SCALE_FACTOR, ScatterPlaneNoTouch
from ui.main import FONT_NAME, app
from ui.project import Function
from kivy.uix.stencilview import StencilView
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle, Line, PushMatrix, PopMatrix, Translate, Scale
from kivy.graphics.svg import Svg
from kivy.core.text import Label as CoreLabel
from kivy.utils import get_color_from_hex
from kivy.metrics import dp

from .kivytypes import KWidget

FONT_SIZE = 14

def find_font_height() -> tuple[int, int]:
    label = Label(
        text = "M",
        font_name = FONT_NAME,
        font_size = FONT_SIZE
    )
    label.texture_update()
    return label.texture_size # type: ignore

FONT_WIDTH, FONT_HEIGHT = find_font_height()
BOX_HEIGHT = FONT_HEIGHT + 10


class CallGraphTab(SerializableTab):
    content: "CallGraphPanel"

    def __init__(self, fun: Function, **kwargs):
        super().__init__(text=fun.name, closeable=True, source="ui/resources/calls.png", **kwargs)
        self.fun = fun

    def serialize(self) -> dict:
        data = super().serialize()
        data["function"] = self.fun.ep
        data["x"] = self.content.scatter.x
        data["y"] = self.content.scatter.y
        data["zoom"] = self.content.scatter.scale
        return data
    
    @classmethod
    def deserialize(cls, data: dict) -> "CallGraphTab":

        functions = app().project.functions
        assert functions
        fun = functions[data["function"]]
        tab = CallGraphTab(fun)
        panel = CallGraphPanel(fun, tab)
        tab.add_widget(panel)
        return tab
    
    def deserialize_post(self, data: dict):
        if "zoom" in data:
            self.content.scatter._set_scale(data["zoom"])
        if "x" in data and "y" in data:
            self.content.scatter._set_pos((data["x"], data["y"]))

@dataclass
class Block:
    path: list[Function]
    function: list[Function]
    x: float
    y: float
    prev_y: float

import cvxpy as cp
import numpy as np

def vertical_nonoverlap_qp(ideal_y, heights):
    """
    Adjust y positions (top of each block) to avoid vertical overlaps
    while minimizing total movement.
    """
    n = len(ideal_y)
    if n == 0:
        return []

    # Ensure arrays are 1D floats
    ideal_y = np.array(ideal_y, dtype=float).flatten()
    heights = np.array(heights, dtype=float).flatten()

    # Sort blocks top-to-bottom
    idx_sort = np.argsort(-ideal_y)
    ideal_y_sorted = ideal_y[idx_sort]
    heights_sorted = heights[idx_sort]

    # Optimization variables
    y = cp.Variable(n)

    # Objective: minimize squared distance from ideal positions
    objective = cp.Minimize(cp.sum_squares(y - ideal_y_sorted))

    # Constraints: no overlap
    constraints = [y[i] <= y[i-1] - heights_sorted[i-1] for i in range(1, n)]

    # Solve
    prob = cp.Problem(objective, constraints)
    prob.solve(solver=cp.OSQP)  # OSQP is usually robust

    # Restore original order
    y_opt = np.zeros(n)
    for i, yi in zip(idx_sort, y.value): #type: ignore
        y_opt[i] = yi

    return y_opt.tolist()

class CallGraph(KWidget, Widget):
    def __init__(self, fun: Function, panel: "CallGraphPanel", **kwargs):
        super().__init__(**kwargs)
        self.fun = fun
        self.panel = panel
        self.bind(pos=self.update_graphics, size=self.update_graphics)

        self.blocks: list[list[Block]] = []

    def update_blocks(self):
        MAX_DEPTH = 5
        functions = app().project.functions
        assert functions

        def shift_layer(blocks: list[Block]):
            ys = [block.y for block in blocks]
            heights = [float(len(block.function) * (BOX_HEIGHT + 10) + 20) for block in blocks]
            optimized_ys = vertical_nonoverlap_qp(ys, heights)
            for block, y in zip(blocks, optimized_ys):
                block.y = y

        self.blocks = []
        depth = 0
        layer: list[Block] = [Block([], [self.fun], 0, 0, 0)]
        x_offset = len(self.fun.name) * FONT_WIDTH + 85
        while depth < MAX_DEPTH:
            # Add callees to next layer
            width = 0
            next_layer = []
            for block in layer:
                for i, fun in enumerate(block.function):
                    # Check if fun has been encountered in this path
                    if fun in block.path:
                        continue

                    y_offset = i * (BOX_HEIGHT + 10)
                    fun_list = []
                    callees = set(map(lambda c: c[1], fun.callees))
                    for ep in callees:
                        callee = functions[ep]
                        fun_list.append(callee)

                    if len(fun_list) > 0:
                        next_layer.append(Block(
                            block.path + [fun],
                            fun_list, 
                            x_offset,
                            block.y - y_offset + len(fun_list) * (BOX_HEIGHT + 10) / 2 - BOX_HEIGHT / 2,
                            block.y - y_offset))
                        
                        width = max(width, max(map(lambda f: len(f.name) * FONT_WIDTH + 10, fun_list)))
            
            x_offset += width + 75
            
            layer = next_layer
            shift_layer(layer)
            depth += 1
            self.blocks.append(layer)

    def update_graphics(self):
        self.update_blocks()

        def draw_box(text: str, x: float, y: float, cycle: bool = False) -> float:
            label = CoreLabel(text=text, font_size=14 * SCALE_FACTOR, font_name=FONT_NAME)
            label.refresh()
            w, h = label.texture.size[0] / SCALE_FACTOR, label.texture.size[1] / SCALE_FACTOR
            Color(1, 1, 1, 1)
            Line(width=0.5, rectangle=(x, y - h - 10, w + 10, h + 10))
            if cycle:
                Color(*get_color_from_hex("#FF5555"))
            else: 
                Color(*get_color_from_hex("#DCDCAA"))
            Rectangle(pos=(x + 5, y - h - 5), size=(w, h), texture=label.texture)
            return w + 10
        
        def draw_layer(blocks: list[Block]):
            for block in blocks:
                x, y = block.x, block.y
                Color(1, 1, 1, 1)
                center = block.prev_y - BOX_HEIGHT / 2

                PushMatrix()
                Translate(x - 70, center - 5)
                Scale(10 / 512, 10 / 512, 1)
                Svg("ui/resources/minus.svg")
                PopMatrix()
                Line(width=0.5, points=[x - 60, center, x - 10, y, x, y])

                offset_y = y
                for fun in block.function:
                    draw_box(fun.name, x, offset_y, cycle=fun in block.path)
                    offset_y -= BOX_HEIGHT + 10
        
        with self.canvas:
            w = draw_box(self.fun.name, 0, 0)

            for layer in self.blocks:
                draw_layer(layer)

class CallGraphPanel(BoxLayout):
    tab: CallGraphTab

    def __init__(self, fun: Function, tab: CallGraphTab, **kwargs):
        super().__init__(**kwargs)
        self.tab = tab
        self.fun = fun

        self.graph = CallGraph(self.fun, self)
        self.stencil = StencilView(size_hint=(1, 1))
        self.scatter = ScatterPlaneNoTouch(do_rotation=False, do_scale=True, do_translation=True, size_hint=(1, 1))
        self.scatter.add_widget(self.graph)
        self.stencil.add_widget(self.scatter)
        self.add_widget(self.stencil)
        self.graph.update_graphics()
