import os
from dataclasses import dataclass, field
from pytreemap import TreeMap
from abc import ABC
from functools import reduce
from itertools import takewhile
from graphviz import Digraph

from disapi import InputBuffer, OutputBuffer, InsnPool, Insn, InsnEntry, Label, Loc, insnentry_to_str
from tcls_900.tlcs_900 import Reg, Mem, MemReg, LWORD, WORD # TODO Specific import
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

# Used for function analysis
class CodeBlock:
    # A CodeBlock may have an arbitrary amount of predecessors but only up to two successors.
    # Every Block ends with a branching instruction or RET
    def __init__(self, insn: list[Instruction], pred: list["CodeBlock"] = None, succ: list[("CodeBlock", bool)] = None):
        self.insn = insn
        self.ep = insn[0].entry.pc
        self.pred = pred or []
        self.succ = succ or []

# Wrapper around Reg to supply equals
class WReg:
    def __init__(self, r: Reg):
        self.r =r

    def __str__(self):
        return str(self.r)
    
    def __hash__(self):
        return self.r.reg
    
    def __eq__(self, value):
        if isinstance(value, WReg):
            return self.r.addr == value.r.addr
        return False

def is_jump_insn(insn: Instruction):
    return insn.entry.opcode in ("JR", "JRL", "JP", "DJNZ")

def get_jump_location(insn: Instruction) -> Loc:
    entry = insn.entry
    if entry.opcode == "JP":
        if len(entry.instructions) == 1: 
            return entry.instructions[0]
    elif entry.opcode in ("JR", "JRL", "DJNZ"):
        return entry.instructions[1] 

    return None

def get_registers(value: Reg | Mem) -> list[WReg]:
    if isinstance(value, Reg): return [WReg(value)]
    elif isinstance(value, MemReg):
        if value.reg2: return [WReg(value.reg1), WReg(value.reg2)]
        else: return [WReg(value.reg1)]
    else: return []

def get_load_register(insn: Instruction) -> list[WReg]:
    if insn.entry.opcode in ("BS1B", "BS1F", "DJNZ", "DEC", "INC", "LD", "LDC", "LDCF", "MDEC1", "MDEC2", "MDEC4", "MINC1", "MINC2", "MINC4", "ORCF", "RL", "RLC", "RR", "RRC", "SET", "TSET", "XORCF"): #second argument
        return get_registers(insn.entry.instructions[1])
    elif insn.entry.opcode in ("CPL", "DAA", "EXTS", "EXTZ", "MIRR", "NEG", "PAA"): # first argument
        return get_registers(insn.entry.instructions[0])
    elif insn.entry.opcode in ("ADC", "ADD", "AND", "ANDCF", "BIT", "DIV", "DIVS", "EX", "MUL", "MULS", "OR", "RLD", "RRD", "SBC", "SLA", "SLL", "SRA", "SRL", "SUB", "XOR"): #first and second argument
        return get_registers(insn.entry.instructions[0]) + get_registers(insn.entry.instructions[1])
    elif insn.entry.opcode in ("CPD", "CPDR", "CPI", "CPIR"):
        return get_registers(insn.entry.instructions[0]) + get_registers(insn.entry.instructions[1]) + [Reg(False, WORD, 0xE4)] # BC
    elif insn.entry.opcode == "MULA":
        return get_registers(insn.entry.instructions[0]) + [Reg(False, LWORD, 0xEC), Reg(False, LWORD, 0xE8)] # XHL, XDE
    elif insn.entry.opcode == "SWI":
        return [Reg(False, LWORD, 0xFC)] # XSP
    elif insn.entry.opcode in ("UNLK", "LINK"):
        return get_registers(insn.entry.instructions[0]) + [Reg(False, LWORD, 0xFC)] # XSP
    elif insn.entry.opcode in ("LDD", "LDDR", "LDI", "LDIR", "LDDR"):
        return get_registers(insn.entry.instructions[1]) + [Reg(False, WORD, 0xE4)] # BC
    return []
        
