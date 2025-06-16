from . import microc

# Constants
BYTE = 0
WORD = 1
LWORD = 2

# Class to hold registers
class Reg:
    def __init__(self, ext, size, reg):
        self.ext = ext
        self._size = size
        self.reg = reg
    
    def __str__(self):
        return regname(self)
    
    @property
    def size(self):
        return self._size
    
    @property
    def addr(self):
        return reg_addr[str(self)]
    
    def normalize(self):
        return Reg(True, self.size, self.addr)
    
    def __hash__(self):
        return hash((self.size, self.addr))
    
    def __eq__(self, value):
        if isinstance(value, Reg):
            return self.size == value.size and self.addr == value.addr
        return False

# Class to hold command registers
class CReg(Reg):
    def __init__(self, size, reg):
        super(CReg, self).__init__(False, size, reg)
    
    def __str__(self):
        return cregname(self)

# Class to hold registers used by MUL, DIV
# Wraps a normal register with a different __str__ method
# TODO Might want to turn this into a method that modifies the address instead
class RReg(Reg):
    def __init__(self, reg):
        super(RReg, self).__init__(reg.ext, reg.size, reg.reg)
    
    def __str__(self):
        return rregname(self)
    
    def normalize(self):
        return Reg(True, self.size, reg_addr[rregname(self)])
    
    @property
    def size(self):
        if self._size == BYTE: return WORD
        if self._size == WORD: return LWORD
        assert False, "Invalid size"

# Class that holds memory addresses
class Mem:
    def __init__(self, insn, address, name = None, plain_addr = False):
        location = microc.check_address(address)
        
        if name is not None: pass
        elif location: name = location.name
        elif insn.ibuffer.min <= address < insn.ibuffer.max:
            name = insn.obuffer.datalabel(address)
        else:
            name = format(address, "X") + "h"

        insn.obuffer.datalabel(address)
        
        self.name = name
        self.address = address
        self.plain_addr = plain_addr
        
    def __str__(self):
        return f"{self.name}" if self.plain_addr else f"({self.name})"
    
    def __hash__(self):
        return self.address
    
    def __eq__(self, value):
        if isinstance(value, Mem):
            return self.address == value.address
        return False

class MemReg(Mem):
    def __init__(self, insn, address, name, reg1, reg2 = None):
        super().__init__(insn, address, name)
        self.reg1 = reg1
        self.reg2 = reg2

def call_opc(insn, x, y, optable):
    opc = optable[x][y]   
    if opc is None:
        #print(hex(insn.pc) + ":", hex(x), hex(y), "UNDEFINED")
        # Pop it off the stack...
        insn.pop()
        if insn.exit_on_invalid:
            insn.kill(error = True)
        return ("UNDEFINED",)
    else:
        #print(hex(insn.pc) + ":", hex(x), hex(y), opc.__name__)
        asm = opc(insn)
        if type(asm) is tuple:
            if insn.exit_on_invalid and asm[0] in ("INVALID", "UNDEFINED"):
                insn.kill(error = True)
            return asm
        elif asm is None:
            raise Exception("Not implemented") 
        else: return (asm,)

def src(insn):
    x, y = peekopc(insn)
    if x >= 0xC:
        insn.lastsize = x - 0xC
    else:
        insn.lastsize = x - 0x8
    insn.lastinsn = insn.peek()
    insn.lastmem = popmem(insn)
    
    x, y = peekopc(insn)
    return call_opc(insn, x, y, optable_src)

def dst(insn):
    insn.lastinsn = insn.peek()
    insn.lastmem = popmem(insn)
    x, y = peekopc(insn)
    return call_opc(insn, x, y, optable_dst)
    
def reg(insn):
    insn.last = insn.peek() # Not really needed but added for consistency
    x, y = peekopc(insn)
    size = x - 0xC
    if y == 0x7:
        # Can have extended registers
        insn.lastr = popr(insn, '?', size)
    else:
        insn.lastr = popR(insn, '?', size)
    insn.lastsize = size
    
    x, y = peekopc(insn)
    return call_opc(insn, x, y, optable_reg)
    
