from hashlib import md5
import os, json
from threading import Thread
from typing import Callable, cast
from pytreemap import TreeMap
from abc import ABC
from functools import reduce
from itertools import takewhile
from graphviz import Digraph
from pathlib import Path

from tcls_900 import tlcs_900 as proc
from disapi import InputBuffer, OutputBuffer, InsnPool, Insn, InsnEntry, Label, LabelKind, Loc, insnentry_to_str
from tcls_900.tlcs_900 import Reg, Mem, MemReg, CReg, RReg, LWORD, WORD, BYTE # TODO Specific import
from .popup import InvalidInsnPopup

DATA_PER_ROW = 7
MAX_SECTION_LENGTH = DATA_PER_ROW * 40
FUN_SECTION_LENGTH = 0x8000

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
    def __init__(self, 
        proj: "Project",
        insn: list[Instruction] | None = None, 
        pred: list[int] | None = None,
        succ: list[tuple[int, bool]] | None = None, 
        ep: int | None = None, ln: int | None = None
    ):
        self.proj = proj
        self._insn = insn
        if insn:
            self.ep = insn[0].entry.pc
            last_insn = insn[-1].entry
            self.len = last_insn.pc + last_insn.length - self.ep
        else:
            assert ep and ln
            self.ep = ep
            self.len = ln

        self.pred = pred or []
        self.succ = succ or []

    @property
    def insn(self):
        if self._insn:
            return self._insn
        self._insn = self.proj.insn(self.ep, self.len)
        return self._insn

    def serialize(self) -> dict:
        res = {}
        res["ep"] = self.ep
        res["pred"] = [b for b in self.pred]
        res["succ"] = [{"ep": s[0], "cond": s[1]} for s in self.succ]
        res["len"] = self.len
        return res
    
    @staticmethod
    def deserialize(data: dict, proj: "Project") -> "CodeBlock":
        ep: int = data["ep"]
        ln: int = data["len"]
        succ = [(s["ep"], s["cond"]) for s in data["succ"]]
        return CodeBlock(proj, None, data["pred"], succ, ep=ep, ln=ln)
    
    def to_section(self) -> CodeSection:
        label = self.proj.ob.label(self.ep)
        data = self.proj.ib.buffer[self.ep - self.proj.org:self.ep + self.len + 1 - self.proj.org]
        return CodeSection(
            offset=self.ep,
            length=self.len,
            labels=[label] if label else [],
            data=data,
            instructions=self.insn
        )


def is_jump_insn(insn: Instruction):
    return insn.entry.opcode in ("JR", "JRL", "JP", "DJNZ")

def get_jump_location(insn: Instruction) -> Loc | None:
    entry = insn.entry
    if entry.opcode == "JP":
        if len(entry.instructions) == 1: 
            return entry.instructions[0]
        else:
            loc = entry.instructions[1]
            if isinstance(loc, Loc): return loc

    elif entry.opcode in ("JR", "JRL", "DJNZ"):
        return entry.instructions[1] 

    return None

def is_unconditional_jump(insn: Instruction) -> int:
    if insn.entry.opcode in ("JR", "JRL"):
        v = insn.entry.instructions[0]
        return 1 if v == "T" else -1 if v == "F" else 0
    elif insn.entry.opcode == "JP":
        if len(insn.entry.instructions) == 2:
            v = insn.entry.instructions[0]
            return 1 if v == "T" else -1 if v == "F" else 0
        else: return 1
    return 0

def get_loc(value: Reg | Mem) -> list[Reg | int]:
    if isinstance(value, Reg): return [value.normalize()]
    elif isinstance(value, MemReg):
        if value.reg2: return [value.reg1.normalize(), value.reg2.normalize()]
        else: return [value.reg1.normalize()]
    elif isinstance(value, Mem):
        return [value.address]
    return []

