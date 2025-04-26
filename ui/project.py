import os
from abc import ABC
from disapi import InputBuffer, OutputBuffer, InsnPool, Insn, InsnEntry, Label, insnentry_to_str


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
        self.sections = []

    def rescan(self, ep: int, org: int, oneshot = False):
        self.sections = [] # TODO Only update parts that changed

        file_len = os.path.getsize(self.path)

        with open(self.path, 'rb') as f:
            ib = InputBuffer(f, file_len, entry_point=org)
            ob = OutputBuffer(None)

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
                    length = i - start - 1
                    buf = ib.buffer[start - org:i - org]
                    self.sections.append(DataSection(start, length, label_list(last_label), buf))
                    last_label = label
                    start = i
            
            length = nxt - start - 1
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
                self.sections.append(CodeSection(v[start].pc, 1, label_list(last_label), data, map(Instruction, v[start:start+1])))
                last = v[start].pc + 1
            else:  
                while True:
                    while label is None:
                        v2 = v[i]
                        label = ob.label(v2.pc)
                        if i >= len(v) - 1: break
                        i += 1

                    if i >= len(v) - 1: break
                
                    if label is not None:
                        vs = v[start]
                        ve = v[i - 1]
                        s = vs.pc
                        e = ve.pc - vs.pc - 1
                        data = ib.buffer[s - org:s + e - org]
                        self.sections.append(CodeSection(s, e, label_list(last_label), data, map(Instruction, v[start:i])))
                    
                    last_label = label
                    label = None
                    start = i - 1

                s = v[start].pc
                e = v[-1].pc + v[-1].length - s - 1
                data = ib.buffer[s - org:s + e - org]
                self.sections.append(CodeSection(s, e, label_list(last_label), data, map(Instruction, v[start:-1])))

                last = s + e + 1

        output_db(file_len + org, last)
        for section in self.sections:
            print(section)
            


def load_project(path: str, ep: int, org: int) -> Project:
    proj = Project(path)
    proj.rescan(ep, org)
    return proj