def next_insn(insn):
    x, y = peekopc(insn)
    return call_opc(insn, x, y, optable)
    
def popcc(insn):
    cc = insn.pop()
    return (cc & 0x0F)

def popmem(insn):
    mem = insn.pop()
    if (mem & 0x40) == 0:
        reg = (mem & 0x7)
        name = Rregtable[LWORD][reg]
        r = RReg(Reg(False, WORD, reg))
        if (mem & 0x8) == 0:
            # XWA to XSP
            return MemReg(insn, 0xE0 + reg, name, r)
        else:
            # XWA to XSP + d8
            d = insn.pop()
            if d > 127:
                d -= 256 # signed
                name += "-" + (str(-d) if d < -1 else "")
            else:
                name += "+" + (str(d) if d > 1 else "")
            return MemReg(insn, 0xE0 + reg + d, name, r)
    elif (mem & 0x4) == 0x4:
        
        mem2 = insn.pop()
        c = (mem2 & 0x2)
        c = 1 if c == 0 else c * 2
        reg = (mem2 & 0xFC)
        r = Reg(True, LWORD, reg)
        name = regname(r)

        if (mem & 0x1) == 0:
            return MemReg(insn, reg - c, "-" + name, r) # -r32
        else:
            return MemReg(insn, reg + c, name + "+", r) # r32+
    else:
        n = mem & 0x3
        if n == 0: 
            return Mem(insn, insn.pop()) # 8
        elif n == 1:
            return Mem(insn, insn.popw()) # 16
        elif n == 2:
            return Mem(insn, insn.popw() | (insn.pop() << 16)) # 24
        else:
            mem = insn.pop()
            n = mem & 0x3
            if n == 0:
                reg = (mem & 0xFE)
                r = Reg(True, LWORD, reg)
                name = regname(r)
                return MemReg(insn, mem * 4, name, r) # r32
            elif n == 1:
                reg = (mem & 0xFE)
                r = Reg(True, LWORD, reg)
                name = regname(r)
                d = insn.popw()
                if d > 32767:
                    d -= 65536  # signed
                    name += "-" + (str(-d) if d < -1 else "")
                else:
                    name += "+" + (str(d) if d > 1 else "")
                return MemReg(insn, reg + d, name, r) # r32 + d16
            elif mem == 0x3:
                reg1 = insn.pop()
                reg2 = insn.pop()
                r1 = Reg(True, LWORD, reg1)
                r2 = Reg(True, BYTE, reg2)
                name = "%s+%s" % (regname(r1), regname(r2))
                return MemReg(insn, reg1, name, r1, r2) # r32 + r8
            else:
                reg1 = insn.pop()
                reg2 = insn.pop()
                r1 = Reg(True, LWORD, reg1)
                r2 = Reg(True, WORD, reg2)
                name = "%s+%s" % (regname(r1), regname(r2))
                return MemReg(insn, reg1, name, r1, r2) # r32 + r16
                
rrtable_8 = ["INVALID", "WA", "INVALID", "BC", "INVALID", "DE", "INVALID", "HL"]

def popn_sz(insn, sz):
    if sz == BYTE:
        return insn.pop()
    elif sz == WORD:
        return insn.popw()
    elif sz == LWORD:
        return insn.popl()
    raise ValueError("Invalid size")

def rregname(register):
    ext = register.ext
    size = register._size
    reg = register.reg
    
    if not ext:
        if size == BYTE:
            return rrtable_8[reg]
        elif size == WORD:
            return Rregtable[LWORD][reg]
        else: return "INVALID"
    elif size == BYTE:
        return regname(Reg(True, WORD, reg))      
    else: return "INVALID"
    