def get_store_register(insn: Instruction) -> list[WReg]:
    if insn.entry.opcode in ("ADC", "ADD", "AND", "BS1B", "BS1F", "CHG", "CPL", "DAA", "DIV", "DIVS", "DJNZ", "EXTS", "EXTZ", "LD", "LDA", "LDC", "MIRR", "MUL", "MULA", "MULS", "NEG", "OR", "PAA", "SBC", "SUB", "XOR"): # first argument
        return get_registers(insn.entry.instructions[0])
    elif insn.entry.opcode in ("DEC", "INC", "MDEC1", "MDEC2", "MDEC4", "MINC1", "MINC2", "MINC4", "RES", "RL", "RLC", "RR", "RRC", "SCC", "SET", "SLA", "SLL", "SRA", "SRL", "STCF", "TSET", "XORCF"): # second arument
        return get_registers(insn.entry.instructions[1])
    elif insn.entry.opcode in ("EX", "RLD", "RRD"):  #first and second argument
        return get_registers(insn.entry.instructions[0]) + get_registers(insn.entry.instructions[1])
    elif insn.entry.opcode == "SWI":
        return [Reg(False, LWORD, 0xFC)] # XSP
    elif insn.entry.opcode in ("UNLK", "LINK"):
        return get_registers(insn.entry.instructions[0]) + [Reg(False, LWORD, 0xFC)] # XSP
    elif insn.entry.opcode in ("LDD", "LDDR", "LDI", "LDIR", "LDDR"):
        return get_registers(insn.entry.instructions[0]) + [Reg(False, WORD, 0xE4)] # BC    
    elif insn.entry.opcode in ("CPD", "CPDR", "CPI", "CPIR"):
        return [Reg(False, WORD, 0xE4)] # BC
    return []

@dataclass
class FunctionState:
    clobbers: set[(int, WReg)] = field(default_factory=set)
    input: set[WReg] = field(default_factory=set)
    output: set[WReg] = field(default_factory=set)
    stack: list[(int, WReg | Loc | int)] = field(default_factory=list)
    pc: int = 0

    @property
    def used(self) -> list[WReg]:
        return self.clobbers + self.input + self.output

    def __str__(self):
        clobbers = ", ".join(map(lambda c: f"{c[0]}: {c[1]}", self.clobbers))
        input = ", ".join(map(str, self.input))
        output = ", ".join(map(str, self.output))
        stack = ", ".join(map(str, self.stack))
        return f"{clobbers=}\n{input=}\n{output=}\n{stack=}"
    
    def is_clobbered(self, pc: int, reg: WReg) -> bool:
        for c, r in self.clobbers:
            if c < pc and r == reg: return True
        return False
    
    def unclobber(self, reg: WReg):
        self.clobbers = set(filter(lambda ir: ir[1] == reg, self.clobbers))

    def add_input(self, reg: WReg):
        self.input.add(reg)

    def add_clobber(self, pc: int, reg: WReg):
        if any(map(lambda ir: ir[1] == reg, self.clobbers)): return
        self.clobbers.add((pc, reg))
    
    
class Underflow(Exception): pass

