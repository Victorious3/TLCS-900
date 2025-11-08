from dataclasses import dataclass

from ui.dock.dock import SerializableTab
from ui.function_graph import SCALE_FACTOR, ScatterPlaneNoTouch
from ui.main import FONT_NAME, app
from ui.project import Function
from kivy.uix.stencilview import StencilView
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle, Line, Fbo
from kivy.graphics.svg import Svg
from kivy.core.text import Label as CoreLabel
from kivy.utils import get_color_from_hex
from kivy.metrics import Metrics
from kivy.graphics.transformation import Matrix
from kivy.clock import Clock

from .kivytypes import KWidget
from .arrow import COLORS

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
        self.content.graph.serialize(data)
        return data
    
    @classmethod
    def deserialize(cls, data: dict) -> "CallGraphTab":

        functions = app().project.functions
        assert functions
        fun = functions[data["function"]]
        tab = CallGraphTab(fun)
        panel = CallGraphPanel(fun, tab)
        panel.graph.deserialize(data)
        tab.add_widget(panel)
        return tab
    
    def deserialize_post(self, data: dict):
        if "zoom" in data:
            self.content.scatter._set_scale(data["zoom"])
        if "x" in data and "y" in data:
            self.content.scatter._set_pos((data["x"], data["y"]))

    def refresh(self, **kwargs):
        self.text = self.content.fun.name
        self.content.graph.rebalance_layers(0, direction=1)
        self.content.graph.rebalance_layers(0, direction=-1)
        self.content.graph.update_graphics()

@dataclass
class Block:
    prev: "Block | None"
    path: list[Function]
    function: list[Function]
    x: float
    y: float
    prev_y: float
    layer: int

@dataclass
class Icon:
    column: int
    row: int
    f: int
    x: float
    y: float

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

def shift_layer(blocks: list[Block]):
    ys = [block.y - len(block.function) * (BOX_HEIGHT + 10) / 2 + (BOX_HEIGHT + 10) / 2 for block in blocks]
    heights = [float(len(block.function) * (BOX_HEIGHT + 10) + 20) for block in blocks]
    optimized_ys = vertical_nonoverlap_qp(ys, heights)
    for block, y in zip(blocks, optimized_ys):
        block.y = y