bnames = ["A", "W", "C", "B", "E", "D", "L", "H"]
wnames = ["WA", "BC", "DE", "HL"]
lnames = ["XWA", "XBC", "XDE", "XHL"]
extnames = ["X", "Y", "Z", "P"]

# takes the returned register of popr / popR
# returns a register name or the address if its an invalid register
def regname(register):
    ext = register.ext
    size = register._size
    reg = register.reg
    
    if size < 0 or size > 2:
        return "INVALID"
    if not ext:
        return Rregtable[size][reg]
    
    if (size == WORD and reg & 1) != 0: 
        return "INVALID" # Check if divisible by 2
    elif (size == LWORD and reg & 0b11) != 0: 
        return "INVALID" # Check if divisible by 4
    
    rname = ""
    if reg <= 0x7F: # Normal banks
        if size == BYTE:
            rname += "Q" if (reg & 0b0010) != 0 else "R"
            rname += bnames[((reg & 0b1100) >> 1) | (reg & 1)]
        elif size == WORD:    
            rname += "Q" if (reg & 0b0010) != 0 else "R"
            rname += wnames[(reg & 0b1100) >> 2]
        elif size == LWORD:
            rname += lnames[(reg & 0b1100) >> 2]
        rname += str((reg & 0xF0) >> 4)
    elif 0xD0 <= reg <= 0xEF:
        if size == BYTE:
            if (reg & 0b0010) != 0: rname += "Q"
            rname += bnames[((reg & 0b1100) >> 1) | (reg & 1)]
        elif size == WORD:
            if (reg & 0b0010) != 0: rname += "Q"
            rname += wnames[(reg & 0b1100) >> 2]
        elif size == LWORD:
            rname += lnames[(reg & 0b1100) >> 2]
        if reg <= 0xDC:
            rname += "'"
        #elif reg <= 0xE0:
        #    return "INVALID"
    elif 0xF0 <= reg <= 0xFF:
        if size == BYTE:
            if (reg & 0b0010) != 0: rname += "Q"
        elif size == LWORD:
            rname += "X"
        if (reg & 0xFC) == 0xFC:
            rname += "S"
        else: rname += "I"
        rname += extnames[(reg & 0b1100) >> 2]
        if size == BYTE:
            rname += "H" if (reg & 0b0010) != 0 else "L"
    else:
        return "INVALID"
    
    return rname
    
lcrnames = ["S0", "S1", "S2", "S3", "D0", "D1", "D2", "D3"]
wcrnames = ["C0", "C1", "C2", "C3"]
bcrnames = ["M0", "M1", "M2", "M3"]

def cregname(reg):
    if reg.size == LWORD:
        if reg.reg == 0x3C: return "XNSP"
        n = reg.reg // 4
        if n < 0 or n > 7: return "INVALID"
        return "DMA" + lcrnames[n]
    elif reg.size == WORD:
        if reg.reg == 0x3C: return "INTNEST"
        n = (reg.reg - 0x20) // 4
        if n < 0 or n > 3: return "INVALID"
        return "DMA" + wcrnames[n]
    else:
        n = (reg.reg - 0x22) // 4
        if n < 0 or n > 3: return "INVALID"
        return "DMA" + bcrnames[n]
        
operand_size_table = {
    'z' : [0, 1, None],
    'zz' : [0b00, 0b01, 0b10],
    'zzz' : [0b010, 0b011, 0b100],
    's' : [None, 0, 1]
}

# Arguments [insn, type = s/z/zz/zzz/?, [size = -1], [spos = -1]]
def popr(insn, tpe, size = -1, spos = -1):
    b = insn.peek()
    # check if we are using extended addresses, flag is 0x7
    extended = ((b ^ 0x7) & 0x7) == 0
    
    reg = popR(insn, tpe, size, spos)
    assert isinstance(reg, Reg)
    
    if not extended: return reg
    
    return Reg(True, reg.size, insn.pop())