def get_load(insn: Instruction) -> list[Reg | int]:
    opcode: str = insn.entry.opcode
    if opcode.endswith("W"): opcode = opcode[:-1]
    if opcode in ("BS1B", "BS1F", "DJNZ", "DEC", "INC", "LD", "LDC", "LDCF", "MDEC1", "MDEC2", "MDEC4", "MINC1", "MINC2", "MINC4", "ORCF", "RL", "RLC", "RR", "RRC", "SET", "TSET", "XORCF"): #second argument
        if len(insn.entry.instructions) == 2:
            return get_loc(insn.entry.instructions[1])
        else: return get_loc(insn.entry.instructions[0])
    elif opcode in ("CPL", "DAA", "EXTS", "EXTZ", "MIRR", "NEG", "PAA"): # first argument
        return get_loc(insn.entry.instructions[0])
    elif opcode in ("ADC", "ADD", "AND", "ANDCF", "BIT", "CP", "DIV", "DIVS", "EX", "MUL", "MULS", "OR", "RLD", "RRD", "SBC", "SLA", "SLL", "SRA", "SRL", "SUB", "XOR"): #first and second argument
        if len(insn.entry.instructions) == 2:
            l = get_loc(insn.entry.instructions[0]) + get_loc(insn.entry.instructions[1])
            if opcode == "XOR" and len(l) == 2 and l[0] == l[1]: return [] # XOR X, X doesn't depend on the value of X, it just sets everything to 0
            return l
        else: return get_loc(insn.entry.instructions[0]) 
    elif opcode in ("CPD", "CPDR", "CPI", "CPIR"):
        return get_loc(insn.entry.instructions[0]) + get_loc(insn.entry.instructions[1]) + [Reg(True, WORD, 0xE4)] # BC
    elif opcode == "MULA":
        return get_loc(insn.entry.instructions[0]) + [Reg(True, LWORD, 0xEC), Reg(True, LWORD, 0xE8)] # XHL, XDE
    elif opcode == "SWI":
        return [Reg(True, LWORD, 0xFC)] # XSP
    elif opcode in ("UNLK", "LINK"):
        return get_loc(insn.entry.instructions[0]) + [Reg(True, LWORD, 0xFC)] # XSP
    elif opcode in ("LDD", "LDDR", "LDI", "LDIR", "LDDR"):
        return get_loc(insn.entry.instructions[1]) + [Reg(True, WORD, 0xE4)] # BC
    return []
        
def get_store(insn: Instruction) -> list[Reg | int]:
    opcode: str = insn.entry.opcode
    if opcode.endswith("W"): opcode = opcode[:-1]
    if opcode in ("ADC", "ADD", "AND", "BS1B", "BS1F", "CHG", "CPL", "DAA", "DIV", "DIVS", "DJNZ", "EXTS", "EXTZ", "LD", "LDA", "LDC", "MIRR", "MUL", "MULA", "MULS", "NEG", "OR", "PAA", "SBC", "SUB", "XOR"): # first argument
        return get_loc(insn.entry.instructions[0])
    elif opcode in ("DEC", "INC", "MDEC1", "MDEC2", "MDEC4", "MINC1", "MINC2", "MINC4", "RES", "RL", "RLC", "RR", "RRC", "SCC", "SET", "SLA", "SLL", "SRA", "SRL", "STCF", "TSET", "XORCF"): # second arument
        if len(insn.entry.instructions) == 2:
            return get_loc(insn.entry.instructions[1])
        else: return get_loc(insn.entry.instructions[0])
    elif opcode in ("EX", "RLD", "RRD"):  #first and second argument
        return get_loc(insn.entry.instructions[0]) + get_loc(insn.entry.instructions[1])
    elif opcode == "SWI":
        return [Reg(True, LWORD, 0xFC)] # XSP
    elif opcode in ("UNLK", "LINK"):
        return get_loc(insn.entry.instructions[0]) + [Reg(True, LWORD, 0xFC)] # XSP
    elif opcode in ("LDD", "LDDR", "LDI", "LDIR", "LDDR"):
        return get_loc(insn.entry.instructions[0]) + [Reg(True, WORD, 0xE4)] # BC    
    elif opcode in ("CPD", "CPDR", "CPI", "CPIR"):
        return [Reg(True, WORD, 0xE4)] # BC
    return []

