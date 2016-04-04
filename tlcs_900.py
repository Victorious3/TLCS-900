# Constants
BYTE = 0
WORD = 1
LWORD = 2

# Class to hold registers
class Reg:
    def __init__(self, ext, size, reg):
        self.ext = ext
        self.size = size
        self.reg = reg
    
    def __str__(self):
        return regname(self)

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

# Class that holds memory addresses
class Mem:
    def __init__(self, address, name = None):
        if name is None:
            self.name = str(address)
        else:
            self.name = name
        self.address = address
        
    def __str__(self):
        return "(%s)" % (self.name)

def call_opc(insn, x, y, optable):
    opc = optable[x][y]   
    if opc is None:
        print(hex(insn.pc) + ":", hex(x), hex(y), "UNDEFINED")
        # Pop it off the stack...
        insn.pop()
        return ("UNDEFINED",)
    else:
        print(hex(insn.pc) + ":", hex(x), hex(y), opc.__name__)
        asm = opc(insn)
        if type(asm) is tuple: 
            return asm
        elif asm is None:
            raise Exception("Not implemented") 
        else: return (asm,)

def src(insn):
    x, y = peekopc(insn)    
    if (x >= 0xC): 
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
    
def next_insn(insn, out):
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
        if (mem & 0x8) == 0:
            # XWA to XSP
            return Mem(0xE0 + 4 * reg, name)
        else:
            # XWA to XSP + d8
            return Mem(0xE0 + 4 * reg + insn.pop(), name)
    elif (mem & 0x4) == 0x4:
        
        mem2 = insn.pop()
        c = (mem2 & 0x2)
        c = 1 if c == 0 else c * 2
        reg = (mem2 & 0xFE) * 4
        name = regname(Reg(True, LWORD, reg))
        if (mem & 0x1) == 0:
            return Mem(reg - c, ("-" + name if c == 1 else "%s-%s" % (name, str(c)))) # -r32
        else:
            return Mem(reg + c, "%s+%s" % (name, (str(c) if c > 1 else ""))) # r32+
    else:
        n = mem & 0x3
        if n == 0: 
            return Mem(insn.pop()) # 8
        elif n == 1:
            return Mem(insn.popw()) # 16
        elif n == 2:
            return Mem(insn.popw() | (insn.pop() >> 16)) # 24
        else:
            mem = insn.pop()
            n = mem & 0x3
            if n == 0:
                reg = (mem & 0xFE) * 4
                name = regname(Reg(True, LWORD, reg))
                return Mem(mem * 4, name) # r32
            elif n == 1:
                reg = (mem & 0xFE) * 4
                name = regname(Reg(True, LWORD, reg))
                offset = insn.popw()
                return Mem(reg + offset, "%s+%s" % (name, str(offset))) # r32 + d16
            elif mem == 0x3:
                reg1 = insn.pop() * 4
                reg2 = insn.pop()
                name = "%s+%s" % (regname(Reg(True, LWORD, reg1)), regname(Reg(True, BYTE, reg2)))
                return Mem(reg1 + reg2, name) # r32 + r8
            else:
                reg1 = insn.pop() * 4
                reg2 = insn.pop() * 2
                name = "%s+%s" % (regname(Reg(True, LWORD, reg1)), regname(Reg(True, WORD, reg2)))
                return Mem(reg1 + reg2, name) # r32 + r16
                
rrtable_8 = ["INVALID", "WA", "INVALID", "BC", "INVALID", "DE", "INVALID", "HL"]

def rregname(register):
    ext = register.ext
    size = register.size
    reg = register.reg
    
    if not ext:
        if size == BYTE:
            return rrtable_8[reg]
        elif size == WORD:
            print(reg)
            return Rregtable[LWORD][reg]
        else: return str(reg)
    else:
        return regname(register)                
    
bnames = ["A", "W", "C", "B", "E", "D", "L", "H"]
wnames = ["WA", "BC", "DE", "HL"]
lnames = ["XWA", "XBC", "XDE", "XHL"]
extnames = ["X", "Y", "Z", "P"]

# takes the returned register of popr / popR
# returns a register name or the address if its an invalid register
def regname(register):
    ext = register.ext
    size = register.size
    reg = register.reg
    
    if size < 0 or size > 2:
        return "INVALID"
    if not ext:
        return Rregtable[size][reg]
    
    if (size == WORD and reg & 1) != 0: 
        return str(reg) # Check if divisible by 2
    elif (size == LWORD and reg & 0b11) != 0: 
        return str(reg) # Check if divisible by 4
    
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
    elif reg >= 0xD0 and reg <= 0xEF:
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
        elif reg <= 0xE0:
            return str(reg)
    elif reg >= 0xF0 and reg <= 0xFF:
        if size == BYTE:
            if (reg & 0b0010) != 0: rname += "Q"
        elif size == LWORD:
            rname += "Z"
        if (reg & 0xFC) == 0xFC:
            rname += "S"
        else: rname += "I"
        rname += extnames[(reg & 0b1100) >> 2]
        if size == BYTE:
            rname += "H" if (reg & 0b0010) != 0 else "L"
    else:
        return str(reg)
    
    return rname
    
lcrnames = ["S0", "S1", "S2", "S3", "D0", "D1", "D2", "D3"]
wcrnames = ["C0", "C1", "C2", "C3"]
bcrnames = ["M0", "M1", "M2", "M3"]

def cregname(reg):
    if reg.size == LWORD:
        if reg.reg == 0x3C: return "XNSP"
        n = (reg.reg / 4)
        if n < 0 or n > 7: return "INVALID"
        return "DMA" + lcrnames[n]
    elif reg.size == WORD:
        if reg.reg == 0x3C: return "INTNEST"
        n = (reg.reg - 0x20) / 4
        if n < 0 or n > 3: return "INVALID"
        return "DMA" + wcrnames[n]
    else:
        n = (reg.reg - 0x22) / 4
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
        
        size = operand_size_table[tpe].index(opsizecode)
        
    return Reg(False, size, rcode)

def peekopc(insn, n = 1):
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
cctable = ["F", "LT", "LE", "ULE", "PE/OV", "M", "Z/EQ", "C", "T", "GE", "GT", "UGT", "PO/NOV", "P", "NZ/NE", "NC"]

from tlcs_900_optable import optable, optable_src, optable_dst, optable_reg 