class CallGraph(KWidget, Widget):
    def __init__(self, fun: Function, panel: "CallGraphPanel", **kwargs):
        super().__init__(**kwargs)
        self.fun = fun
        self.panel = panel
        self.bind(pos=self.update_graphics, size=self.update_graphics)

        # Callees open to the right and callers to the left
        self.callees = [[Block(None, [], [self.fun], 0, 0, 0, 0)]]
        self.callers = [[Block(None, [], [self.fun], 0, 0, 0, 0)]]
        self.plus: list[Icon] = []
        self.minus: list[Icon] = []

        # Render plus and minus icons to texture to speed things up
        fbo = Fbo(size=(512, 512), with_stencilbuffer=True)
        with fbo: Svg("ui/resources/plus.svg")
        fbo.draw()
        self.plus_texture = fbo.texture
        fbo = Fbo(size=(512, 512), with_stencilbuffer=True)
        with fbo: Svg("ui/resources/minus.svg")
        fbo.draw()
        self.minus_texture = fbo.texture

        self.open_center() # open the root function
        self.hovered: int | None = None

    def serialize(self, data: dict):
        callers = []
        callees = []

        def serialize_layer(prev_layer: list[Block] | None, layer: list[Block]) -> list[dict]:
            layer_data = []
            for block in layer:
                block_data = {
                    "prev_index": prev_layer.index(block.prev) if block.prev and prev_layer else None,
                    "path": [f.ep for f in block.path],
                    "functions": [f.ep for f in block.function]
                }
                layer_data.append(block_data)
            return layer_data
        
        prev_layer = None
        for layer in self.callees:
            callees.append(serialize_layer(prev_layer, layer))
            prev_layer = layer
        prev_layer = None
        for layer in self.callers:
            callers.append(serialize_layer(prev_layer, layer))
            prev_layer = layer

        data["callees"] = callees
        data["callers"] = callers

    def deserialize(self, data: dict):
        self.callees.clear()
        self.callers.clear()

        functions = app().project.functions
        assert functions

        def deserialize_layer(prev_layer: list[Block], layer_data: list[dict], index: int) -> list[Block]:
            layer = []
            for block_data in layer_data:
                prev_index = block_data["prev_index"]
                block = Block(
                    prev=prev_layer[prev_index] if prev_index is not None else None,
                    path=[functions[ep] for ep in block_data["path"]],
                    function=[functions[ep] for ep in block_data["functions"]],
                    x=0, y=0, prev_y=0, layer=index
                )
                layer.append(block)
            return layer

        prev_layer = []
        for i, layer_data in enumerate(data.get("callees", [])):
            prev_layer = deserialize_layer(prev_layer, layer_data, i)
            self.callees.append(prev_layer)

        prev_layer = []
        for i, layer_data in enumerate(data.get("callers", [])):
            prev_layer = deserialize_layer(prev_layer, layer_data, -i)
            self.callers.append(prev_layer)

        self.rebalance_layers(0, direction=1)
        self.rebalance_layers(0, direction=-1)
        self.update_graphics()

    def open_center(self):
        all_functions = app().project.functions
        assert all_functions
        
        # Open both callers and callees for the center function
        center_callees = self.callees[0][0]
        center_callers = self.callers[0][0]

        callee_functions = list({all_functions[ep] for i, ep in self.fun.callees})
        self.callees.append([Block(center_callees, [self.fun], callee_functions, len(self.fun.name) * FONT_WIDTH + 85, 0, 0, 1)])
        
        caller_functions = list({all_functions[ep] for i, ep in self.fun.callers})
        self.callers.append([Block(center_callers, [self.fun], caller_functions, max(map(lambda c: len(c.name) * FONT_WIDTH + 85, caller_functions), default=0), 0, 0, -1)])

        self.update_graphics()

    def close(self, column: int, row: int):
        blocks = self.callees if column >= 0 else self.callers
        layer = blocks[abs(column)]
        removed = [layer.pop(row)]

        if len(layer) == 0:
            blocks.remove(layer)

        for layer in blocks[abs(column):]:
            for block in layer[:]:
                if block.prev in removed:
                    layer.remove(block)
                    removed.append(block)
            if len(layer) == 0:
                blocks.remove(layer)

        self.rebalance_layers(abs(column) - 1, column > 0 and 1 or -1)

    def open(self, column: int, row: int, f: int):
        all_functions = app().project.functions
        assert all_functions
        
        blocks = self.callees if column >= 0 else self.callers
        layer = blocks[abs(column)]
        block = layer[row]
        fun = block.function[f]

        functions = []
        for b in layer: functions.extend(b.function)

        block_index = row
        insert_index = 0
        if abs(column) + 1 < len(blocks):
            next_layer = blocks[abs(column) + 1]
            for b in next_layer:
                x_offset = b.x
                assert b.prev
                if layer.index(b.prev) > block_index:
                    break
                elif layer.index(b.prev) == block_index:
                    if block.function.index(b.path[-1]) > f:
                        break

                insert_index += 1
        else:
            next_layer = []
            blocks.append(next_layer)

        y_offset = f * (BOX_HEIGHT + 10)
        fun_list = []
        callees = set(map(lambda c: c[1], fun.callees if column >= 0 else fun.callers))
        for ep in callees:
            callee = all_functions[ep]
            fun_list.append(callee)

        if len(fun_list) > 0:
            next_layer.insert(insert_index, Block(
                block,
                block.path + [fun],
                fun_list, 
                0, 0, 0, # Don't set these, rebalancing will do it
                column + 1 if column >= 0 else column - 1))
            
        # Rebalance layers
        self.rebalance_layers(abs(column), column > 0 and 1 or -1)
        
    def rebalance_layers(self, column: int, direction: int = 1):
        blocks = self.callees if direction >= 0 else self.callers
        prev_layer = blocks[column]
        for layer in blocks[column + 1:]:
            functions = []
            if direction > 0:
                for b in prev_layer: functions.extend(b.function)
            else:
                for b in layer: functions.extend(b.function)


            if len(functions) == 0: continue
            x_offset = max(map(lambda f: len(f.name) * FONT_WIDTH + 10, functions)) + 75
            
            # Reset positions
            for block in layer:
                assert block.prev
                block.x = block.prev.x + x_offset
                block.prev_y = block.prev.y - block.prev.function.index(block.path[-1]) * (BOX_HEIGHT + 10)
                block.y = block.prev_y + ((BOX_HEIGHT + 10) * len(block.function)) / 2 - (BOX_HEIGHT + 10) / 2

            shift_layer(layer)
            prev_layer = layer

    def on_mouse_move(self, pos: tuple[float, float]):
        super().on_mouse_move(pos) # type: ignore

        self.hovered = None
        for layer in (self.callees + self.callers):
            for block in layer:
                x, offset_y = block.x, block.y
                if block.layer < 0: x = -x
                for fun in block.function:
                    if (x <= pos[0] <= x + len(fun.name) * FONT_WIDTH + 10) and (offset_y - BOX_HEIGHT <= pos[1] <= offset_y):
                        self.hovered = fun.ep
                        break
                    offset_y -= BOX_HEIGHT + 10

        self.update_hover()

    def update_hover(self):
        self.canvas.after.clear()
        if self.hovered is None:
            return

        with self.canvas.after:
            for layer in (self.callees + self.callers):
                for block in layer:
                    for f, fun in enumerate(block.function):
                        if fun.ep == self.hovered:
                            x, y = block.x, block.y
                            if block.layer < 0: x = -x
                            offset_y = y - f * (BOX_HEIGHT + 10)

                            Color(*get_color_from_hex("#64B5F655"))
                            Rectangle(pos=(x, offset_y - BOX_HEIGHT), size=(len(fun.name) * FONT_WIDTH + 10, BOX_HEIGHT))

    def update_graphics(self):

        def draw_box(text: str, x: float, y: float, cycle: bool = False, color = (1, 1, 1, 1)):
            label = CoreLabel(text=text, font_size=14 * SCALE_FACTOR, font_name=FONT_NAME)
            label.refresh()
            w, h = FONT_WIDTH * len(text), FONT_HEIGHT
            Color(*color)
            Line(width=0.5, rectangle=(x, y - h - 10, w + 10, h + 10))
            if cycle:
                Color(*get_color_from_hex("#FF5555"))
            else: 
                Color(*get_color_from_hex("#DCDCAA"))
            Rectangle(pos=(x + 5, y - h - 5), size=(w, h), texture=label.texture)
        
        def draw_layer(index: int):
            blocks = self.callees if index > 0 else self.callers

            layer = blocks[abs(index)]
            next_layer = None
            if abs(index) + 1 < len(blocks):
                next_layer = blocks[abs(index) + 1]

            for r, block in enumerate(layer):
                x, y = block.x, block.y
                if index < 0: x = -x
                Color(1, 1, 1, 1)
                center = block.prev_y - BOX_HEIGHT / 2

                assert block.prev
                if index > 0:
                    mx = (max(map(lambda f: len(f.name) * FONT_WIDTH + 10, (item for block in blocks[abs(index) - 1] for item in block.function))))
                    mn = (len(block.path[-1].name) * FONT_WIDTH + 10)
                    offset_x = -65 - (mx - mn)
                else:
                    mx = (max(map(lambda f: len(f.name) * FONT_WIDTH + 10, (item for block in layer for item in block.function))))
                    mn = (len(block.function[0].name) * FONT_WIDTH + 10)
                    offset_x = 65 + mn

                x1, y1 = x + offset_x - 10 if index > 0 else x + mx + 65, center - 5

                if abs(index) > 1:
                    self.minus.append(Icon(index, r, 0, x1, y1))
                    Rectangle(pos=(x1, y1), size=(10, 10), texture=self.minus_texture)
                else:
                    if index > 0:
                        Line(width=0.5, points=[x + offset_x - 10, center, x + offset_x, center])
                    else:
                        Line(width=0.5, points=[x + offset_x + 10, center, x + offset_x, center])

                if index > 0:
                    Line(width=0.5, points=[x + offset_x, center, x - 65, center, x - 10, y, x, y])
                else:
                    Line(width=0.5, points=[x + mn, y, x + 10 + mn, y, x + mx + 10, y, x + mx + 65, center])

                offset_y = y
                for f, fun in enumerate(block.function):
                    render_plus = len(fun.callees) > 0 if index > 0 else len(fun.callers) > 0
                    if render_plus and not any(map(lambda b: b.prev == block and b.path[-1] == fun, next_layer or [])):
                        # Render plus icon if there are callees and the next layer for the function is not open
                        x2, y2 = (x + len(fun.name) * FONT_WIDTH + 10) if index > 0 else x - 10, offset_y - BOX_HEIGHT / 2 - 5
                        self.plus.append(Icon(index, r, f, x2, y2))
                        Color(1, 1, 1, 1)
                        Rectangle(pos=(x2, y2), size=(10, 10), texture=self.plus_texture)

                    if fun in duplicate_functions:
                        color = COLORS[fun.ep % len(COLORS)]
                    else: color = (1, 1, 1, 1)

                    draw_box(fun.name, x, offset_y, cycle=fun in block.path, color=color)
                    offset_y -= BOX_HEIGHT + 10

        functions = set()
        duplicate_functions = set()
        for layer in (self.callees + self.callers):
            for block in layer:
                for fun in block.function:
                    if fun in functions:
                        duplicate_functions.add(fun)
                    else:
                        functions.add(fun)

        self.canvas.clear()
        with self.canvas:
            self.plus.clear()
            self.minus.clear()

            draw_box(self.fun.name, 0, 0)

            for i in range(1, len(self.callees)):
                draw_layer(i)

            for i in range(1, len(self.callers)):
                draw_layer(-i)

    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        if touch.button != 'left': return False
        for icon in self.plus:
            if (icon.x <= touch.x <= icon.x + 10) and (icon.y <= touch.y <= icon.y + 10):
                self.open(icon.column, icon.row, icon.f)
                self.update_graphics()
                return True
        for icon in self.minus:
            if (icon.x <= touch.x <= icon.x + 10) and (icon.y <= touch.y <= icon.y + 10):
                self.close(icon.column, icon.row)
                self.update_graphics()
                return True

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

    def move_to_initial_pos(self):
        self.scatter.apply_transform(Matrix().scale(Metrics.density, Metrics.density, Metrics.density))
        x = self.stencil.x + self.stencil.width / 2
        y = self.stencil.y + self.stencil.height / 2
        self.scatter._set_pos((x, y))
