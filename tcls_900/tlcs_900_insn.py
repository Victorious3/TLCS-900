from disapi import Loc
from tcls_900.tlcs_900 import *

# 1) Load Instructions

#LD
def LD_R_r(insn): 
    return "LD", popR(insn, '?', insn.lastsize), insn.lastr
def LD_r_R(insn):
    return "LD", insn.lastr, popR(insn, '?', insn.lastsize)
    
def LD_r_3X(n): 
    def LD_N(insn):
        insn.pop()
        return "LD", insn.lastr, n
    return LD_N

def LD_R_n(insn):
    return "LD", popR(insn, 'zzz'), insn.pop()
def LD_RR_nn(insn):
    return "LD", popR(insn, 'zzz'), insn.popw()
def LD_XRR_nnnn(insn): 
    return "LD", popR(insn, 'zzz'), insn.popl()
def LD_r_X(insn):
    insn.pop()
    return "LD", insn.lastr, popn_sz(insn, insn.lastsize) 
def LD_R_mem(insn): 
    return "LD", popR(insn, '?', insn.lastsize), insn.lastmem 

def LD_n_n(insn):
    if (insn.pop() & 0x2) == 0: #BYTE
        return "LD", Mem(insn, insn.pop()), insn.pop()
    else: #WORD
        return "LDW", Mem(insn, insn.pop()), insn.popw()
        
def LD_nn_m(insn):
    insn.pop()
    return ("LDW" if insn.lastsize == WORD else "LD"), Mem(insn, insn.popw()), insn.lastmem
def LDB_mem_R(insn): 
    return "LD", insn.lastmem, popR(insn, '?', BYTE)
def LDW_mem_R(insn): 
    return "LD", insn.lastmem, popR(insn, '?', WORD)
def LDL_mem_R(insn):
    return "LD", insn.lastmem, popR(insn, '?', LWORD)

def LDB_m_X(insn): 
    insn.pop()
    return "LD", insn.lastmem, insn.pop()
def LDW_m_X(insn): 
    insn.pop()
    return "LDW", insn.lastmem, insn.popw()

def LDW_n_nn(insn):
    insn.pop()
    return "LDW", Mem(insn, insn.pop()), insn.popw()

def LDB_m_nn(insn):
    return "LD", insn.lastmem, Mem(insn, insn.popw())
def LDW_m_nn(insn):
    return "LDW", insn.lastmem, Mem(insn, insn.popw())
    
#PUSH
def PUSH_F(insn):
    insn.pop()
    return "PUSH", "F"
def PUSH_A(insn):
    insn.pop()
    return "PUSH", "A"
def PUSH_RR(insn): 
    return "PUSH", popR(insn, 's')
def PUSH_r(insn): 
    return "PUSH", popr(insn, 'zz')
def PUSH_n(insn):
    insn.pop()
    return "PUSH", insn.pop()
def PUSHW_nn(insn): 
    insn.pop()
    return "PUSHW", insn.popw()
def PUSH_mem(insn):
    insn.pop() 
    return ("PUSHW" if insn.lastsize == WORD else "PUSH"), insn.lastmem

#POP
def POP_F(insn):
    insn.pop()
    return "POP", "F"
def POP_A(insn):
    insn.pop()
    return "POP", "A"
def POP_RR(insn): 
    return "POP", popR(insn, '?', WORD)
def POP_XRR(insn): 
    return "POP", popR(insn, '?', LWORD)
def POP_r(insn):
    insn.pop() 
    return "POP", insn.lastr
def POPB_mem(insn):
    insn.pop() 
    return "POP", insn.lastmem 
def POPW_mem(insn): 
    insn.pop()
    return "POPW", insn.lastmem

#LDA
def LDAW_R_mem(insn): 
    lastmem = insn.lastmem
    lastmem.plain_addr = True
    return "LDA", popR(insn, '?', WORD), lastmem
def LDAL_R_mem(insn):
    lastmem = insn.lastmem
    lastmem.plain_addr = True
    return "LDA", popR(insn, '?', LWORD), lastmem
    