class Function:
    def __init__(self, ep: int, name: str, start: CodeBlock):
        self.ep = ep
        self.name = name
        self.start = start
        self.state = FunctionState()

    def _graph(self, block: CodeBlock, visited: set[CodeBlock], dig: Digraph, ob: OutputBuffer):
        if block in visited: return
        visited.add(block)
        text = "".join(map(lambda insn: insnentry_to_str(insn.entry, ob) + "\\l", block.insn))
        dig.node(str(block.ep), text)
        for succ, branch in block.succ:
            dig.edge(str(block.ep), str(succ.ep), color="red" if branch else "black")
            self._graph(succ, visited, dig, ob)

    def graph(self, out_folder: str, ob: OutputBuffer):
        visited: set[CodeBlock] = set()
        dig = Digraph(self.name)
        dig.attr("node", shape="box", fontname="Roboto Mono")
        self._graph(self.start, visited, dig, ob)
        dig.render(directory=out_folder, format="svg")

    def analyze(self):
        states: dict[CodeBlock, FunctionState] = {}
        queue: list[CodeBlock] = [self.start]
        done: set[CodeBlock] = set()

        res: list[FunctionState] = list()

        def merge(a: FunctionState, b: FunctionState) -> FunctionState:
            if a is None: return b
            elif b is None: return a

            state = FunctionState(
                clobbers = a.clobbers.copy(),
                input = a.input | b.input,
                stack = a.stack if len(a.stack) >= len(b.stack) else b.stack,
                pc = max(a.pc, b.pc)
            )
            for pc, cl in b.clobbers: state.add_clobber(pc, cl)
            return state

        while len(queue) > 0:
            block = next(filter(lambda pre: all(map(lambda p: p in done, pre.pred)), reversed(queue)), None)
            if block is not None:
                # This means we have an item that has been reached by all predecessors
                queue.remove(block)
            else: 
                # In case of a cycle, we have to start somewhere
                block = queue.pop()

            if block in done: continue
            done.add(block)

            # Merge results of all predecessors
            state: FunctionState = reduce(merge, map(lambda p: states[p], block.pred), FunctionState())
            states[block] = state

            pc = state.pc
            # Update state
            for insn in block.insn:
                if insn.entry.opcode in ("RET", "RETD", "RETI"):
                    res.append(state)
                elif insn.entry.opcode == "PUSH":
                    state.stack.append((pc, insn.entry.instructions[0]))
                elif insn.entry.opcode == "POP":
                    if len(state.stack) > 0:
                        pc, last = state.stack.pop()
                        if last == insn.entry.instructions[0] and not state.is_clobbered(pc, last):
                            state.unclobber(last)

                    else: raise Underflow()
                else:
                    load = get_load_register(insn)
                    for r in load:
                        if not state.is_clobbered(pc, r):
                            print("input", pc, r)
                            state.add_input(r)

                    store = get_store_register(insn)
                    for r in store:
                        print("clobber", pc, r)
                        state.add_clobber(pc, r)
                pc += 1

            state.pc = pc
            for succ in block.succ:
                queue.append(succ[0])

        self.state = reduce(merge, res, FunctionState())
        print(self.state)

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
        self.functions: dict[int, Function] = {}

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
        self.functions.clear()
        # Find all functions
        for ep in self.ob.calls:
            fun = self.extract_function(ep)
            self.functions[ep] = fun

    def extract_function(self, ep: int):
        section: Section = self.sections.get(ep)
        if not section: return None
        name = str(section.labels[0])

        blocks: dict[int, CodeBlock] = {}    
        def next_block(ep: int, pred: CodeBlock = None, branch = False) -> CodeBlock:
            insn = []
            entry = self.sections.get_floor_entry(ep)
            if not entry: return None
            next_section: Section = entry.get_value()
            instructions = list(filter(lambda i: i.entry.pc >= ep, next_section.instructions))
            if len(instructions) == 0: return None
            ep2 = instructions[0].entry.pc
            if ep2 in blocks:
                block = blocks[ep2]
                block.pred.append(pred)
                pred.succ.append((block, branch))
                return None

            while True:
                new_insn = list(takewhile(lambda i: not is_jump_insn(i), instructions))
                insn.extend(new_insn)
                if len(new_insn) == len(instructions):
                    last_insn = new_insn[-1]
                    if last_insn.entry.opcode == "RET" and len(last_insn.entry.instructions) == 0 or last_insn.entry.opcode in ("RETI", "RETD"):
                        pc = insn[0].entry.pc
                        block = CodeBlock(insn)
                        blocks[pc] = block
                        if pred: 
                            block.pred.append(pred)
                            pred.succ.append((block, branch))

                        return block
                    next_section = self.sections.get_higher_entry(last_insn.entry.pc).get_value()
                    if next_section is None: return None
                    if len(next_section.labels) > 0:
                        pc = insn[0].entry.pc
                        block = CodeBlock(insn)
                        blocks[pc] = block
                        if pred: 
                            block.pred.append(pred)
                            pred.succ.append((block, False))

                        next_block(next_section.offset, block, False)
                        return block
                    
                    instructions = next_section.instructions
                else:
                    last_insn = instructions[len(new_insn)]
                    insn.append(last_insn)

                    pc = insn[0].entry.pc
                    block = CodeBlock(insn)
                    blocks[pc] = block
                    if pred: 
                        block.pred.append(pred)
                        pred.succ.append((block, branch))

                    loc = get_jump_location(last_insn)
                    if loc:
                        ep = int(loc)
                        if ep in blocks:
                            target = blocks[ep]
                            target.pred.append(block)
                            block.succ.append((target, True))
                        else:
                            next_block(ep, block, True)

                    if not (last_insn.entry.opcode == "JP" and len(last_insn.entry.instructions) == 1):
                        next_block(last_insn.entry.pc + 1, block)
                    return block

        start = next_block(ep)
        fun = Function(ep, name, start)
        if ep == 0xF39A32:
            fun.graph("out", self.ob)
            fun.analyze()
        return fun

def load_project(path: str, ep: int, org: int) -> Project:
    proj = Project(path)
    proj.rescan(ep, org)
    return proj