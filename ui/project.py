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
    def __init__(self, offset: int, length: int, labels: list[Label], data: bytearray):
        self.offset = offset
        self.length = length
        self.labels = labels
        self.data = data

    def __str__(self):
        return f"{self.__class__.__name__}: {list(map(str, self.labels))} {self.offset:X} -> {self.offset + self.length:X}"

class DataSection(Section):
    def __init__(self, offset, length, labels, data):
        super().__init__(offset, length, labels, data)

class CodeSection(Section):
    def __init__(self, 
                 offset: int, length: int, labels: list[Label], 
                 data: bytearray, instructions: list[Instruction]):
        super().__init__(offset, length, labels, data)
        self.instructions = instructions

class Project:
    def __init__(self, path: str):
        self.path = path
        self.sections: list[Section] = []
        self.ib: InputBuffer = InputBuffer
        self.ob: OutputBuffer = None

    def rescan(self, ep: int, org: int, oneshot = False):
        self.sections = [] # TODO Only update parts that changed

        file_len = os.path.getsize(self.path)

        with open(self.path, 'rb') as f:
            ib = InputBuffer(f, file_len, entry_point=org)
            ob = OutputBuffer(None)
            self.ob = ob
            self.ib = ib

            from tcls_900 import tlcs_900 as proc

            pool = InsnPool(proc)
            insn = Insn(pool, ib, ob, ep)

        pool.query(insn)
        pool.poll_all()

        ob.compute_labels(org, file_len + org)

        def label_list(label):
            if label is None: return []
            return [label]

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

            i = 1
            start = 0
            last_label = ob.label(v[start].pc)
            label = None

            if len(v) == 1:
                v1 = v[start]
                self.sections.append(CodeSection(v1.pc, v1.length, label_list(last_label), ib.buffer[v1.pc - org:v1.pc + v1.length + 1 - org], list(map(Instruction, v[start:start+1]))))
                last = v1.pc + v1.length
            else:  
                while True:
                    while label is None:
                        label = ob.label(v[i].pc)
                        i += 1
                        if i > len(v) - 1: break
                
                    if label is not None:
                        vs = v[start]
                        ve = v[i - 1]
                        s = vs.pc
                        e = ve.pc + ve.length - vs.pc
                        data = ib.buffer[s - org:s + e + 1 - org]
                        self.sections.append(CodeSection(s, e, label_list(last_label), data, list(map(Instruction, v[start:i - 1]))))

                        start = i - 1
                        last_label = label
                        label = None
                    
                    if i > len(v) - 1:
                        break
                
                s = v[start].pc
                e = v[-1].pc + v[-1].length - s
                data = ib.buffer[s - org:s + e + 1 - org]
                self.sections.append(CodeSection(s, e, label_list(last_label), data, list(map(Instruction, v[start:]))))

                last = s + e
        
        output_db(file_len + org, last)

        def split_section(section: Section):
            if section.length < MAX_SECTION_LENGTH:
                return [section]
            
            res = []
            if isinstance(section, DataSection):
                labels = section.labels
                for i in range(0, section.length, MAX_SECTION_LENGTH):
                    diff = min(MAX_SECTION_LENGTH, section.length - i + 1)
                    res.append(DataSection(section.offset + i, diff, labels, section.data[i:i + diff + 1]))
                    labels = []
            elif isinstance(section, CodeSection):
                labels = section.labels
                last = 0
                last_i = 0
                i = 0
                offset = 0
                for insn in section.instructions:
                    offset += insn.entry.length
                    if offset - last + insn.entry.length > MAX_SECTION_LENGTH:
                        data = section.data[last:offset]
                        res.append(CodeSection(section.offset + offset, offset - last, labels, data, section.instructions[last_i:i]))
                        last = offset - insn.entry.length
                        last_i = i
                        labels = []

                    i += 1
                
                if last < section.length:
                    res.append(CodeSection(section.offset + last, section.length - last, labels, section.data[last:], section.instructions[last_i:]))

            return res

        self.sections = reduce(list.__add__, map(split_section, self.sections))

        #for section in self.sections:
        #    print(section)
            


def load_project(path: str, ep: int, org: int) -> Project:
    proj = Project(path)
    proj.rescan(ep, org)
    return proj