#LDAR
# Couldn't find it in the documentation, did they forget about this or is it not implemented?
def LDAR(insn):
    insn.pop()
    offset = insn.popw()
    if offset > 32767:
        offset -= 65536
    return "LDAR", popR(insn, 's'), Loc(insn.pc + offset + 5) # TODO: Maybe 4? Test this!


# 2) Exchange

# EX
def EX_F_F1(insn):
    insn.pop()
    return "EX", "F", "F'"
def EX_R_r(insn): 
    return "EX", popR(insn, '?', insn.lastsize), insn.lastr
def EX_mem_R(insn): 
    return "EX", insn.lastmem, popR(insn, '?', insn.lastsize)

#MIRR
def MIRR(insn): 
    insn.pop()
    return "MIRR", insn.lastr

# 3) Load Increment/Decrement & Compare Increment/Decrement Size

# Helper function for special register code
def LD(insn):
    if (insn.lastinsn & 0xF) == 0b0011:
        return "(XDE+)", "(XHL+)"
    elif (insn.lastinsn & 0xF) == 0b0101:
        return "(XIX+)", "(XIY+)"
    else:
        return "INVALID", "INVALID"

#LDXX
def LDI(insn): 
    r1, r2 = LD(insn)
    return ("LDIW" if insn.lastsize == WORD else "LDI"), r1, r2
def LDIR(insn): 
    r1, r2 = LD(insn)
    return ("LDIRW" if insn.lastsize == WORD else "LDIR"), r1, r2
def LDD(insn): 
    r1, r2 = LD(insn)
    return ("LDDW" if insn.lastsize == WORD else "LDD"), r1, r2
def LDDR(insn): 
    r1, r2 = LD(insn)
    return ("LDDRW" if insn.lastsize == WORD else "LDDR"), r1, r2

#CPXX
def CPI(insn): 
    insn.pop()
    return "CPI", ("A" if insn.lastsize == WORD else "WA"), "(" + str(insn.lastr) + "+)"
    
def CPIR(insn):
    insn.pop()
    return "CPIR", ("A" if insn.lastsize == WORD else "WA"), "(" + str(insn.lastr) + "+)"

def CPD(insn): 
    insn.pop()
    r1 = "AW" if insn.lastsize == WORD else "W"
    r2 = str(insn.lastr) + "-" 
    return "CPD", r1, r2
def CPDR(insn): 
    insn.pop()
    r1 = "AW" if insn.lastsize == WORD else "W"
    r2 = str(insn.lastr) + "-" 
    return "CPDR", r1, r2

# 4) Arithmetic Operations

#ADD
def ADD_R_r(insn): 
    return "ADD", popR(insn, '?', insn.lastsize), insn.lastr
def ADD_r_X(insn):
    insn.pop()
    return "ADD", insn.lastr, popn_sz(insn, insn.lastsize)
def ADD_R_mem(insn): 
    return "ADD", popR(insn, '?', insn.lastsize), insn.lastmem
def ADD_mem_R(insn): 
    return "ADD", insn.lastmem, popR(insn, '?', insn.lastsize)
def ADD_mem_X(insn):
    insn.pop()
    return ("ADDW" if insn.lastsize == WORD else "ADD"), insn.lastmem, popn_sz(insn, insn.lastsize)

#ADC
def ADC_R_r(insn): 
    dst = popR(insn, '?', insn.lastsize)
    return "ADC", dst, insn.lastr
def ADC_r_X(insn):
    insn.pop()
    return "ADC", insn.lastr, popn_sz(insn, insn.lastsize)
def ADC_R_mem(insn):
    return "ADC", popR(insn, '?', insn.lastsize), insn.lastmem
def ADC_mem_R(insn):
    return "ADC", insn.lastmem, popR(insn, '?', insn.lastsize)
def ADC_mem_X(insn): 
    insn.pop()
    return ("ADCW" if insn.lastsize == WORD else "ADC"), insn.lastmem, popn_sz(insn, insn.lastsize)