# Arguments [insn, type = s/z/zz/zzz/?, [size = -1], [spos = -1]]
def popR(insn, tpe, size = -1, spos = -1):
    b = insn.pop()
    rcode = (b & 0x7)
    
    if tpe != '?':
        opsizecode = 0
        if tpe == 's' or tpe == 'z':
            if spos < 0: spos = 3
            smask = (0x80 >> spos)
            opsizecode = (b & smask) >> (8 - spos - 1)
        elif tpe == 'zz':
            if spos < 0: spos = 2
            smask = (0xC0 >> spos)
            opsizecode = (b & smask) >> (8 - spos - 2)
        elif tpe == 'zzz':
            if spos < 0: spos = 1
            smask = (0xE0 >> spos)
            opsizecode = (b & smask) >> (8 - spos - 3)
        elif tpe != '?': raise ValueError("Type must be one of s/z/zz/zzz/?")
        
        try:
            size = operand_size_table[tpe].index(opsizecode)
        except ValueError:
            return "INVALID"
        
    return Reg(False, size, rcode)

def peekopc(insn, n = 0):
    opcode = insn.peek(n)
    x = (opcode & 0xF0) >> 4
    y = (opcode & 0x0F)
    return [x, y]

# Global tables

Rregtable = [
    ["W", "A", "B", "C", "D", "E", "H", "L"],
    ["WA", "BC", "DE", "HL", "IX", "IY", "IZ", "SP"],
    ["XWA", "XBC", "XDE", "XHL", "XIX", "XIY", "XIZ", "XSP"]
]

# TODO: Actually replace T with None and have a function instead of access to cctable
cctable = ["F", "LT", "LE", "ULE", "PE/OV", "M", "Z/EQ", "C/ULT", "T", "GE", "GT", "UGT", "PO/NOV", "P", "NZ/NE", "NC/UGE"]

