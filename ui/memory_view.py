import math
from typing import cast
from kivy.uix.widget import Widget
from kivy.uix.relativelayout import RelativeLayout
from kivy.properties import ObjectProperty, NumericProperty
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Rectangle
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock

from ui.kivytypes import KWidget

from .project import DATA_PER_ROW, MAX_SECTION_LENGTH, CodeSection, DataSection, Instruction, Section, VirtualByteArray
from .main import FONT_HEIGHT, app
from .sections import RV, EditableLabel, ScrollBar, SectionBase, SectionData, FONT_SIZE, FONT_NAME, LABEL_HEIGHT
from .dock.dock import SerializableTab

from disapi import InsnEntry, Label, LabelKind
from tcls_900.tlcs_900 import BYTE, LWORD, WORD

class MemoryViewTab(SerializableTab):
    content: "MemoryView"

    def __init__(self, **kwargs):
        super().__init__(text="Memory View", closeable=True, source="ui/resources/memory.png", **kwargs)
        self.add_widget(MemoryView())

    def serialize(self) -> dict:
        data = super().serialize()
        self.content.serialize(data)
        return data

    @classmethod
    def deserialize(cls, data: dict) -> "MemoryViewTab":
        tab = MemoryViewTab()
        return tab
    
    def deserialize_post(self, data: dict):
        self.content.deserialize_post(data)
    
class MemoryView(RelativeLayout):
    def __init__(self, **kwargs):
        self.rv = cast(MemoryRV, None)
        self.scrollbar: ScrollBar
        self.highlighted_list = []
        super().__init__(**kwargs)

    def on_kv_post(self, base_widget):
        self.rv = self.ids["rv"]
        self.scrollbar = self.ids["scrollbar"]

    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        return self.rv.on_touch_down_selection(touch)
    
    def on_touch_move(self, touch):
        if super().on_touch_move(touch): return True
        return self.rv.on_touch_move_section(touch)
    
    def serialize(self, data: dict):
        data["scroll_x"] = self.scrollbar.view.scroll_x
        data["scroll_y"] = self.rv.scroll_y
        data["selection_start"] = self.rv.selection_start
        data["selection_end"] = self.rv.selection_end

        expanded_sections: list[int] = []
        for d in self.rv.data:
            if "collapse" in d:
                expanded_sections.append(d["collapse"])
        data["expanded_sections"] = expanded_sections

    def deserialize_post(self, data: dict):
        if "expanded_sections" in data:
            expanded_sections: list[int] = data["expanded_sections"]
            for collapse_index in expanded_sections:
                collapsed_sections = self.rv.data[collapse_index-1]["collapsed_sections"]
                if collapsed_sections is not None:
                    del self.rv.data[collapse_index-1]["collapsed_sections"]
                    collapsed_sections[-1]["collapse"] = collapse_index
                    collapsed_sections[-1]["collapse_size"] = len(collapsed_sections)
                    self.rv.data[collapse_index:collapse_index] = collapsed_sections
            self.rv.recalculate_height()
            self.rv.refresh_from_data()

        if "scroll_y" in data:
            self.rv.scroll_y = data["scroll_y"]
        if "scroll_x" in data:
            self.scrollbar.view.scroll_x = data["scroll_x"]
        if "selection_start" in data:  
            self.rv.selection_start = data["selection_start"]
        if "selection_end" in data:
            self.rv.selection_end = data["selection_end"]

class MemorySectionData(SectionData):
    def trigger_context_menu(self, touch): return False

def typename_from_label(type: int) -> str:
    if type == BYTE: return "byte"
    if type == WORD: return "short"
    if type == LWORD: return "int"
    return "unknown"

def size_from_label(type: int) -> int:
    if type == BYTE: return 1
    if type == WORD: return 2
    if type == LWORD: return 4
    return 1

def directive_from_label(type: int) -> str:
    if type == BYTE: return ".db"
    if type == WORD: return ".dw"
    if type == LWORD: return ".dd"
    return ".db"

