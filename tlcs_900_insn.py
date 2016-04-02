from tlcs_900 import * 

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

def LD_r_X(insn): return

def LD_R_mem(insn): 
    return "LD", popR(insn, '?', insn.lastsize), wrap(insn.lastmem) 

def LD_n_n(insn):
    if (insn.pop() & 0x2) == 0: #BYTE
        return "LD", wrap(insn.pop()), insn.pop()
    else: #WORD
        return "LDW", wrap(insn.pop()), insn.popw()
        

def LD_nn_m(insn): return

def LDB_mem_R(insn): 
    return "LD", wrap(insn.lastmem), popR(insn, '?', BYTE)
def LDW_mem_R(insn): 
    return "LD", wrap(insn.lastmem), popR(insn, '?', WORD)
def LDL_mem_R(insn):
    return "LD", wrap(insn.lastmem), popR(insn, '?', LWORD)

def LDB_m_X(insn): 
    insn.pop()
    return "LD", wrap(insn.lastmem), insn.pop()
def LDW_m_X(insn): 
    insn.pop()
    return "LDW", wrap(insn.lastmem), insn.popw()

def LDW_n_nn(insn):
    insn.pop()
    return "LDW", wrap(insn.pop()), insn.popw()

def LDB_m_nn(insn): return
def LDW_m_nn(insn): return

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
def PUSH_n(insn): return
def PUSHW_nn(insn): return
def PUSH_mem(insn): return

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

def POP_r(insn): return
def POPB_mem(insn): return
def POPW_mem(insn): return

#LDA
def LDAW_R_mem(insn): 
    return "LDA", popR(insn, '?', WORD), insn.lastmem
def LDAL_R_mem(insn):
    return "LDA", popR(insn, '?', LWORD), insn.lastmem
    
#LDAR
def LDAR(insn): return

# 2) Exchange

# EX
def EX_F_F1(insn): return
def EX_R_r(insn): 
    return "EX", popR(insn, '?', insn.lastsize), insn.lastr
def EX_mem_R(insn): 
    return "EX", wrap(insn.lastmem), popR(insn, '?', insn.lastsize)

#MIRR
def MIRR(insn): return

# 3) Load Increment/Decrement & Compare Increment/Decrement Size

#LDXX
def LDI(insn): return
def LDIR(insn): return
def LDD(insn): return
def LDDR(insn): return

#CPXX
def CPI(insn): 
    insn.pop()
    return "CPI", ("A" if insn.lastsize == WORD else "WA"), "(" + regname(insn.lastr) + "+)"
    
def CPIR(insn): return
def CPD(insn): return
def CPDR(insn): return

# 4) Arithmetic Operations

#ADD
def ADD_R_r(insn): 
    return "ADD", popR(insn, '?', insn.lastsize), insn.lastr
def ADD_r_X(insn):
    insn.pop()
    return "ADD", insn.lastr, insn.popn(insn.lastsize)
def ADD_R_mem(insn): 
    return "ADD", popR(insn, '?', insn.lastsize), wrap(insn.lastmem)
def ADD_mem_R(insn): return
def ADD_mem_X(insn): return

#ADC
def ADC_R_r(insn): 
    dst = popR(insn, '?', insn.lastsize)
    return "ADC", dst, insn.lastr
def ADC_r_X(insn): return
def ADC_R_mem(insn): return
def ADC_mem_R(insn): return
def ADC_mem_X(insn): return

#SUB
def SUB_R_r(insn):
    dst = popR(insn, '?', insn.lastsize)
    return "SUB", dst, insn.lastr
def SUB_r_X(insn):
    insn.pop()
    return "SUB", insn.lastr, insn.popn(insn.lastsize)    
def SUB_R_mem(insn): return
def SUB_mem_R(insn): return
def SUB_mem_X(insn): return

#SBC
def SBC_R_r(insn): return
def SBC_r_X(insn): return
def SBC_R_mem(insn): return
def SBC_mem_R(insn): 
    return "SBC", wrap(insn.lastmem), popR(insn, '?', insn.lastmem)
def SBC_mem_X(insn): return

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
    return "CP", insn.lastr, insn.popn(insn.lastsize)
def CP_R_mem(insn): 
    return "CP", wrap(insn.lastmem), popR(insn, '?', insn.lastsize)
def CP_mem_R(insn): 
    return "CP", popR(insn, '?', insn.lastsize), wrap(insn.lastmem)
def CP_mem_X(insn): 
    insn.pop()
    return ("CPW" if insn.lastsize == WORD else "CP"), wrap(insn.lastmem), insn.popn(insn.lastsize)

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
        return
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
        return
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
def DAA(insn): return

#PAA
def PAA(insn): return

#MUL
def MUL_RR_r(insn): 
    return "MUL", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def MUL_rr_X(insn): 
    insn.pop()
    return "MUL", RReg(insn.lastr), insn.popn(insn.lastsize)
def MUL_RR_mem(insn):
    return "MUL", RReg(popR(insn, '?', insn.lastsize)), wrap(insn.lastmem)

