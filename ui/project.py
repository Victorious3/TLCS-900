import os
from pytreemap import TreeMap
from abc import ABC
from functools import reduce
from disapi import InputBuffer, OutputBuffer, InsnPool, Insn, InsnEntry, Label

from .popup import InvalidInsnPopup

DATA_PER_ROW = 7
MAX_SECTION_LENGTH = DATA_PER_ROW * 40

class Instruction:
    def __init__(self, entry: InsnEntry):
        self.entry = entry

class Section(ABC):
    def __init__(self, offset: int, length: int, labels: list[Label], data: bytearray, instructions: list[Instruction]):
        self.offset = offset
        self.length = length
        self.labels = labels
        self.data = data
        self.instructions = instructions

    def __str__(self):
        return f"{self.__class__.__name__}: {list(map(str, self.labels))} {self.offset:X} -> {self.offset + self.length:X}"

class DataSection(Section): 
    def __init__(self, offset, length, labels, data, instructions = None):
        if instructions is None:
            instructions = []
            for i in range(0, length, DATA_PER_ROW):
                width = min(DATA_PER_ROW, length - i)
                res = data[i:i+width]
                instructions.append(Instruction(InsnEntry(offset + i, width, ".db", (res,))))
                
        super().__init__(offset, length, labels, data, instructions)

class CodeSection(Section): pass

def label_list(label):
    if label is None: return []
    return [label]