class MemorySection(SectionBase):
    rv: "MemoryRV"

    def refresh_view_attrs(self, rv: RV, index, data):
        super().refresh_view_attrs(rv, index, data)
        section: Section = data["section"]
        self.ids["header"].display = len(section.labels) > 0

        snip: MemorySnip = self.ids["snip"]

        snip.disabled = False
        snip.opacity = 1
        snip.height = dp(20)

        if "collapsed_sections" in data:
            snip.collapsed_sections = data["collapsed_sections"]
            snip.collapse = -1
            snip.collapse_size = 0
            snip.index = index
        elif "collapse" in data:
            snip.collapse = data["collapse"]
            snip.collapse_size = data["collapse_size"]
            snip.index = index
        else:
            snip.disabled = True
            snip.opacity = 0
            snip.height = 0
            snip.collapsed_sections = None
            snip.collapse = -1
            snip.collapse_size = 0
            snip.index = -1

        if len(section.labels) > 0:
            label = app().project.ob.label(section.offset)
            assert label
            self.ids["type"].text = typename_from_label(label.type)
            

class MemorySnip(KWidget, Widget):
    parent: MemorySection
    collapsed_sections: list[dict] | None = ObjectProperty(None, allownone=True)
    xoffset: int = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.index = -1
        self.collapse = -1
        self.collapse_size = 9
        self.bind(pos=self.refresh, size=self.refresh, xoffset=self.refresh, collapsed_sections=self.refresh)

    def refresh(self, *args):
        with self.canvas:
            self.canvas.clear()
            if self.collapsed_sections is not None:
                first: Section = self.collapsed_sections[0]["section"]
                last: Section = self.collapsed_sections[-1]["section"]
                label = CoreLabel(text=f"... ({last.offset + last.length - first.offset} bytes collapsed) ...", font_size=FONT_SIZE, font_name=FONT_NAME, color=get_color_from_hex("#888888"))
                label.refresh()
                Rectangle(texture=label.texture, pos=(self.x + self.xoffset + dp(250), self.y), size=label.texture.size)
            elif self.collapse >= 0:
                data_length = len(self.parent.rv.data)
                first: Section = self.parent.rv.data[min(data_length-1, self.collapse)]["section"]
                last: Section = self.parent.rv.data[min(data_length-1, self.collapse+self.collapse_size-1)]["section"]
                label = CoreLabel(text=f"... (Collapse {last.offset + last.length - first.offset} bytes) ...", font_size=FONT_SIZE, font_name=FONT_NAME, color=get_color_from_hex("#888888"))
                label.refresh()
                Rectangle(texture=label.texture, pos=(self.x + self.xoffset + dp(250), self.y), size=label.texture.size)

    def on_touch_down(self, touch):
        if super().on_touch_down(touch): return True
        if not self.collide_point(*touch.pos): return False
        if self.collapse >= 0:
            # Collapse back
            collapsed_sections = self.parent.rv.data[self.collapse:self.collapse+self.collapse_size]
            del self.parent.rv.data[self.collapse:self.collapse+self.collapse_size]
            last = self.parent.rv.data[self.collapse-1]
            last["collapsed_sections"] = collapsed_sections

            # Subtract from all following collapse indices
            for d in self.parent.rv.data[self.collapse:]:
                if "collapse" in d:
                    d["collapse"] -= self.collapse_size

            self.parent.rv.recalculate_height()
            self.parent.rv.refresh_from_data()
            section: Section = last["section"]
            Clock.schedule_once(lambda dt: self.parent.rv.scroll_to_offset(section.offset + section.length - 1))
        elif self.collapsed_sections is not None:
            # Expand
            del self.parent.rv.data[self.index]["collapsed_sections"]
            self.collapsed_sections[-1]["collapse"] = self.index + 1
            self.collapsed_sections[-1]["collapse_size"] = len(self.collapsed_sections)
            self.parent.rv.data[self.index+1:self.index+1] = self.collapsed_sections
            
            # Add to all following collapse indices
            for d in self.parent.rv.data[self.index + 1 + len(self.collapsed_sections):]:
                if "collapse" in d:
                    d["collapse"] += len(self.collapsed_sections)

            self.parent.rv.recalculate_height()
            self.parent.rv.refresh_from_data()
            section: Section = self.collapsed_sections[-1]["section"]
            Clock.schedule_once(lambda dt: self.parent.rv.scroll_to_offset(section.offset + section.length - 1))
        return True

MIN_COLLAPSE_SIZE = DATA_PER_ROW * 5

