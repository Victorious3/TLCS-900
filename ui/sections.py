import math

from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, Line
from kivy.utils import get_color_from_hex, escape_markup
from kivy.properties import ObjectProperty
from kivy.effects.scroll import ScrollEffect
from kivy.uix.recycleview import RecycleView

from . import main
from .project import Section, DATA_PER_ROW, Instruction
from .main import LABEL_HEIGHT, FONT_HEIGHT, FONT_SIZE, FONT_NAME, FONT_WIDTH, MAX_SECTION_LENGTH, app, iter_all_children_of_type, KWidget
from .context_menu import ContextMenuBehavior, show_context_menu, MenuHandler, MenuItem
from disapi import Loc

class RV(KWidget, RecycleView):
    parent: "main.MainPanel"
    any_hovered = False

    def __init__(self, **kwargs):
        self.selection_start = 0
        self.selection_end = 0
        self.outside_bounds = False
        super().__init__(**kwargs)
        self.effect_x = ScrollEffect()
        self.update_data()
        self.bind(size=lambda *_: self.redraw_children())
        Window.bind(mouse_pos=self.on_mouse_move)

    @classmethod 
    def on_mouse_move(cls, window, pos):
        cls.any_hovered = False
        
    @classmethod
    def update_cursor(cls):
        if cls.any_hovered and app().ctrl_down and not app().any_hovered:
            Window.set_system_cursor("hand")
            app().set_hover()

    def update_data(self):
        data = []
        for section in app().project.sections.values():
            columns = len(section.instructions)
            data.append({"section": section, 
                         "height": columns * FONT_HEIGHT + (LABEL_HEIGHT if section.labels else 0),
                         "width": dp(1500) })

        self.data = data

    def update_from_scroll(self, *largs):
        super().update_from_scroll(*largs)

        def update(dt):
            self.redraw_children()

        Clock.schedule_once(update, 0)
        
        self.parent.arrows.redraw()

    def get_visible_range(self):
        content_height = self.children[0].height - self.height
        scroll_pos = self.scroll_y * content_height

        return scroll_pos, scroll_pos + self.height
    
    def calculate_selection(self, pos: tuple[int, int]):
        for panel in iter_all_children_of_type(self.children[0], SectionData):
            x, y = panel.to_window(panel.x, panel.y)
            if pos[0] > x + panel.width: x1 = 0
            else: x1 = math.floor((pos[0] - x) / (FONT_WIDTH * 3))
            if y <= pos[1] < y + panel.height:
                section = panel.section
                y1 = y - pos[1]
                rows = len(section.instructions)
                row = math.floor(rows + y1 / FONT_HEIGHT)
                if row >= len(section.instructions): continue
                insn = section.instructions[row]
                x1 = min(insn.entry.length - 1, max(x1, 0))
                offset = insn.entry.pc + x1
                return offset
                
        return -1
    
    def reset_selection(self):
        self.selection_start = 0
        self.selection_end = 0
        self.redraw_children()

    def redraw_children(self):
        for panel in iter_all_children_of_type(self.children[0], SectionColumn):
            panel.redraw()

    def on_touch_move_section(self, touch):
        if self.outside_bounds: return
        if touch.button != "left": return
        tx, ty = touch.x, touch.y

        panel = next(iter_all_children_of_type(self.children[0], SectionData))
        x, y = panel.x, panel.y
        if touch.x > x + panel.width:
            end = self.calculate_selection((x + panel.width, ty))
        else:
            end = self.calculate_selection((tx, ty))

        if end > 0:
            self.selection_end = end

        self.redraw_children()
    
    def on_touch_down_selection(self, touch):
        if touch.button != "left": return
        self.outside_bounds = touch.x > self.parent.minimap.x
        if self.outside_bounds: return
        tx, ty = touch.x, touch.y

        panel = next(iter_all_children_of_type(self.children[0], SectionData))
        x, y = panel.x, panel.y
        if touch.x > x + panel.width:
            selection_end = self.calculate_selection((x + panel.width, ty))
            selection_start = self.calculate_selection((x, ty))
        else:
            selection_end = self.calculate_selection((tx, ty))
            selection_start = selection_end

        if not app().shift_down: 
            self.selection_end = selection_end
            self.selection_start = selection_start
        else:
            start = self.selection_start
            end = self.selection_end
            if start > end:
                if selection_end < start: self.selection_end = selection_end
                else: self.selection_start = selection_start
            else:
                if selection_end < end: self.selection_start = selection_start
                else: self.selection_end = selection_end

        self.redraw_children()