def overlaps(r1: Reg | int, r2: Reg | int):
    if isinstance(r1, Reg) and isinstance(r2, Reg):
        if r1.size == r2.size: return r1.addr == r2.addr
        if r1.size > r2.size:
            r1, r2 = r2, r1
        if r1.size == BYTE:
            if r2.size == WORD: 
                return r2.addr <= r1.addr <= r2.addr + 1
            elif r2.size == LWORD:
                return r2.addr <= r1.addr <= r2.addr + 3
        elif r1.size == WORD and r2.size == LWORD:
            return r2.addr <= r1.addr <= r2.addr + 3

        assert False, "Invalid register sizes"
    elif isinstance(r1, int) and isinstance(r2, int):
        return r1 == r2
    else: return False

def overlaps_and_covers(r1: Reg | int, r2: Reg | int):
    if isinstance(r1, Reg) and isinstance(r2, Reg):
        return overlaps(r1, r2) and r1.size <= r2.size
    return overlaps(r1, r2)

def serialize_reg_mem(value: Reg | int) -> dict:
    res = {}
    if isinstance(value, int):
        res["type"] = "Mem"
        res["address"] = value
    elif isinstance(value, Reg):
        res["type"] = "Reg"
        res["size"] = value._size
        res["reg"] = value.reg

    assert not isinstance(value, (CReg, RReg))

    return res

def deserialize_reg_mem(data: dict) -> Reg | int:
    tpe = data["type"]
    if tpe == "Mem":
        return data["address"]
    elif tpe == "Reg":
        return Reg(True, data["size"], data["reg"])
    
    raise ValueError("Invalid register or memory location")