#SUB
def SUB_R_r(insn):
    dst = popR(insn, '?', insn.lastsize)
    return "SUB", dst, insn.lastr
def SUB_r_X(insn):
    insn.pop()
    return "SUB", insn.lastr, popn_sz(insn, insn.lastsize)    
def SUB_R_mem(insn):
    return "SUB", popR(insn, '?', insn.lastsize), insn.lastmem
def SUB_mem_R(insn): 
    return "SUB", insn.lastmem, popR(insn, '?', insn.lastsize)
def SUB_mem_X(insn):
    insn.pop()
    return ("SUBW" if insn.lastsize == WORD else "SUB"), insn.lastmem, popn_sz(insn, insn.lastsize)

#SBC
def SBC_R_r(insn):
    dst = popR(insn, '?', insn.lastsize)
    return "SBC", dst, insn.lastr
def SBC_r_X(insn):
    insn.pop()
    return "SBC", insn.lastr, popn_sz(insn, insn.lastsize)    
def SBC_R_mem(insn):
    return "SBC", popR(insn, '?', insn.lastsize), insn.lastmem
def SBC_mem_R(insn): 
    return "SBC", insn.lastmem, popR(insn, '?', insn.lastsize)
def SBC_mem_X(insn):
    insn.pop()
    return ("SBCW" if insn.lastsize == WORD else "SBC"), insn.lastmem, popn_sz(insn, insn.lastsize)

#CP
def CP_R_r(insn):
    return "CP", popR(insn, '?', insn.lastsize), insn.lastr    
def CP_R_3X(n):
    def CP_R_N(insn):
        insn.pop()
        return "CP", insn.lastr, n
    return CP_R_N
def CP_r_X(insn): 
    insn.pop()
    return "CP", insn.lastr, popn_sz(insn, insn.lastsize)
def CP_R_mem(insn): 
    return "CP", popR(insn, '?', insn.lastsize), insn.lastmem
def CP_mem_R(insn): 
    return "CP", insn.lastmem, popR(insn, '?', insn.lastsize)
def CP_mem_X(insn): 
    insn.pop()
    return ("CPW" if insn.lastsize == WORD else "CP"), insn.lastmem, popn_sz(insn, insn.lastsize)

#INC
def INCF(insn): 
    insn.pop()
    return "INCF"

# TODO: INC and DEC, replace constant INC 1, REG with INC REG
def INC_X3_r(n):
    def INC_N_r(insn):
        insn.pop()
        return "INC", n, insn.lastr
    return INC_N_r

def INC_X3_mem(n):
    def INC_N_mem(insn):
        insn.pop()
        return ("INCW" if insn.lastsize == WORD else "INC") , n, insn.lastmem
    return INC_N_mem
    
#DEC
def DECF(insn): insn.pop(); return "DECF"

def DEC_X3_r(n):
    def DEC_N_r(insn):
        insn.pop()
        return "DEC", n, insn.lastr
    return DEC_N_r

def DEC_X3_mem(n):
    def DEC_N_mem(insn):
        insn.pop()
        return ("DECW" if insn.lastsize == WORD else "DEC") , n, insn.lastmem
    return DEC_N_mem

#NEG
def NEG_r(insn): 
    insn.pop()
    return "NEG", insn.lastr 

#EXTZ
def EXTZ(insn):
    insn.pop() 
    return "EXTZ", insn.lastr

#EXTS
def EXTS(insn):
    insn.pop() 
    return "EXTS", insn.lastr

#DAA
def DAA(insn):
    insn.pop()
    return "DAA", insn.lastr
#PAA
def PAA(insn): 
    insn.pop()
    return "PAA", insn.lastr

#MUL
def MUL_RR_r(insn): 
    return "MUL", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def MUL_rr_X(insn): 
    insn.pop()
    return "MUL", RReg(insn.lastr), popn_sz(insn, insn.lastsize)
def MUL_RR_mem(insn):
    return "MUL", RReg(popR(insn, '?', insn.lastsize)), insn.lastmem