#MULS
def MULS_RR_r(insn):
    return "MULS", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def MULS_rr_X(insn):
    insn.pop()
    return "MULS", RReg(insn.lastr), insn.popn(insn.lastsize)
def MULS_RR_mem(insn):
    return "MULS", RReg(popR(insn, '?', insn.lastsize)), wrap(insn.lastmem)

#DIV
def DIV_RR_r(insn):
    return "DIV", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def DIV_rr_X(insn):
    insn.pop()
    return "DIV", RReg(insn.lastr), insn.popn(insn.lastsize)
def DIV_RR_mem(insn):
    return "DIV", RReg(popR(insn, '?', insn.lastsize)), wrap(insn.lastmem)
    
#DIVS
def DIVS_RR_r(insn):
    return "DIVS", RReg(popR(insn, '?', insn.lastsize)), insn.lastr
def DIVS_rr_X(insn):
    insn.pop()
    return "DIVS", RReg(insn.lastr), insn.popn(insn.lastsize)
def DIVS_RR_mem(insn):
    return "DIVS", RReg(popR(insn, '?', insn.lastsize)), wrap(insn.lastmem)

#MULA
def MULA(insn): return

#MINC
def MINC(n):
    def MINCN(insn):
        return
    return MINCN
    
#MDEC
def MDEC(n):
    def MDECN(insn):
        return
    return MDECN
    
# 5) Logical operations

#AND
def AND_R_r(insn): 
    return "AND", popR(insn, '?', insn.lastsize), insn.lastr
def AND_r_X(insn):
    insn.pop()
    return "AND", insn.lastr, insn.popn(insn.lastsize)
def AND_R_mem(insn): return
def AND_mem_R(insn): 
    reg = popR(insn, '?', insn.lastsize)
    return "AND", wrap(insn.lastmem), reg
def AND_mem_X(insn): return

#OR
def OR_R_r(insn): 
    return "OR", popR(insn, '?', insn.lastsize), insn.lastr
def OR_r_X(insn):
    insn.pop()
    return "OR", insn.lastr, insn.popn(insn.lastsize)
def OR_R_mem(insn): return
def OR_mem_R(insn): return
def OR_mem_X(insn): return

#XOR
def XOR_R_r(insn):
    return "XOR", popR(insn, '?', insn.lastsize), insn.lastr
def XOR_r_X(insn): 
    insn.pop()
    return "XOR", insn.lastr, insn.popn(insn.lastsize)
def XOR_R_mem(insn): return
def XOR_mem_R(insn): return
def XOR_mem_X(insn): return

#CPL
def CPL_r(insn): 
    insn.pop()
    return "CPL", insn.lastr

# 6) Bit operations

#LDCF
def LDCF_X_r(insn): return
def LDCF_A_r(insn): return

def LDCF_X3_mem(n):
    def LDCF_N_mem(insn):
        return
    return LDCF_N_mem

def LDCF_A_mem(insn): return

#STCF
def STCF_X_r(insn): return
def STCF_A_r(insn): return

def STCF_X3_mem(n):
    def STCF_N_mem(insn):
        return
    return STCF_N_mem
    
def STCF_A_mem(insn): return

#ANDCF
def ANDCF_X_r(insn): return
def ANDCF_A_r(insn): return

def ANDCF_X3_mem(n):
    def ANDCF_N_mem(insn):
        return
    return ANDCF_N_mem
    
def ANDCF_A_mem(insn): return

#ORCF
def ORCF_X_r(insn): return
def ORCF_A_r(insn): return

def ORCF_X3_mem(n):
    def ORCF_N_mem(insn):
        return
    return ORCF_N_mem
    
def ORCF_A_mem(insn): return

#XORCF
def XORCF_X_r(insn): return
def XORCF_A_r(insn): return

def XORCF_X3_mem(n):
    def XORCF_N_mem(insn):
        return
    return XORCF_N_mem
    
def XORCF_A_mem(insn): return

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
        return "BIT", n, wrap(insn.lastmem)
    return BIT_N_mem

#RES
def RES_X_r(insn):
    insn.pop()
    return "RES", (insn.pop() & 0xF), insn.lastr
def RES_X3_mem(n):
    def RES_N_mem(insn):
        insn.pop()
        return "RES", n, wrap(insn.lastmem)
    return RES_N_mem
    
#SET
def SET_X_r(insn):
    insn.pop()
    return "SET", (insn.pop() & 0xF), insn.lastr
def SET_X3_mem(n):
    def SET_N_mem(insn):
        insn.pop()
        return "SET", n, wrap(insn.lastmem)
    return SET_N_mem

#CHG
def CHG_X_r(insn):
    insn.pop()
    return "CHG", (insn.pop() & 0xF), insn.lastr
def CHG_X3_mem(n):
    def CHG_N_mem(insn):
        insn.pop()
        return "CHG", n, wrap(insn.lastmem)
    return CHG_N_mem

#TSET
def TSET_X_r(insn):
    insn.pop()
    return "TSET", (insn.pop() & 0xF), insn.lastr
def TSET_X3_mem(n):
    def TSET_N_mem(insn):
        insn.pop()
        return "TSET", n, wrap(insn.lastmem)
    return TSET_N_mem