class FunctionState:
    def __init__(
            self, proj: "Project",
            clobbers: set[tuple[int, Reg | int]] | None = None, 
            input: set[Reg | int] | None = None, 
            output: set[Reg | int] | None = None, 
            stack: list[tuple[int, Reg | int]] | None = None, 
            fun_stack: list[tuple[int, set[Reg | int], set[Reg | int]]] | None = None,
            pc: int = 0
        ):
        
        self.clobbers = clobbers or set()
        self.input = input or set()
        self.output = output or set()
        self.stack = stack or list()
        self.fun_stack = fun_stack or list()
        self.pc = pc
        self.proj = proj

    def serialize(self) -> dict:
        res = {}
        res["clobbers"] = [{"ep": c[0], "value": serialize_reg_mem(c[1]) } for c in self.clobbers]
        res["input"] = [serialize_reg_mem(i) for i in self.input]
        res["output"] = [serialize_reg_mem(o) for o in self.output]
        fun_stack = []
        for fun, in_in, in_out in self.fun_stack:
            c_in_in = [serialize_reg_mem(i) for i in in_in]
            c_in_out = [serialize_reg_mem(i) for i in in_out]
            fun_stack.append({"function": fun, "in": c_in_in, "out": c_in_out})

        res["stack"] = [{"ep": s[0], "value": serialize_reg_mem(s[1])} for s in self.stack]
        res["fun_stack"] = fun_stack
        res["pc"] = self.pc

        return res
    
    @staticmethod
    def deserialize(data: dict, proj: "Project") -> "FunctionState":
        state = FunctionState(proj)
        for c in data["clobbers"]:
            state.clobbers.add((c["ep"], deserialize_reg_mem(c["value"])))
        for i in data["input"]:
            state.input.add(deserialize_reg_mem(i))
        for o in data["output"]:
            state.output.add(deserialize_reg_mem(o))
        for stack in data["stack"]:
            state.stack.append((stack["ep"], deserialize_reg_mem(stack["value"])))
        for stack in data["fun_stack"]:
            c_in_in = set(deserialize_reg_mem(r) for r in stack["in"])
            c_in_out = set(deserialize_reg_mem(r) for r in stack["out"])
            fun = int(stack["function"])
            state.fun_stack.append((fun, c_in_in, c_in_out))
        state.pc = data["pc"]

        return state

    def __str__(self):
        clobbers = ", ".join(map(lambda c: f"{c[0]}: {c[1]}", self.clobbers))
        input = ", ".join(map(str, self.input))
        output = ", ".join(map(str, self.output))
        stack = ", ".join(map(str, self.stack))
        return f"{{\n\t{clobbers=}\n\t{input=}\n\t{output=}\n\t{stack=}\n}}"
    
    def is_clobbered(self, pc: int, reg: Reg | int) -> bool:
        for c, r in self.clobbers:
            if c < pc and overlaps(r, reg): return True
        return False
    
    def unclobber(self, reg: Reg | int):
        self.clobbers = set(filter(lambda ir: not overlaps_and_covers(ir[1], reg), self.clobbers))

    def add_input(self, pc: int, reg: Reg | int):
        for fun, in_in, in_out in reversed(self.fun_stack):
            for i in in_in: 
                if overlaps(reg, i): in_out.add(i)

        if self.is_clobbered(pc, reg): return
        if any(map(lambda r2: overlaps_and_covers(reg, r2), self.input)): return
        self.input = set(filter(lambda r2: not overlaps_and_covers(r2, reg), self.input))
        self.input.add(reg)

    def add_clobber(self, pc: int, reg: Reg | int):
        for fun, in_in, in_out in reversed(self.fun_stack):
            for r in in_in.copy():
                if overlaps(r, reg): in_in.remove(r)
        self.fun_stack = list(filter(lambda s: len(s[1]) > 0, self.fun_stack))

        if any(map(lambda ir: overlaps_and_covers(reg, ir[1]), self.clobbers)): return
        self.clobbers = set(filter(lambda c: not overlaps_and_covers(c[1], reg), self.clobbers))
        self.clobbers.add((pc, reg))

    def push_function(self, pc: int, fun: "Function"):
        assert fun.state is not None
        input = set(map(lambda c: c[1], fun.state.clobbers))
        for c in fun.state.input:
            self.add_input(pc, c)
        for c in input:
            self.add_clobber(pc, c)
        self.fun_stack.append((fun.ep, input, set()))

    def clear_functions(self):
        for fun, in_in, in_out in self.fun_stack:
            assert self.proj.functions is not None
            fun = self.proj.functions[fun]
            assert fun.state is not None
            fun.state.output.update(in_out)
        self.fun_stack.clear()

    @staticmethod
    def merge(a: "FunctionState | None", b: "FunctionState | None",) -> "FunctionState":
        if a is None:
            assert b is not None
            b.clear_functions()
            return b.copy()
        elif b is None:
            a.clear_functions()
            return a.copy()
        
        a.clear_functions()
        b.clear_functions()

        state = FunctionState(
            a.proj,
            clobbers = a.clobbers.copy(),
            input = a.input.copy(),
            stack = a.stack if len(a.stack) >= len(b.stack) else b.stack,
            pc = max(a.pc, b.pc)
        )
        for pc, cl in b.clobbers: state.add_clobber(pc, cl)
        for i in b.input: state.add_input(a.pc, i)
        return state
    
    def copy(self) -> "FunctionState":
        fun_stack = list()
        for fun, in_in, in_out in self.fun_stack:
            fun_stack.append((fun, in_in.copy(), in_out.copy()))

        return FunctionState(
            self.proj,
            self.clobbers.copy(), 
            self.input.copy(), 
            self.output.copy(), 
            self.stack.copy(), 
            fun_stack, 
            self.pc
        )


class Underflow(Exception): pass

from ui.main import app 