#MULS
def MULS_RR_r(insn):
    return "MULS", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def MULS_rr_X(insn):
    insn.pop()
    return "MULS", RReg(insn.lastr), popn_sz(insn, insn.lastsize)
def MULS_RR_mem(insn):
    return "MULS", RReg(popR(insn, '?', insn.lastsize)), insn.lastmem

#DIV
def DIV_RR_r(insn):
    return "DIV", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def DIV_rr_X(insn):
    insn.pop()
    return "DIV", RReg(insn.lastr), popn_sz(insn, insn.lastsize)
def DIV_RR_mem(insn):
    return "DIV", RReg(popR(insn, '?', insn.lastsize)), insn.lastmem
    
#DIVS
def DIVS_RR_r(insn):
    return "DIVS", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def DIVS_rr_X(insn):
    insn.pop()
    return "DIVS", RReg(insn.lastr), popn_sz(insn, insn.lastsize)
def DIVS_RR_mem(insn):
    return "DIVS", RReg(popR(insn, '?', insn.lastsize)), insn.lastmem

#MULA
def MULA(insn): 
    insn.pop()
    return "MULA", RReg(popR(insn, '?', WORD))

#MINC
def MINC(n):
    def MINCN(insn):
        insn.pop()
        return "MINC" + str(n), insn.popw() - n, insn.lastr
    return MINCN
    
#MDEC
def MDEC(n):
    def MDECN(insn):
        insn.pop()
        return "MDEC" + str(n), insn.popw() - n, insn.lastr
    return MDECN
    
# 5) Logical operations

#AND
def AND_R_r(insn): 
    return "AND", popR(insn, '?', insn.lastsize), insn.lastr
def AND_r_X(insn):
    insn.pop()
    return "AND", insn.lastr, popn_sz(insn, insn.lastsize)
def AND_R_mem(insn): 
    reg = popR(insn, '?', insn.lastsize)
    return "AND", reg, insn.lastmem
def AND_mem_R(insn): 
    reg = popR(insn, '?', insn.lastsize)
    return "AND", insn.lastmem, reg
def AND_mem_X(insn):
    insn.pop() 
    return ("ANDW" if insn.lastsize == WORD else "AND"), insn.lastmem, popn_sz(insn, insn.lastsize)

#OR
def OR_R_r(insn): 
    return "OR", popR(insn, '?', insn.lastsize), insn.lastr
def OR_r_X(insn):
    insn.pop()
    return "OR", insn.lastr, popn_sz(insn, insn.lastsize)
def OR_R_mem(insn): 
    reg = popR(insn, '?', insn.lastsize)
    return "OR", reg, insn.lastmem
def OR_mem_R(insn):
    reg = popR(insn, '?', insn.lastsize)
    return "OR", insn.lastmem, reg
def OR_mem_X(insn):
    insn.pop() 
    return ("ORW" if insn.lastsize == WORD else "OR"), insn.lastmem, popn_sz(insn, insn.lastsize)

#XOR
def XOR_R_r(insn):
    return "XOR", popR(insn, '?', insn.lastsize), insn.lastr
def XOR_r_X(insn): 
    insn.pop()
    return "XOR", insn.lastr, popn_sz(insn, insn.lastsize)
def XOR_R_mem(insn):
    reg = popR(insn, '?', insn.lastsize)
    return "XOR", reg, insn.lastmem
def XOR_mem_R(insn):
    reg = popR(insn, '?', insn.lastsize)
    return "XOR", insn.lastmem, reg
def XOR_mem_X(insn):
    insn.pop() 
    return ("XORW" if insn.lastsize == WORD else "XOR"), insn.lastmem, popn_sz(insn, insn.lastsize)

#CPL
def CPL_r(insn): 
    insn.pop()
    return "CPL", insn.lastr

# 6) Bit operations

#LDCF
def LDCF_X_r(insn):
    insn.pop()
    return "LDCF", insn.lastr, (insn.pop() & 0xF) 