class MemoryRV(RV):

    # We don't have arrows
    def redraw_arrows(self): pass

    def update_data(self):
        data = []
        section: Section
        project = app().project
        
        for region in project.addresses:
            if region.start == project.org:
                for section in project.sections.values():
                    if isinstance(section, CodeSection): continue
                    label2 = project.ob.label(section.offset)
                    if label2 is not None and label2.kind == LabelKind.DATA and label2.type is not None:
                        offset = size_from_label(label2.type)
                        d = int.from_bytes(cast(bytearray, section.data[:offset]), "big")
                        label_section = DataSection(section.offset, offset, [label2], section.data[0:offset], [Instruction(InsnEntry(section.offset, offset, directive_from_label(label2.type), (d,)))])
                        data.append({"section": label_section, 
                                    "rv": self})
                        if section.length - offset > 0:
                            rest_section = DataSection(section.offset + offset, section.length - offset, [], section.data[offset:])
                            data.append({"section": rest_section, 
                                        "rv": self})
                    else:
                        data.append({"section": section, 
                                    "rv": self})
            else:
                labels = project.ob.labels.values()
                label: Label
                filtered_labels = []
                for label in labels:
                    if label.location >= region.start and label.location < region.start + region.size and label.kind == LabelKind.DATA:
                        filtered_labels.append(label)
                filtered_labels.sort(key=lambda l: l.location)

                for i in range(len(filtered_labels)):
                    label = filtered_labels[i]
                    start = label.location
                    end = region.start + region.size
                    if i + 1 < len(filtered_labels):
                        end = filtered_labels[i + 1].location
                    size = end - start

                    if label.type is not None:
                        name = directive_from_label(label.type)
                        labelsize = min(size, size_from_label(label.type))
                        size -= labelsize
                        vdata = VirtualByteArray(labelsize, 0x0)
                        data.append({"section": DataSection(label.location, labelsize, [label], vdata, [Instruction(InsnEntry(start, labelsize, name, (0,)))]), 
                                    "rv": self})
                    else: labelsize = 0
                    
                    for r in range(0, size, MAX_SECTION_LENGTH):
                        chunk_size = min(MAX_SECTION_LENGTH, size - r)
                        vdata = VirtualByteArray(chunk_size, 0x0)
                        data.append({"section": DataSection(start + r + labelsize, chunk_size, [], vdata), 
                                    "rv": self})
                        
        new_data = []
        i = 0
        while i < len(data):
            d = data[i]
            new_data.append(d)
            section: Section = d["section"]
            collapsed_sections = []
            i += 1
            if i < len(data):
                # Append one section, then collapse all following sections without labels
                first_d = data[i]
                next_d = first_d
                if len(next_d["section"].labels) > 0:
                    continue
                new_data.append(next_d)
                i += 1
                while True:
                    if i >= len(data): break
                    next_d = data[i]
                    next_section: Section = next_d["section"]
                    if len(next_section.labels) > 0: 
                        break
                    collapsed_sections.append(next_d)
                    i += 1
                if collapsed_sections:
                    first: Section = collapsed_sections[0]["section"]
                    last: Section = collapsed_sections[-1]["section"]
                    if last.offset - first.offset + last.length > MIN_COLLAPSE_SIZE:
                        first_d["collapsed_sections"] = collapsed_sections
                    else:
                        new_data.extend(collapsed_sections)

        self.data = new_data

        self.recalculate_height()

    def recalculate_height(self):
        for data in self.data:
            section: Section = data["section"]
            rows = math.ceil(section.length / DATA_PER_ROW)
            height = rows * FONT_HEIGHT
            if len(section.labels) > 0:
                height += LABEL_HEIGHT
            if "collapsed_sections" in data or "collapse" in data:
                height += dp(20)
            data["height"] = height

class MemoryMinimap(Widget): pass

class MemoryLabel(EditableLabel):
    section: Section = ObjectProperty(None)
    rv: RV = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = 1, None
        self.font_size = FONT_SIZE
        self.font_name = FONT_NAME
        self.padding = (0, 0, 0, 0)
        self.height = LABEL_HEIGHT

    def on_section(self, instance, value: Section):
        self.refresh()

    def refresh(self, **kwargs):
        if len(self.section.labels) > 0:
            self.text = self.section.labels[0].name