class Function:
    def __init__(self, ep: int, start: CodeBlock, blocks: dict[int, CodeBlock]):
        self.ep = ep
        self.start = start
        self.blocks = blocks
        self.state: FunctionState | None = None
        self.underflow = False
        self.callers: list[tuple[int, int]]
        self.callees: list[tuple[int, int]]

    def __str__(self) -> str:
        return self.name

    @property
    def name(self) -> str:
        return str(app().project.ob.label(self.ep))
    
    @name.setter
    def name(self, name: str):
        app().project.rename_label(self.ep, name)

    def serialize(self) -> dict:
        res = {}
        if self.state:
            res["state"] = self.state.serialize()

        res["start"] = self.start.ep
        blocks = []
        for block in self.blocks.values():
            blocks.append(block.serialize())
        
        res["blocks"] = blocks
        res["underflow"] = self.underflow
        res["callers"] = [{"loc": c[0], "fun": c[1] } for c in self.callers]
        res["callees"] = [{"loc": c[0], "fun": c[1] } for c in self.callees]

        return res
    
    @staticmethod
    def deserialize(data: dict, proj: "Project") -> "Function":
        state: FunctionState | None = None
        if "state" in data:
            state = FunctionState.deserialize(data["state"], proj)
        
        blocks: dict[int, CodeBlock] = {}
        for block_data in data["blocks"]:
            block = CodeBlock.deserialize(block_data, proj)
            blocks[block.ep] = block

        ep: int = data["start"]
        start = blocks[ep]
        fun = Function(ep, start, blocks)
        fun.underflow = data["underflow"]

        fun.callers = [(c["loc"], c["fun"]) for c in data["callers"]]
        fun.callees = [(c["loc"], c["fun"]) for c in data["callees"]]
        fun.state = state

        return fun
    
    def _graph(self, block: CodeBlock, visited: set[CodeBlock], dig: Digraph, ob: OutputBuffer):
        if block in visited: return
        visited.add(block)
        text = "".join(map(lambda insn: insnentry_to_str(insn.entry, ob) + "\\l", block.insn))
        dig.node(str(block.ep), text)
        for succ, branch in block.succ:
            dig.edge(str(block.ep), str(succ), color="red" if branch else "black")
            self._graph(self .blocks[succ], visited, dig, ob)

    def graph(self, ob: OutputBuffer) -> Digraph:
        visited: set[CodeBlock] = set()
        dig = Digraph(self.name)
        dig.attr("node", shape="box", fontname="Roboto Mono")
        self._graph(self.start, visited, dig, ob)
        return dig
    
    def graph_svg(self, out_folder: str, ob: OutputBuffer) -> str:
        dig = self.graph(ob)
        return dig.render(directory=out_folder, format="svg")

    def graph_json(self, out_folder: str, ob: OutputBuffer) -> str:
        dig = self.graph(ob)
        return dig.render(directory=out_folder, format="json0")

    def analyze(self, proj: "Project", tick: Callable[[str], None] | None = None):
        assert proj.functions is not None
        if self.state: return
        self.state = FunctionState(proj)
        self.underflow = False
        self.callers = []
        self.callees = []

        states: dict[CodeBlock, FunctionState] = {}
        queue: list[CodeBlock] = [self.start]
        done: set[CodeBlock] = set()

        res: list[FunctionState] = list()

        try: 
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
                if len(block.pred) == 1:
                    state = states.get(self.blocks[block.pred[0]], FunctionState(proj)).copy()
                else: state = reduce(FunctionState.merge, map(lambda p: states.get(self.blocks[p]), block.pred), FunctionState(proj))
                states[block] = state

                pc = state.pc
                # Update state
                for insn in block.insn:
                    if insn.entry.opcode in ("RET", "RETD", "RETI"):
                        res.append(state)
                    elif insn.entry.opcode == "PUSH":
                        reg_or_mem = insn.entry.instructions[0]
                        if isinstance(reg_or_mem, Mem):
                            state.stack.append((pc, reg_or_mem.address))
                        elif isinstance(reg_or_mem, Reg):
                            state.stack.append((pc, reg_or_mem.normalize()))
                        elif reg_or_mem == "SR":
                            state.stack.append((pc, -1)) # SR special flag
                        elif reg_or_mem == "F":
                            state.stack.append((pc, -2)) # F special flag
                    elif insn.entry.opcode == "POP":
                        if len(state.stack) > 0:
                            pc2, last = state.stack.pop()
                            reg_or_mem = insn.entry.instructions[0]
                            if reg_or_mem == "SR": reg_or_mem = -1
                            elif reg_or_mem == "F": reg_or_mem = -2
                            #print("unclobber", last, pc, state.is_clobbered(pc, last))
                            if last == reg_or_mem and not state.is_clobbered(pc2, last):
                                state.unclobber(last)
                        else: raise Underflow()
                    elif insn.entry.opcode in ("CALL", "CALR"):
                        fun = None
                        if len(insn.entry.instructions) == 1:
                            fun = proj.functions.get(int(insn.entry.instructions[0]))
                        else:
                            loc = insn.entry.instructions[1]
                            if isinstance(loc, Loc): fun = proj.functions.get(int(loc))

                        if fun:
                            if not fun.state: fun.analyze(proj, tick)
                            fun.callers.append((insn.entry.pc, self.ep))
                            self.callees.append((insn.entry.pc, fun.ep))
                            state.push_function(pc, fun)

                    else:
                        load = get_load(insn)
                        for r in load:
                            #print(self.ep, "input", pc, r)
                            state.add_input(pc, r)

                        store = get_store(insn)
                        for r in store:
                            #print(self.ep, "clobber", pc, r)
                            state.add_clobber(pc, r)
                    pc += 1

                state.pc = pc
                for succ in block.succ:
                    queue.append(self.blocks[succ[0]])

            self.state = reduce(FunctionState.merge, res, FunctionState(proj))
        except Underflow:
            self.underflow = True
        
        if tick: tick(self.name)