def LDCF_A_r(insn):
    insn.pop()
    return "LDCF", "A", insn.lastr
def LDCF_X3_mem(n):
    def LDCF_N_mem(insn):
        insn.pop()
        return "LDCF", n, insn.lastmem
    return LDCF_N_mem
def LDCF_A_mem(insn):
    insn.pop()
    return "LDCF", "A", insn.lastmem

#STCF
def STCF_X_r(insn): 
    insn.pop()
    return "STCF", insn.lastr, (insn.pop() & 0xF) 
def STCF_A_r(insn): 
    insn.pop()
    return "STCF", "A", insn.lastr
def STCF_X3_mem(n):
    def STCF_N_mem(insn):
        insn.pop()
        return "STCF", n, insn.lastmem
    return STCF_N_mem
def STCF_A_mem(insn):
    insn.pop()
    return "STCF", "A", insn.lastmem

#ANDCF
def ANDCF_X_r(insn):
    insn.pop()
    return "ANDCF", insn.lastr, (insn.pop() & 0xF) 
def ANDCF_A_r(insn):
    insn.pop()
    return "ANDCF", "A", insn.lastr
def ANDCF_X3_mem(n):
    def ANDCF_N_mem(insn):
        insn.pop()
        return "ANDCF", n, insn.lastmem
    return ANDCF_N_mem
def ANDCF_A_mem(insn):
    insn.pop()
    return "ANDCF", "A", insn.lastmem

#ORCF
def ORCF_X_r(insn): 
    insn.pop()
    return "ORCF", insn.lastr, (insn.pop() & 0xF) 
def ORCF_A_r(insn):
    insn.pop()
    return "ORCF", "A", insn.lastr
def ORCF_X3_mem(n):
    def ORCF_N_mem(insn):
        insn.pop()
        return "ORCF", n, insn.lastmem
    return ORCF_N_mem
def ORCF_A_mem(insn):
    insn.pop()
    return "ORCF", "A", insn.lastmem

#XORCF
def XORCF_X_r(insn):
    insn.pop()
    return "XORCF", insn.lastr, (insn.pop() & 0xF) 
def XORCF_A_r(insn):
    insn.pop()
    return "XORCF", "A", insn.lastr
def XORCF_X3_mem(n):
    def XORCF_N_mem(insn):
        insn.pop()
        return "XORCF", n, insn.lastmem
    return XORCF_N_mem
def XORCF_A_mem(insn):
    insn.pop()
    return "XORCF", "A", insn.lastmem

#RCF, SCF, CCF, ZCF
def RCF(insn): insn.pop(); return "RCF"
def SCF(insn): insn.pop(); return "SCF"
def CCF(insn): insn.pop(); return "CCF"
def ZCF(insn): insn.pop(); return "ZCF"

#BIT
def BIT_X_r(insn): 
    insn.pop()
    return "BIT", (insn.pop() & 0xF), insn.lastr
def BIT_X3_mem(n):
    def BIT_N_mem(insn):
        insn.pop()
        return "BIT", n, insn.lastmem
    return BIT_N_mem

#RES
def RES_X_r(insn):
    insn.pop()
    return "RES", (insn.pop() & 0xF), insn.lastr
def RES_X3_mem(n):
    def RES_N_mem(insn):
        insn.pop()
        return "RES", n, insn.lastmem
    return RES_N_mem
    
#SET
def SET_X_r(insn):
    insn.pop()
    return "SET", (insn.pop() & 0xF), insn.lastr
def SET_X3_mem(n):
    def SET_N_mem(insn):
        insn.pop()
        return "SET", n, insn.lastmem
    return SET_N_mem

#CHG
def CHG_X_r(insn):
    insn.pop()
    return "CHG", (insn.pop() & 0xF), insn.lastr
def CHG_X3_mem(n):
    def CHG_N_mem(insn):
        insn.pop()
        return "CHG", n, insn.lastmem
    return CHG_N_mem

#TSET
def TSET_X_r(insn):
    insn.pop()
    return "TSET", (insn.pop() & 0xF), insn.lastr