class LabelRow(ContextMenuBehavior, TextInput):
    section = ObjectProperty(None)
    rv: RV = ObjectProperty(None, allownone=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = 1, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
        self.height = LABEL_HEIGHT
        self.background_color = 0, 0, 0, 0
        self.foreground_color = 1, 1, 1, 1
        self.padding = dp(250), 0, 0, 0
        self.multiline = False
        self.cursor_color = 0, 0, 0, 0
        self.is_active = False
        self.is_function = False

    def trigger_context_menu(self, touch) -> bool:
        if self.collide_point(touch.x, touch.y):
            text = self.text
            is_function = self.is_function
            section = self.section

            class Handler(MenuHandler):
                def on_select(self, item):
                    if item == "graph":
                        if is_function:
                            app().open_function_graph(text)
                        else:
                            app().open_function_graph_from_label(section.offset)
            
            show_context_menu(Handler(), [
                MenuItem("graph", "Open in function graph")
            ])
            return True
        return False

    def on_section(self, instance, value: Section):
        if len(value.labels) == 0:
            self.disabled = True
            self.opacity = 0
            self.height = 0
            self.is_function = False
        else:
            self.text = value.labels[0].name
            self.disabled = False
            self.opacity = 1
            self.height = LABEL_HEIGHT
            self.is_function = app().project.is_function(self.section.offset)

    def on_double_tap(self):
        self.cursor_color = (1, 1, 1, 1)
        if self.is_active:
            super().on_double_tap()
        self.is_active = True
    
    def _on_focus(self, instance, value, *largs):
        super()._on_focus(instance, value, *largs)
        if value: self.rv.reset_selection()
        else:
            self.cursor_color = (0, 0, 0, 0)
            self.is_active = False

    def _key_down(self, key, repeat=False):
        if key[2].startswith("cursor") and not self.is_active:
            return
        super()._key_down(key, repeat)

    def keyboard_on_textinput(self, window, text):
        if not self.is_active: return
        super().keyboard_on_textinput(window, text)
    

class SectionColumn(Label):
    section = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = None, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
    
    def redraw(self): pass    

class SectionAddresses(KWidget, SectionColumn):
    rv: RV = ObjectProperty(None, allownone=True)

    def on_section(self, instance, section: Section):
        self.text = "\n".join(format(x, "X") for x in map(lambda i: i.entry.pc, section.instructions))
    
    def redraw(self):
        super().redraw()
        self.canvas.before.clear()

        last_position = app().last_position
        if self.section.offset <= last_position < self.section.offset + self.section.length:
            # Draw background on location that has been jumped to
            for i, insn in enumerate(self.section.instructions):
                if insn.entry.pc + insn.entry.length > last_position:
                    width = len(format(insn.entry.pc, "X")) * FONT_WIDTH
                    with self.canvas.before:
                        Color(*get_color_from_hex("#E69533"))
                        Rectangle(pos=(self.x + self.width - width, self.y + (self.height - i * FONT_HEIGHT) - FONT_HEIGHT), size=(width, FONT_HEIGHT))
                    break
        

class SectionData(KWidget, SectionColumn):
    rv: RV = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.width = DATA_PER_ROW * dp(40)
        self.color = get_color_from_hex("#B5CEA8")

    def on_section(self, instance, section: Section):
        lines = []
        for insn in section.instructions:
            data = section.data[
                insn.entry.pc - section.offset :
                insn.entry.pc + insn.entry.length - section.offset]
            lines.append(" ".join(format(x, "0>2X") for x in data))

        self.text = "\n".join(lines)

    def redraw(self):
        start, end = self.rv.selection_start, self.rv.selection_end
        if end < start: start, end = end, start

        self.canvas.before.clear()

        if (self.section.offset <= start <= self.section.offset + self.section.length or
            self.section.offset <= end <= self.section.offset + self.section.length or
            start < self.section.offset and end > self.section.offset + self.section.length):

            row_start = len(self.section.instructions)
            row_end = 0
            start_column = 0
            end_column = 0
            for i, insn in enumerate(self.section.instructions):
                if insn.entry.pc > start:
                    last = self.section.instructions[i - 1]
                    start_column = last.entry.length - insn.entry.pc + start
                    row_start = i
                    break
            else: 
                start_column = self.section.instructions[-1].entry.length - (self.section.offset + self.section.length - start)

            end_length = 0
            for i, insn in reversed(list(enumerate(self.section.instructions))):
                if insn.entry.pc <= end: 
                    end_column = end - insn.entry.pc + 1
                    end_length = insn.entry.length
                    row_end = i
                    break

            with self.canvas.before:
                Color(*get_color_from_hex("#264F78"))

                start_x = start_column * 3 * FONT_WIDTH
                end_x = end_column * 3 * FONT_WIDTH
                width = self.rv.width - self.rv.parent.minimap.width

                if self.section.offset <= start < self.section.offset + self.section.length and row_start - 1 == row_end and end_column < end_length:
                    if start_column == 0:
                        Rectangle(pos=(self.parent.x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(self.x + 3 * FONT_WIDTH, FONT_HEIGHT))
                    Rectangle(pos=(self.x + start_x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(end_x - start_x, FONT_HEIGHT))
                else:
                    if self.section.offset <= start < self.section.offset + self.section.length: 
                        if start_column == 0:
                            Rectangle(pos=(self.parent.x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(width, FONT_HEIGHT))
                        else:
                            Rectangle(pos=(self.x + start_x, self.y + self.height - (row_start * FONT_HEIGHT)), size=(width - start_x - self.x, FONT_HEIGHT))
                    if self.section.offset <= end < self.section.offset + self.section.length and row_end >= row_start:
                        if end_column < end_length:
                            Rectangle(pos=(self.parent.x, self.y + self.height - ((row_end + 1) * FONT_HEIGHT)), size=(self.x + end_x, FONT_HEIGHT))
                        else:
                            Rectangle(pos=(self.parent.x, self.y + self.height - ((row_end + 1) * FONT_HEIGHT)), size=(width, FONT_HEIGHT))


                    if row_start <= row_end:
                        off_y = 0
                        if end >= self.section.offset + self.section.length: off_y = 1
                        Rectangle(pos=(self.parent.x, self.y + self.height - ((row_end + off_y) * FONT_HEIGHT)), size=(width, (row_end + off_y - row_start) * FONT_HEIGHT))



def loc_to_str(insn: Loc):
    ob = app().project.ob
    label = ob.label(insn.loc)
    if label is not None:
        return str(label)
    return str(insn.loc)

class LocationLabel:
    def __init__(self, ep: int, text: str, x: int, y: int, width: int, height: int, is_fun: bool = False):
        self.ep = ep
        self.hovered = False
        self.text = text
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.is_fun = is_fun

def section_to_markup(instructions: list[Instruction], text: list[str], labels: list[LocationLabel]):
    for insn in instructions:
        row_width = len(insn.entry.opcode) + 1
        row = f"[color=#569CD6]{insn.entry.opcode}[/color] "
        for i in range(len(insn.entry.instructions)):
            param = insn.entry.instructions[i]
            if isinstance(param, Loc):
                is_fun = insn.entry.opcode in ("CALL", "CALR")
                label_text = loc_to_str(param)
                t = f"[color=#DCDCAA]{label_text}[/color]"
                labels.append(
                    LocationLabel(int(param), label_text, row_width, len(text), len(label_text), 1, is_fun))
                row += t
                row_width += len(label_text)
            elif isinstance(param, bytearray):
                res = param.decode("ascii", "replace")
                res = "".join(x if 0x7E >= ord(x) >= 0x20 else "." for x in res)
                row += '"' + escape_markup(res) + '"'
                row_width += len(res) + 2
            else:
                insn_text = str(param)
                row += escape_markup(insn_text)
                row_width += len(insn_text)
            if i < len(insn.entry.instructions) - 1:
                row += ", "
                row_width += 2

        text.append(row)

class SectionMnemonic(KWidget, ContextMenuBehavior, SectionColumn):
    rv: RV = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.labels: list[LocationLabel] = []
        self.ctrl_down = False

        Window.bind(on_key_down=self._keydown)
        Window.bind(on_key_up=self._keyup)
        Window.bind(mouse_pos=self._on_mouse_move)
        
    def on_section(self, instance, section: Section):
        self.labels = []
        text = []
        section_to_markup(section.instructions, text, self.labels)
        for label in self.labels:
            label.x = label.x * FONT_WIDTH
            label.y = label.y * FONT_HEIGHT
            label.width *= FONT_WIDTH
            label.height *= FONT_HEIGHT

        self.text = "\n".join(text)

    def _on_mouse_move(self, window, pos):
        x, y = pos
        sx, sy = self.to_window(self.x, self.y)
        for label in self.labels:
            label.hovered = False
            if (sx + label.x <= x <= sx + label.x + label.width and
                sy + self.height - label.y - label.height <= y <= sy + self.height - label.y):
                RV.any_hovered = True
                label.hovered = True
               

        self._on_update()
        RV.update_cursor()

    def trigger_context_menu(self, touch):
        for label in self.labels:
            if label.hovered and self.ctrl_down:
                class Handler(MenuHandler):
                    def on_select(self, item):
                        if item == "goto": app().scroll_to_label(label.text)
                        elif item == "graph": 
                            if label.is_fun:
                                app().open_function_graph(label.text)
                            else:
                                app().open_function_graph_from_label(label.ep)
                
                show_context_menu(Handler(), [
                    MenuItem("goto", f"Go to {'function' if label.is_fun else 'label'}"),
                    MenuItem("graph", "Open in function graph")
                ])
                return True

        return False

    def on_touch_up(self, touch):
        if super().on_touch_up(touch): return True
        for label in self.labels:
            if label.hovered and self.ctrl_down and touch.button == 'left':
                try:
                    self.rv.reset_selection()
                    app().scroll_to_label(label.text)
                    return True
                except ValueError: pass

    def _on_update(self):
        self.canvas.after.clear()

        for label in self.labels:
            if label.hovered and self.ctrl_down:
                color = get_color_from_hex("#64B5F6")

                cl = CoreLabel(text = label.text, font_size = FONT_SIZE, font_name = FONT_NAME)
                cl.refresh()
                              
                with self.canvas.after:
                    Color(*color)
                    Rectangle(texture = cl.texture, pos = (self.x + label.x, self.y + self.height - label.y - label.height), size = cl.texture.size)
                    Line(points=[
                        self.x + label.x, self.y + self.height - label.y - label.height + 1,
                        self.x + label.x + label.width, self.y + self.height - label.y - label.height + 1
                    ], width=dp(1))

    def _keydown(self, window, keyboard: int, keycode: int, text: str, modifiers: list[str]):
        if keycode == 224: 
            self.ctrl_down = True
            self._on_update()
    
    def _keyup(self, window, keyboard: int, keycode: int):
        if keycode == 224: 
            self.ctrl_down = False
            self._on_update()

class SectionPanel(RecycleDataViewBehavior, ContextMenuBehavior, BoxLayout):
    section = ObjectProperty(None)
    rv: RV = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def trigger_context_menu(self, touch):
        if not self.collide_point(touch.x, touch.y): return
        if (touch.x < self.rv.width - self.rv.parent.minimap.width):
            rv = self.rv
            class Handler(MenuHandler):
                def on_select(self, item):
                    if item == "dis": 
                        a = app()
                        def callback():
                            a.rv.update_data()
                            a.minimap.redraw()
                            a.arrows.recompute_arrows()
                            a.arrows.redraw()
                            Clock.schedule_once(lambda dt: a.scroll_to_offset(rv.selection_start), 0)
                
                        a.project.disassemble(rv.selection_start, callback)
                        
            show_context_menu(Handler(), [
                MenuItem("label", "Insert Label"),
                MenuItem("dis", "Disassemble from here"),
                MenuItem("dis_oneshot", "Disassemble oneshot"),
                MenuItem("dis_selected", "Disassemble selected"),
            ])

            return True

    def refresh_view_attrs(self, rv, index, data):
        super().refresh_view_attrs(rv, index, data)

        section: Section = data["section"]
        self.ids["label"].section = section
        self.ids["data"].section = section
        self.ids["addresses"].section = section
        self.ids["mnemonics"].section = section
        
    def is_visible(self):
        visible_range = app().rv.get_visible_range()   
        window = MAX_SECTION_LENGTH * FONT_HEIGHT     
        return self.y + self.height >= visible_range[0] - window and self.y <= visible_range[1] + window