def label_list(label):
    if label is None: return []
    return [label]

class ProjectLoadException(Exception): pass

class Project:
    def __init__(self, project_folder: Path, path: Path, org: int, ep: int | list[int]):
        self.project_folder = project_folder
        self.path = path
        self.filename = os.path.basename(path)
        self.sections = TreeMap()
        self.org = org
        self.ep = ep
        self.ib: InputBuffer
        self.ob: OutputBuffer
        self.pool: InsnPool
        self.file_len = 0
        self.functions: dict[int, Function] | None = None

    def rename_label(self, ep: int, name: str):
        label = self.ob.label(ep)
        if label:
            label.name = name
            app().main_dock.refresh(ep = ep)

    def get_project_id(self) -> str:
        return md5(str(self.path).encode()).hexdigest()

    def write_to_file(self, project_folder: Path):
        project_folder.mkdir(exist_ok=True)

        labels = {}
        for ep, l in self.ob.labels.items():
            label = {}
            label["name"] = l.name
            label["count"] = l.count
            label["kind"] = l.kind.value
            labels[ep] = label

        with open(project_folder / "labels.json", "w") as fp:
            json.dump(labels, fp, indent=2, sort_keys=True)

        proj = {
            "rom": self.path.relative_to(project_folder).as_posix(),
            "ep": self.ep,
            "org": self.org
        }
        with open(project_folder / "proj.json", "w") as fp:
            json.dump(proj, fp, indent=2, sort_keys=True)

        fun_folder = project_folder / "fun"
        fun_folder.mkdir(exist_ok=True)
        
        if self.functions:
            for fun in self.functions.values():
                section = (fun.ep - self.org) // FUN_SECTION_LENGTH
                section_name = format(section * FUN_SECTION_LENGTH + self.org, "X")
                section_folder = fun_folder / section_name
                section_folder.mkdir(exist_ok=True)
                with open(section_folder / (str(fun.ep) + ".json"), "w") as fp:
                    json.dump(fun.serialize(), fp, indent=2, sort_keys=True)

    @staticmethod
    def read_from_file(project_folder: Path) -> "Project":
        if not project_folder.is_dir(): 
            raise ProjectLoadException("Not a directory")
        if not project_folder.name.endswith(".disproj"): 
            raise ProjectLoadException("Invalid name")
        
        proj_file = project_folder / "proj.json"
        if not proj_file.exists() or not proj_file.is_file():
            raise ProjectLoadException("No proj.json file")
        
        with open(proj_file, "r") as fp:
            proj_json = json.load(fp)

        path = project_folder / proj_json["rom"]
        file_len = os.path.getsize(path)

        project = Project(project_folder, path, proj_json["org"], proj_json["ep"])
        project.file_len = file_len

        with open(path, "rb") as fp:
            project.ib = InputBuffer(fp, file_len, entry_point=project.org, exit_on_invalid=True)
            project.ob = OutputBuffer(None)

        project.pool = InsnPool(proc)

        labels = {}
        labels_file = project_folder / "labels.json"
        if labels_file.exists() and labels_file.is_file():
            with open(labels_file, "r") as fp:
                labels = json.load(fp)
        
        label_eps: list[int] = []
        for ep, label in labels.items():
            ep = int(ep)
            count = label["count"]
            name = label["name"]
            kind = LabelKind(label["kind"])
            if kind != LabelKind.DATA: label_eps.append(ep)
            if kind == LabelKind.FUNCTION: project.ob.calls.add(ep)
            project.ob.labels[ep] = Label(ep, count, name, kind)

        for ep in label_eps:
            project.pool.query(Insn(project.pool, project.ib, project.ob, ep, do_branch=False))
        project.pool.poll_all(threaded=False)
        project._load_sections()

        # Load functions
        fun_folder = project_folder / "fun"
        if fun_folder.exists() and fun_folder.is_dir():
            project.functions = {}

            for fun_file in fun_folder.rglob("*"):
                if fun_file.is_dir(): continue
                with open(fun_file, "r") as fp:
                    fun_data = json.load(fp)
                fun = Function.deserialize(fun_data, project)
                project.functions[fun.ep] = fun


        return project


    def is_function(self, ep: int) -> bool:
        return ep in self.ob.calls

    def disassemble(self, ep: int, callback):
        clear_cache()
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
    
    def _load_sections(self):
        ib = self.ib
        ob = self.ob
        org = self.org

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

    def rescan(self, ep: int | list[int], org: int):
        self.ep = ep
        self.org = org
        
        clear_cache()
        self.sections.clear()
        self.file_len = os.path.getsize(self.path)

        with open(self.path, 'rb') as f:
            ib = InputBuffer(f, self.file_len, entry_point=org, exit_on_invalid=True)
            ob = OutputBuffer(None)
            self.ob = ob
            self.ib = ib
 
        self.pool = InsnPool(proc)

        if isinstance(ep, int):
            ep = [ep]
        
        for entry in ep:
            insn = Insn(self.pool, ib, ob, entry)
            self.pool.query(insn)
        
        self.pool.poll_all()

        ob.compute_labels(org, self.file_len + org)

        self._load_sections()

    def analyze_functions(self, callback: Callable[[], None], progress: Callable[[int, str], None]) -> int:
        def analyze():
            self.functions = {}
            # Find all functions
            for i, ep in enumerate(self.ob.calls):
                fun = self.extract_function(ep)
                assert fun is not None
                self.functions[ep] = fun
            
            t = 0
            def tick(name: str):
                nonlocal t
                progress(t, name)
                t += 1

            for fun in self.functions.values():
                fun.analyze(self, tick)

            callback()
            #for fun in self.functions.values():
            #    print(fun.name, ":", str(fun.state))
            #    print("callers: ", list(map(lambda c: f"{c[0]}: {c[1].name}", fun.callers)))
            #    print("callees: ", list(map(lambda c: f"{c[0]}: {c[1].name}", fun.callees)))

        Thread(target=analyze, daemon=True).start()
        return len(self.ob.calls)
    
    def insn(self, start: int, ln: int) -> list[Instruction]:
        entry = self.sections.floor_entry(start)
        res = []

        assert entry is not None
        section: Section = cast(Section, entry.get_value())
        s = start - section.offset
        end = min(section.length - s, ln)
        res.extend([i for i in section.instructions if section.offset + s <= i.entry.pc < start + end])
        read = end
        if read < ln:
            entry = self.sections.floor_entry(section.offset + section.length + 1)
            if entry is None: return res
            section = cast(Section, entry.get_value())

            while section.offset + section.length < start + ln:
                res.extend(section.instructions[:])
                read += section.length
                entry = self.sections.floor_entry(section.offset + section.length + 1)
                if entry is None: return res
                section = cast(Section, entry.get_value())
            rest = ln - read
            if rest > 0:
                res.extend([i for i in section.instructions if i.entry.pc < start + ln])

        last_offset = res[-1].entry.pc + res[-1].entry.length
        first_offset = res[0].entry.pc
        assert last_offset - first_offset == ln
        return res

    def extract_function(self, ep: int):
        section = self.sections.get(ep)
        if not section: return None

        blocks: dict[int, CodeBlock] = {}    
        def next_block(ep: int, pred: CodeBlock | None = None, branch = False) -> CodeBlock | None:
            insn: list[Instruction] = []
            entry = self.sections.get_floor_entry(ep)
            if not entry: return None
            next_section: Section = entry.get_value()
            instructions = list(filter(lambda i: i.entry.pc >= ep, next_section.instructions))
            if len(instructions) == 0: return None
            ep2 = instructions[0].entry.pc
            if ep2 in blocks:
                if pred:
                    block = blocks[ep2]
                    block.pred.append(pred.ep)
                    pred.succ.append((block.ep, branch))
                    return None

            while True:
                new_insn = list(takewhile(lambda i: not is_jump_insn(i), instructions))
                insn.extend(new_insn)
                if len(new_insn) == len(instructions):
                    last_insn = new_insn[-1]
                    if last_insn.entry.opcode == "RET" and len(last_insn.entry.instructions) == 0 or last_insn.entry.opcode in ("RETI", "RETD"):
                        pc = insn[0].entry.pc
                        block = CodeBlock(self, insn)
                        blocks[pc] = block
                        if pred: 
                            block.pred.append(pred.ep)
                            pred.succ.append((block.ep, branch))

                        return block
                    next_entry = self.sections.get_higher_entry(last_insn.entry.pc)
                    if next_entry is None: return None
                    next_section = next_entry.get_value()
                    if len(next_section.labels) > 0:
                        pc = insn[0].entry.pc
                        block = CodeBlock(self, insn)
                        blocks[pc] = block
                        if pred: 
                            block.pred.append(pred.ep)
                            pred.succ.append((block.ep, branch))

                        next_block(next_section.offset, block, False)
                        return block
                    
                    instructions = next_section.instructions
                else:
                    last_insn = instructions[len(new_insn)]
                    insn.append(last_insn)

                    pc = insn[0].entry.pc
                    block = CodeBlock(self, insn)
                    blocks[pc] = block
                    if pred: 
                        block.pred.append(pred.ep)
                        pred.succ.append((block.ep, branch))

                    cond = is_unconditional_jump(last_insn)
                    loc = get_jump_location(last_insn)
                    if loc and cond != -1:
                        ep = int(loc)
                        if ep in blocks:
                            target = blocks[ep]
                            target.pred.append(block.ep)
                            block.succ.append((target.ep, True))
                        else:
                            next_block(ep, block, True)

                    if cond != 1:
                        next_block(last_insn.entry.pc + last_insn.entry.length, block)
                    return block

        start = next_block(ep)
        assert start is not None
        fun = Function(ep, start, blocks)
        return fun
    
    def get_data_slice(self, start: int, end: int) -> bytes:
        return self.ib.buffer[start - self.org:end - self.org + 1]

def new_project(path: Path, ep: int | list[int], org: int) -> Project:
    proj = Project(path.parent, path, org, ep)
    proj.rescan(ep, org)
    return proj

from .arrow import clear_cache