reg_addr = {
    "INVALID": -1,
    # normal registers
    "RA0": 0x00, "RWA0": 0x00, "XWA0": 0x00, "RW0": 0x01, "QA0": 0x02, "QWA0": 0x02, "QW0": 0x03,
    "RC0": 0x04, "RBC0": 0x04, "XBC0": 0x04, "RB0": 0x05, "QC0": 0x06, "QBC0": 0x06, "QB0": 0x07,
    "RE0": 0x08, "RDE0": 0x08, "XDE0": 0x08, "RD0": 0x09, "QE0": 0x0A, "QDE0": 0x0A, "QD0": 0x0B,
    "RL0": 0x0C, "RHL0": 0x0C, "XHL0": 0x0C, "RH0": 0x0D, "QL0": 0x0E, "QHL0": 0x0E, "QH0": 0x0F,

    "RA1": 0x10, "RWA1": 0x10, "XWA1": 0x10, "RW1": 0x11, "QA1": 0x12, "QWA1": 0x12, "QW1": 0x13,
    "RC1": 0x14, "RBC1": 0x14, "XBC1": 0x14, "RB1": 0x15, "QC1": 0x16, "QBC1": 0x16, "QB1": 0x17,
    "RE1": 0x18, "RDE1": 0x18, "XDE1": 0x18, "RD1": 0x19, "QE1": 0x1A, "QDE1": 0x1A, "QD1": 0x1B,
    "RL1": 0x1C, "RHL1": 0x1C, "XHL1": 0x1C, "RH1": 0x1D, "QL1": 0x1E, "QHL1": 0x1E, "QH1": 0x1F,

    "RA2": 0x20, "RWA2": 0x20, "XWA2": 0x20, "RW2": 0x21, "QA2": 0x22, "QWA2": 0x22, "QW2": 0x23,
    "RC2": 0x24, "RBC2": 0x24, "XBC2": 0x24, "RB2": 0x25, "QC2": 0x26, "QBC2": 0x26, "QB2": 0x27,
    "RE2": 0x28, "RDE2": 0x28, "XDE2": 0x28, "RD2": 0x29, "QE2": 0x2A, "QDE2": 0x2A, "QD2": 0x2B,
    "RL2": 0x2C, "RHL2": 0x2C, "XHL2": 0x2C, "RH2": 0x2D, "QL2": 0x2E, "QHL2": 0x2E, "QH2": 0x2F,

    "RA3": 0x30, "RWA3": 0x30, "XWA3": 0x30, "RW3": 0x31, "QA3": 0x32, "QWA3": 0x32, "QW3": 0x33,
    "RC3": 0x34, "RBC3": 0x34, "XBC3": 0x34, "RB3": 0x35, "QC3": 0x36, "QBC3": 0x36, "QB3": 0x37,
    "RE3": 0x38, "RDE3": 0x38, "XDE3": 0x38, "RD3": 0x39, "QE3": 0x3A, "QDE3": 0x3A, "QD3": 0x3B,
    "RL3": 0x3C, "RHL3": 0x3C, "XHL3": 0x3C, "RH3": 0x3D, "QL3": 0x3E, "QHL3": 0x3E, "QH3": 0x3F,

    "A'": 0xD0, "WA'": 0xD0, "XWA'": 0xD0, "W'": 0xD1, "QA'": 0xD2, "QWA'": 0xD2, "QW'": 0xD3,
    "C'": 0xD4, "BC'": 0xD4, "XBC'": 0xD4, "B'": 0xD5, "QC'": 0xD6, "QBC'": 0xD6, "QB'": 0xD7,
    "E'": 0xD8, "DE'": 0xD8, "XDE'": 0xD8, "D'": 0xD9, "QE'": 0xDA, "QDE'": 0xDA, "QD'": 0xDB,
    "L'": 0xDC, "HL'": 0xDC, "XHL'": 0xDC, "H'": 0xDD, "QL'": 0xDE, "QHL'": 0xDE, "QH'": 0xDF,

    "A": 0xE0, "WA": 0xE0, "XWA": 0xE0, "W": 0xE1, "QA": 0xE2, "QWA": 0xE2, "QW": 0xE4,
    "C": 0xE4, "BC": 0xE4, "XBC": 0xE4, "B": 0xE5, "QC": 0xE6, "QBC": 0xE6, "QB": 0xE7,
    "E": 0xE8, "DE": 0xE8, "XDE": 0xE8, "D": 0xE9, "QE": 0xEA, "QDE": 0xEA, "QD": 0xEB,
    "L": 0xEC, "HL": 0xEC, "XHL": 0xEC, "H": 0xED, "QL": 0xEE, "QHL": 0xEE, "QH": 0xEF,

    "IXL": 0xF0, "IX": 0xF0, "XIX": 0xF0, "IXH": 0xF1, "QIXL": 0xF2, "QIX": 0xF2, "QIXH": 0xF3,
    "IYL": 0xF4, "IY": 0xF4, "XIY": 0xF4, "IYH": 0xF5, "QIYL": 0xF6, "QIY": 0xF6, "QIYH": 0xF7,
    "IZL": 0xF8, "IZ": 0xF8, "XIZ": 0xF8, "IZH": 0xF9, "QIZL": 0xFA, "QIZ": 0xFA, "QIZH": 0xFB,
    "SPL": 0xFC, "SP": 0xFC, "XSP": 0xFC, "SPH": 0xFD, "QSPL": 0xFE, "QSP": 0xFE, "QSPH": 0xFF,

    # control registers
    "DMAS0": 0x00, "DMAS1": 0x04, "DMAS2": 0x08, "DMAS3": 0x0C,
    "DMAD0": 0x10, "DMAD1": 0x14, "DMAD2": 0x18, "DMAD3": 0x1C,
    "DMAC0": 0x20, "DMAC1": 0x24, "DMAC3": 0x28, "DMAC4": 0x2C,
    "DMAM0": 0x22, "DMAM1": 0x26, "DMAM2": 0x2A, "DMAM3": 0x2E 
}

from tcls_900.tlcs_900_optable import optable, optable_src, optable_dst, optable_reg