class Project:
    def __init__(self, path: str):
        self.path = path
        self.sections = TreeMap()
        self.ib: InputBuffer = InputBuffer
        self.ob: OutputBuffer = None
        self.pool: InsnPool = None
        self.file_len = 0

    def disassemble(self, ep: int, callback):
        # TODO make this part of the API instead of messing with the internals manually
        old_map = self.ob.insnmap
        old_locations = self.pool.locations.copy()
        old_access = self.ib.access.copy()

        new_map = {}
        self.ob.insnmap = new_map # Reset instruction map to get a diff later
        self.pool.query(Insn(self.pool, self.ib, self.ob, ep))
        error = self.pool.poll_all()

        def cont(popup):
            self._update_data(new_map)

            old_map.update(new_map)
            self.ob.insnmap = old_map
            callback()
            if popup: 
                popup.dismiss()

        def close(popup):
            self.ob.insnmap = old_map
            self.ib.access = old_access
            self.pool.locations = old_locations
            popup.dismiss()

        if error > 0:
            popup = InvalidInsnPopup(instruction=error)
            popup.bind(on_close=close)
            popup.bind(on_continue=cont)
            popup.open()
        else: cont(None)

    def _update_data(self, new_map: dict):
        self.ob.compute_labels(self.ib.entry_point, self.file_len + self.ib.entry_point)

        sections = []
        for k, v in sorted(new_map.items()):
            v = list(v)
            self.extract_sections(v, sections)

        sections: list[Section] = reduce(list.__add__, map(self.split_section, sections), [])
        in_sections = list(self.sections.values())
        
        if len(sections) > 0:
            i, j = 0, 0
            total = len(in_sections)
            while i < total:
                in_section = in_sections[i]
                if j >= len(sections): break
                section = sections[j]
                # Note: Only data sections can get replaced. Code sections need to be marked as data sections first before they can be considered for replacement
                if isinstance(in_section, DataSection) and in_section.offset + in_section.length > section.offset:
                    insn: list[Instruction] = list(filter(lambda i: i.entry.pc < section.offset, in_section.instructions))
                    if len(insn) > 0:
                        last_insn = insn[-1]
                        if last_insn.entry.pc + last_insn.entry.length > section.offset:
                            ln = section.offset - last_insn.entry.pc
                            off = last_insn.entry.pc - in_section.offset
                            insn[-1] = Instruction(InsnEntry(last_insn.entry.pc, ln, ".db", (in_section.data[off:off + ln + 1],)))

                    # Section before
                    if section.offset - in_section.offset > 0:
                        ln = section.offset - in_section.offset
                        in_sections[i] = in_section.__class__(in_section.offset, ln, in_section.labels, in_section.data[:ln + 1], insn)
                    
                        # New section
                        in_sections.insert(i + 1, section)
                        i += 1; total += 1
                    else:
                        in_sections[i] = section

                    # Section after
                    ln = in_section.length - section.length - (section.offset - in_section.offset)
                    if ln > 0:
                        insn_after: list[Instruction] = list(filter(lambda i: i.entry.pc + i.entry.length > section.offset + section.length, in_section.instructions))
                        # Shorten first data
                        ln2 = insn_after[0].entry.pc + insn_after[0].entry.length - (section.offset + section.length)
                        off = (section.offset + section.length) - in_section.offset

                        insn_after[0] = Instruction(InsnEntry(section.offset + section.length, ln2, ".db", (in_section.data[off:off + ln2],)))
                        in_sections.insert(i + 1, DataSection(section.offset + section.length, ln, [], in_section.data[off:], insn_after))
                        
                        total += 1

                    # Remove overlaps
                    while i + 1 < len(in_sections):
                        next_section = in_sections[i + 1]
                        #print(f"{section.offset:X} {section.length} {next_section.offset:X} {next_section.length}")
                        
                        if next_section.offset >= section.offset:
                            # Remove whole section if new section covers it completely
                            if next_section.offset + next_section.length <= section.offset + section.length:
                                del in_sections[i + 1]
                                total -= 1
                            elif next_section.offset < section.offset + section.length:
                                #print(f"{section.offset:X} {section.length} {next_section.offset:X} {next_section.length}")
                                # Partial overlap
                                ln3 = next_section.length - (section.offset + section.length - next_section.offset)
                                in_sections[i + 1] = DataSection(section.offset + section.length, ln3, [], next_section.data[next_section.length - ln3:])
                                break
                            else: break
                        else: break

                    j += 1
                    # TODO We might want to merge sections together if the result is smaller than MAX_SECTION_LENGTH
                i += 1

            # TODO Don't recreate the map from scratch, this only makes things slower and not faster
            self.sections.clear()
            for section in in_sections:
                self.sections[section.offset] = section
                

    def extract_sections(self, v: list[InsnEntry], out_list: list[Section]) -> int:
        org = self.ib.entry_point
        i = 1
        start = 0
        last_label = self.ob.label(v[start].pc)
        label = None

        if len(v) == 1:
            v1 = v[start]
            out_list.append(
                CodeSection(v1.pc, v1.length, 
                            label_list(last_label), 
                            self.ib.buffer[v1.pc - org:v1.pc + v1.length + 1 - org], 
                            list(map(Instruction, v[start:start+1]))))
            
            return v1.pc + v1.length
        
        while True:
            while label is None:
                label = self.ob.label(v[i].pc)
                i += 1
                if i > len(v) - 1: break
        
            if label is not None:
                vs = v[start]
                ve = v[i - 2]
                s = vs.pc
                e = ve.pc + ve.length - vs.pc
                data = self.ib.buffer[s - org:s + e + 1 - org]
                out_list.append(CodeSection(s, e, label_list(last_label), data, list(map(Instruction, v[start:i - 1]))))

                start = i - 1
                last_label = label
                label = None
            
            if i > len(v) - 1:
                break
        
        s = v[start].pc
        e = v[-1].pc + v[-1].length - s
        data = self.ib.buffer[s - org:s + e + 1 - org]
        out_list.append(CodeSection(s, e, label_list(last_label), data, list(map(Instruction, v[start:]))))

        return s + e
    
    def split_section(self, section: Section):
        if section.length < MAX_SECTION_LENGTH:
            return [section]
        
        ctor = section.__class__
        res = []
        labels = section.labels
        last = 0
        last_i = 0
        i = 0
        offset = 0
        for insn in section.instructions:
            offset += insn.entry.length
            if offset - last > MAX_SECTION_LENGTH:
                data = section.data[last:offset]
                res.append(ctor(section.offset + last, offset - insn.entry.length - last, labels, data, section.instructions[last_i:i]))
                last = offset - insn.entry.length
                last_i = i
                labels = []

            i += 1
        
        if last < section.length:
            res.append(ctor(section.offset + last, section.length - last, labels, section.data[last:], section.instructions[last_i:]))

        return res

    def rescan(self, ep: int, org: int):
        self.sections.clear()
        self.file_len = os.path.getsize(self.path)

        with open(self.path, 'rb') as f:
            ib = InputBuffer(f, self.file_len, entry_point=org, exit_on_invalid=True)
            ob = OutputBuffer(None)
            self.ob = ob
            self.ib = ib

            from tcls_900 import tlcs_900 as proc

            self.pool = InsnPool(proc)
            insn = Insn(self.pool, ib, ob, ep)

        self.pool.query(insn)
        self.pool.poll_all()

        ob.compute_labels(org, self.file_len + org)

        sections: list[Section] = list()
        def output_db(nxt: int, last: int):
            diff = nxt - last
            if diff < 1: return

            last_label = ob.label(last)
            start = last
            for i in range(last + 1, nxt):
                label = ob.label(i)
                if label is not None:
                    length = i - start
                    buf = ib.buffer[start - org:i - org]
                    sections.append(DataSection(start, length, label_list(last_label), buf))
                    last_label = label
                    start = i
            
            length = nxt - start
            if length > 0:
                buf = ib.buffer[start - org:nxt - org]
                sections.append(DataSection(start, length, label_list(last_label), buf))
        
        last = org

        # Load the sections
        for k, v in sorted(ob.insnmap.items()):
            v = list(v)
            output_db(v[0].pc, last)
            last = self.extract_sections(v, sections)
        
        output_db(self.file_len + org, last)

        sections = reduce(list.__add__, map(self.split_section, sections), [])

        for section in sections:
            self.sections[section.offset] = section

        #for section in self.sections:
        #    print(section)
    
    def analyze_functions(self):
        # Find all functions
        for ep in self.ob.calls:
            self.analyze_function(ep)
        print(len(self.ob.calls))

    def analyze_function(self, ep: int):
        section: Section = self.sections.get(ep)
        if not section: return
        name = section.labels[0]
        print(name)


def load_project(path: str, ep: int, org: int) -> Project:
    proj = Project(path)
    proj.rescan(ep, org)
    return proj