#BS1
def BS1F(insn): return
def BS1B(insn): return

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
def EI(insn): return

#DI
def DI(insn): return

#PUSH
def PUSH_SR(insn): return

#POP
def POP_SR(insn): return

#SWI
def SWI(insn): return

#HALT
def HALT(insn): 
    insn.pop()
    return "HALT"

#LDC
def LDC_cr_r(insn): return
def LDC_r_cr(insn): return

#LDX
def LDX(insn): return

#LINK
def LINK(insn): return

#UNLNK
def UNLNK(insn): return

#LDF
def LDF_n(insn): return

#SCC
def SCC(insn): 
    return "SCC", cctable[popcc(insn)], insn.lastr
    
# 9) Rotate and shift

#RLC
def RLC_X_r(insn):
    insn.pop()
    return "RLC", (insn.pop() & 0xF), insn.lastr
def RLC_A_r(insn): return
def RLC_mem(insn): 
    return ("RLCW" if insn.lastsize == WORD else "RLC"), wrap(insn.lastmem)

#RRC
def RRC_X_r(insn):
    insn.pop()
    return "RRC", (insn.pop() & 0xF), insn.lastr
def RRC_A_r(insn): return
def RRC_mem(insn):
    return ("RRCW" if insn.lastsize == WORD else "RRC"), wrap(insn.lastmem)

#RL
def RL_X_r(insn): 
    insn.pop()
    return "RL", (insn.pop() & 0xF), insn.lastr
def RL_A_r(insn): return
def RL_mem(insn):
    return ("RLW" if insn.lastsize == WORD else "RL"), wrap(insn.lastmem)

#RR
def RR_X_r(insn): 
    insn.pop()
    return "RR", (insn.pop() & 0xF), insn.lastr
def RR_A_r(insn):
    insn.pop()
    return "RR", "A", insn.lastr
def RR_mem(insn):
    return ("RRW" if insn.lastsize == WORD else "RR"), wrap(insn.lastmem)

#SLA
def SLA_X_r(insn): 
    insn.pop()
    return "RR", (insn.pop() & 0xF), insn.lastr
def SLA_A_r(insn):
    insn.pop()
    return "RR", "A", insn.lastr
def SLA_mem(insn):
    return ("SLAW" if insn.lastsize == WORD else "SLA"), wrap(insn.lastmem)

#SRA
def SRA_X_r(insn):
    insn.pop()
    return "SRA", (insn.pop() & 0xF), insn.lastr
def SRA_A_r(insn): 
    insn.pop()
    return "SRA", "A", insn.lastr
def SRA_mem(insn):
    return ("SRAW" if insn.lastsize == WORD else "SRA"), wrap(insn.lastmem)

#SLL
def SLL_X_r(insn):
    insn.pop()
    return "SLL", (insn.pop() & 0xF), insn.lastr
def SLL_A_r(insn):
    insn.pop()
    return "SLL", "A", insn.lastr
def SLL_mem(insn):
    return ("SLLW" if insn.lastsize == WORD else "SLL"), wrap(insn.lastmem)

#SRL
def SRL_X_r(insn):
    insn.pop()
    return "SRL", (insn.pop() & 0xF), insn.lastr
def SRL_A_r(insn):
    insn.pop()
    return "SRL", "A", insn.lastr
def SRL_mem(insn):
    return ("SRLW" if insn.lastsize == WORD else "SRL"), wrap(insn.lastmem)

#RLD / RRD
def RLD(insn):
    insn.pop()
    return "RLD", "A", wrap(insn.lastmem)
def RRD(insn): 
    insn.pop()
    return "RRD", "A", wrap(insn.lastmem)

# 9) Jump, call and return

#JP
def JP_nn(insn): 
    insn.pop()
    return "JP", insn.popw()
def JP_nnn(insn):
    insn.pop()
    return "JP", (insn.popw() | (insn.pop() << 16))

def JP_cc_mem(insn): return

def JR_cc(insn): 
    pc = insn.pc
    cc = cctable[popcc(insn)]
    loc = insn.pop()
    
    return "JR", cc, (pc + 2 + loc)
    return

def JRL_cc(insn): 
    pc = insn.pc
    cc = cctable[popcc(insn)]
    loc = insn.popw()
    
    return "JRL", cc, (pc + 3 + loc)
def JP_mem(insn): return
    
#CALL
def CALL_nn(insn):
    insn.pop()
    return "CALL", insn.popw()
def CALL_nnn(insn):
    insn.pop()
    return "CALL", (insn.popw() | (insn.pop() << 16))

def CALL_cc_mem(insn): return
def CALR(insn): return
def CALL(insn): return

#DJNZ
def DJNZ(insn): 
    insn.pop()
    pc = insn.pc
    loc = insn.pop()
    
    return "DJNZ", insn.lastr, (pc + 3 + loc)

#RET
def RET(insn): insn.pop(); return "RET"
def RET_cc(insn): return
    
def RETD(insn): 
    insn.pop()
    return "RET", insn.popw()
def RETI(insn): 
    insn.pop()
    return "RETI"