def TSET_X3_mem(n):
    def TSET_N_mem(insn):
        insn.pop()
        return "TSET", n, insn.lastmem
    return TSET_N_mem

#BS1
def BS1F(insn): 
    insn.pop()
    return "BS1F", "A", insn.lastr
def BS1B(insn): 
    insn.pop()
    return "BS1B", "A", insn.lastr

# 7) Special operations and CPU control

#NOP
def NOP(insn): insn.pop(); return "NOP"

#NORMAL
def NORMAL(insn): insn.pop(); return "NORMAL"

#MAX
def MAX(insn): insn.pop(); return "MAX"

#MIN
def MIN(insn): insn.pop(); return "MIN"

#EI
def EI(insn): 
    insn.pop()
    return "EI", (insn.pop() & 0x7)

#DI
def DI(insn): 
    insn.popw()
    return "DI"

#PUSH
def PUSH_SR(insn): 
    insn.pop()
    return "PUSH", "SR"

#POP
def POP_SR(insn): 
    insn.pop()
    return "POP", "SR"

#status_register = ["C", "N", "V", "'0'", "H", "'0'", "Z", "S", "RFP0", "RFP1", "RFP2", "MAX", "IFF0", "IFF1", "IFF2", "SYSM"]

#SWI
def SWI(n):
    #r = status_register[n]
    def SWI_N(insn):
         insn.pop()
         return "SWI", n
    return SWI_N

#HALT
def HALT(insn): 
    insn.pop()
    return "HALT"

#LDC
def LDC_cr_r(insn): 
    insn.pop()
    return "LDC", insn.lastr, CReg(insn.lastsize, insn.pop())
def LDC_r_cr(insn): 
    insn.pop()
    return "LDC", CReg(insn.lastsize, insn.pop()), insn.lastr

#LDX
def LDX(insn): 
    insn.pop()
    r1 = insn.pop()
    insn.pop()
    r2 = insn.pop()
    insn.pop()
    return "LDX", Mem(insn, r1), r2

#LINK
def LINK(insn): 
    insn.pop()
    return "LINK", insn.lastr, popn_sz(insn, insn.lastsize)

#UNLK
def UNLK(insn): 
    insn.pop()
    return "UNLINK", insn.lastr

#LDF
def LDF_n(insn): 
    insn.pop()
    return "LDF", (insn.pop() & 0x7)

#SCC
def SCC(insn): 
    return "SCC", cctable[popcc(insn)], insn.lastr
    
# 9) Rotate and shift

#RLC
def RLC_X_r(insn):
    insn.pop()
    return "RLC", (insn.pop() & 0xF), insn.lastr
def RLC_A_r(insn): 
    insn.pop()
    return "RLC", "A", insn.lastr
def RLC_mem(insn): 
    return ("RLCW" if insn.lastsize == WORD else "RLC"), insn.lastmem

#RRC
def RRC_X_r(insn):
    insn.pop()
    return "RRC", (insn.pop() & 0xF), insn.lastr
def RRC_A_r(insn):
    insn.pop()
    return "RRC", "A", insn.lastr
def RRC_mem(insn):
    return ("RRCW" if insn.lastsize == WORD else "RRC"), insn.lastmem

#RL
def RL_X_r(insn): 
    insn.pop()
    return "RL", (insn.pop() & 0xF), insn.lastr
def RL_A_r(insn): 
    insn.pop()
    return "RL", "A", insn.lastr
def RL_mem(insn):
    return ("RLW" if insn.lastsize == WORD else "RL"), insn.lastmem

#RR
def RR_X_r(insn): 
    insn.pop()
    return "RR", (insn.pop() & 0xF), insn.lastr
def RR_A_r(insn):
    insn.pop()
    return "RR", "A", insn.lastr
def RR_mem(insn):
    return ("RRW" if insn.lastsize == WORD else "RR"), insn.lastmem

#SLA
def SLA_X_r(insn): 
    insn.pop()
    return "RR", (insn.pop() & 0xF), insn.lastr
