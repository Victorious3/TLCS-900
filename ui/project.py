import os
from abc import ABC
from functools import reduce
from disapi import InputBuffer, OutputBuffer, InsnPool, Insn, InsnEntry, Label

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
        self.sections: list[Section] = []
        self.ib: InputBuffer = InputBuffer
        self.ob: OutputBuffer = None
        self.pool: InsnPool = None

    def disassemble(self, ep: int):
        old_map = self.ob.insnmap
        new_map = {}
        self.ob.insnmap = new_map # Reset instruction map to get a diff later
        self.pool.query(Insn(self.pool, self.ib, self.ob, ep))
        self.pool.poll_all()

        sections = []
        for k, v in sorted(new_map.items()):
            v = list(v)
            self.extract_sections(v, sections)

        sections = reduce(list.__add__, map(self.split_section, sections))
        for i in range(len(self.sections)): pass

        old_map.update(new_map)
        self.ob.insnmap = old_map

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
                res.append(ctor(section.offset + last, offset - last, labels, data, section.instructions[last_i:i]))
                last = offset - insn.entry.length
                last_i = i
                labels = []

            i += 1
        
        if last < section.length:
            res.append(ctor(section.offset + last, section.length - last, labels, section.data[last:], section.instructions[last_i:]))

        return res

    def rescan(self, ep: int, org: int):
        self.sections = []
        file_len = os.path.getsize(self.path)

        with open(self.path, 'rb') as f:
            ib = InputBuffer(f, file_len, entry_point=org)
            ob = OutputBuffer(None)
            self.ob = ob
            self.ib = ib

            from tcls_900 import tlcs_900 as proc

            self.pool = InsnPool(proc)
            insn = Insn(self.pool, ib, ob, ep)

        self.pool.query(insn)
        self.pool.poll_all()

        ob.compute_labels(org, file_len + org)

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
                    self.sections.append(DataSection(start, length, label_list(last_label), buf))
                    last_label = label
                    start = i
            
            length = nxt - start
            if length > 0:
                buf = ib.buffer[start - org:nxt - org]
                self.sections.append(DataSection(start, length, label_list(last_label), buf))
        
        last = org

        # Load the sections
        for k, v in sorted(ob.insnmap.items()):
            v = list(v)
            output_db(v[0].pc, last)
            last = self.extract_sections(v, self.sections)
        
        output_db(file_len + org, last)

        self.sections = reduce(list.__add__, map(self.split_section, self.sections))

        #for section in self.sections:
        #    print(section)
            


def load_project(path: str, ep: int, org: int) -> Project:
    proj = Project(path)
    proj.rescan(ep, org)
    return proj