def SLA_A_r(insn):
    insn.pop()
    return "RR", "A", insn.lastr
def SLA_mem(insn):
    return ("SLAW" if insn.lastsize == WORD else "SLA"), insn.lastmem

#SRA
def SRA_X_r(insn):
    insn.pop()
    return "SRA", (insn.pop() & 0xF), insn.lastr
def SRA_A_r(insn): 
    insn.pop()
    return "SRA", "A", insn.lastr
def SRA_mem(insn):
    return ("SRAW" if insn.lastsize == WORD else "SRA"), insn.lastmem

#SLL
def SLL_X_r(insn):
    insn.pop()
    return "SLL", (insn.pop() & 0xF), insn.lastr
def SLL_A_r(insn):
    insn.pop()
    return "SLL", "A", insn.lastr
def SLL_mem(insn):
    return ("SLLW" if insn.lastsize == WORD else "SLL"), insn.lastmem

#SRL
def SRL_X_r(insn):
    insn.pop()
    return "SRL", (insn.pop() & 0xF), insn.lastr
def SRL_A_r(insn):
    insn.pop()
    return "SRL", "A", insn.lastr
def SRL_mem(insn):
    return ("SRLW" if insn.lastsize == WORD else "SRL"), insn.lastmem

#RLD / RRD
def RLD(insn):
    insn.pop()
    return "RLD", "A", insn.lastmem
def RRD(insn): 
    insn.pop()
    return "RRD", "A", insn.lastmem

# 9) Jump, call and return

#JP
def JP_nn(insn): 
    insn.pop()
    to = Loc(insn.popw())
    insn.branch(to)
    
    return "JP", to
def JP_nnn(insn):
    insn.pop()
    to = Loc(insn.popw() | (insn.pop() << 16))
    insn.branch(to)
    
    return "JP", to
def JP_cc_mem(insn):
    cc = cctable[popcc(insn)]
    return "JP", cc, insn.lastmem
    
def JR_cc(insn): 
    pc = insn.pc
    cc = cctable[popcc(insn)]
    offset = insn.pop()
    if offset > 127:
        offset -= 256
    loc = Loc(pc + offset + 2)
    if cc != "F": insn.branch(loc, cc != "T")
    
    return "JR", cc, loc

def JRL_cc(insn): 
    pc = insn.pc
    cc = cctable[popcc(insn)]
    offset = insn.popw()
    if offset > 32767:
        offset -= 65536
    loc = Loc(pc + offset + 3)
    if cc != "F": insn.branch(loc, cc != "T")
    
    return "JRL", cc, loc
    
#CALL
def CALL_nn(insn):
    insn.pop()
    to = Loc(insn.popw())
    insn.branch(to, True, call = True)
    return "CALL", to
def CALL_nnn(insn):
    insn.pop()
    to = Loc(insn.popw() | (insn.pop() << 16))
    insn.branch(to, True, call = True)
    return "CALL", to
def CALL_cc_mem(insn): 
    return "CALL", cctable[popcc(insn)], insn.lastmem
def CALR(insn): 
    insn.pop()
    offset = insn.popw()
    if offset > 32767:
        offset -= 65536
    to = Loc(insn.pc + offset)
    insn.branch(to, True, call = True)
    return "CALR", to

#DJNZ
def DJNZ(insn): 
    insn.pop()
    offset = insn.pop()
    if offset > 127:
        offset -= 256
    loc = Loc(insn.pc + offset)
    insn.branch(loc, True)
    
    return "DJNZ", insn.lastr, loc

#RET
def RET(insn): 
    insn.pop()
    insn.kill()
    return "RET"
def RET_cc(insn):
    if insn.lastinsn != 0xB0: 
        return "INVALID",
    cc = cctable[popcc(insn)]
    if cc == "T":
        insn.kill()
    return "RET", cc
def RETD(insn): 
    insn.pop()
    insn.kill()
    return "RETD", insn.popw()
def RETI(insn): 
    insn.pop()
    insn.kill()
    return "RETI"