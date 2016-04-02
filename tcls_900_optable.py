from tcls_900_insn import * 

optable = [
    [NOP, NORMAL, PUSH_SR, POP_SR, MAX, HALT, EI, RETI, LD_n_n, PUSH_n, LDW_n_nn, PUSHW_nn, INCF, DECF, RET, RETD],
    [RCF, SCF, CCF, ZCF, PUSH_A, POP_A, EX_F_F1, LDF_n, PUSH_F, POP_F, JP_nn, JP_nnn, CALL_nn, CALL_nnn, CALR, None],
    [LD_R_n, LD_R_n, LD_R_n, LD_R_n, LD_R_n, LD_R_n, LD_R_n, LD_R_n, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR],
    [LD_RR_nn, LD_RR_nn, LD_RR_nn, LD_RR_nn, LD_RR_nn, LD_RR_nn, LD_RR_nn, LD_RR_nn, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR, PUSH_RR],
    [LD_XRR_nnnn, LD_XRR_nnnn, LD_XRR_nnnn, LD_XRR_nnnn, LD_XRR_nnnn, LD_XRR_nnnn, LD_XRR_nnnn, LD_XRR_nnnn, POP_RR, POP_RR, POP_RR, POP_RR, POP_RR, POP_RR, POP_RR, POP_RR],
    [None, None, None, None, None, None, None, None, POP_XRR, POP_XRR, POP_XRR, POP_XRR, POP_XRR, POP_XRR, POP_XRR, POP_XRR],
    [JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc, JR_cc],
    [JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc, JRL_cc],
    [src, src, src, src, src, src, src, src, src, src, src, src, src, src, src, src],
    [src, src, src, src, src, src, src, src, src, src, src, src, src, src, src, src],
    [src, src, src, src, src, src, src, src, src, src, src, src, src, src, src, src],
    [dst, dst, dst, dst, dst, dst, dst, dst, dst, dst, dst, dst, dst, dst, dst, dst],
    [src, src, src, src, src, src, None, reg, reg, reg, reg, reg, reg, reg, reg, reg],
    [src, src, src, src, src, src, None, reg, reg, reg, reg, reg, reg, reg, reg, reg],
    [src, src, src, src, src, src, None, reg, reg, reg, reg, reg, reg, reg, reg, reg],
    [dst, dst, dst, dst, dst, dst, None, LDX, SWI(0), SWI(1), SWI(2), SWI(3), SWI(3), SWI(4), SWI(5), SWI(6), SWI(7)]
]

optable_reg = [
    [None, None, None, LD_r_X, PUSH_r, POP_r, CPL_r, NEG_r, MUL_rr_X, MULS_rr_X, DIV_rr_X, DIVS_rr_X, LINK, UNLNK, BS1F, BS1B],
    [DAA, None, EXTZ, EXTS, PAA, None, MIRR, None, None, MULA, None, None, DJNZ, None, None, None],
    [ANDCF_X_r, ORCF_X_r, XORCF_X_r, LDCF_X_r, STCF_X_r, None, None, None, ANDCF_A_r, ORCF_A_r, XORCF_A_r, LDCF_A_r, STCF_A_r, None, LDC_cr_r, LDC_r_cr],
    [RES_X_r, SET_X_r, CHG_X_r, BIT_X_r, TSET_X_r, None, None, None, MINC(1), MINC(2), MINC(4), None, MDEC(1), MDEC(2), MDEC(4), None],
    [MUL_RR_r, MUL_RR_r, MUL_RR_r, MUL_RR_r, MUL_RR_r, MUL_RR_r, MUL_RR_r, MUL_RR_r, MULS_RR_r, MULS_RR_r, MULS_RR_r, MULS_RR_r, MULS_RR_r, MULS_RR_r, MULS_RR_r, MULS_RR_r],
    [DIV_RR_r, DIV_RR_r, DIV_RR_r, DIV_RR_r, DIV_RR_r, DIV_RR_r, DIV_RR_r, DIV_RR_r, DIVS_RR_r, DIVS_RR_r, DIVS_RR_r, DIVS_RR_r, DIVS_RR_r, DIVS_RR_r, DIVS_RR_r, DIVS_RR_r],
    [INC_X3_r(8), INC_X3_r(1), INC_X3_r(2), INC_X3_r(3), INC_X3_r(4), INC_X3_r(5), INC_X3_r(6), INC_X3_r(7), DEC_X3_r(8), DEC_X3_r(1), DEC_X3_r(2), DEC_X3_r(3), DEC_X3_r(4), DEC_X3_r(5), DEC_X3_r(6), DEC_X3_r(7)],
    [SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC, SCC],
    [ADD_R_r, ADD_R_r, ADD_R_r, ADD_R_r, ADD_R_r, ADD_R_r, ADD_R_r, ADD_R_r, LD_R_r, LD_R_r, LD_R_r, LD_R_r, LD_R_r, LD_R_r, LD_R_r, LD_R_r],
    [ADC_R_r, ADC_R_r, ADC_R_r, ADC_R_r, ADC_R_r, ADC_R_r, ADC_R_r, ADC_R_r, LD_r_R, LD_r_R, LD_r_R, LD_r_R, LD_r_R, LD_r_R, LD_r_R, LD_r_R],
    [SUB_R_r, SUB_R_r, SUB_R_r, SUB_R_r, SUB_R_r, SUB_R_r, SUB_R_r, SUB_R_r, LD_r_3X(0), LD_r_3X(1), LD_r_3X(2), LD_r_3X(3), LD_r_3X(4), LD_r_3X(5), LD_r_3X(6), LD_r_3X(7)],
    [SBC_R_r, SBC_R_r, SBC_R_r, SBC_R_r, SBC_R_r, SBC_R_r, SBC_R_r, SBC_R_r, EX_R_r, EX_R_r, EX_R_r, EX_R_r, EX_R_r, EX_R_r, EX_R_r, EX_R_r],
    [AND_R_r, AND_R_r, AND_R_r, AND_R_r, AND_R_r, AND_R_r, AND_R_r, AND_R_r, ADD_r_X, ADC_r_X, SUB_r_X, SBC_r_X, AND_r_X, XOR_r_X, OR_r_X, CP_r_X],
    [XOR_R_r, XOR_R_r, XOR_R_r, XOR_R_r, XOR_R_r, XOR_R_r, XOR_R_r, XOR_R_r, CP_R_3X(0), CP_R_3X(1), CP_R_3X(2), CP_R_3X(3), CP_R_3X(4), CP_R_3X(5), CP_R_3X(6), CP_R_3X(7)],
    [OR_R_r, OR_R_r, OR_R_r, OR_R_r, OR_R_r, OR_R_r, OR_R_r, OR_R_r, RLC_X_r, RRC_X_r, RL_X_r, RR_X_r, SLA_X_r, SRA_X_r, SLL_X_r, SRL_X_r],
    [CP_R_r, CP_R_r, CP_R_r, CP_R_r, CP_R_r, CP_R_r, CP_R_r, CP_R_r, RLC_A_r, RRC_A_r, RL_A_r, RR_A_r, SLA_A_r, SRA_A_r, SLL_A_r, SRL_A_r],
]

optable_src = [
    [None, None, None, None, PUSH_mem, None, RLD, RRD, None, None, None, None, None, None, None, None],
    [LDI, LDIR, LDD, LDDR, CPI, CPIR, CPD, CPDR, None, LD_nn_m, None, None, None, None, None, None],
    [LD_R_mem, LD_R_mem, LD_R_mem, LD_R_mem, LD_R_mem, LD_R_mem, LD_R_mem, LD_R_mem, None, None, None, None, None, None, None, None],
    [EX_mem_R, EX_mem_R, EX_mem_R, EX_mem_R, EX_mem_R, EX_mem_R, EX_mem_R, EX_mem_R, ADD_mem_X, ADC_mem_X, SUB_mem_X, SBC_mem_X, AND_mem_X, XOR_mem_X, OR_mem_X, CP_mem_X],
    [MUL_RR_mem, MUL_RR_mem, MUL_RR_mem, MUL_RR_mem, MUL_RR_mem, MUL_RR_mem, MUL_RR_mem, MUL_RR_mem, MULS_RR_mem, MULS_RR_mem, MULS_RR_mem, MULS_RR_mem, MULS_RR_mem, MULS_RR_mem, MULS_RR_mem, MULS_RR_mem],
    [DIV_RR_mem, DIV_RR_mem, DIV_RR_mem, DIV_RR_mem, DIV_RR_mem, DIV_RR_mem, DIV_RR_mem, DIV_RR_mem, DIVS_RR_mem, DIVS_RR_mem, DIVS_RR_mem, DIVS_RR_mem, DIVS_RR_mem, DIVS_RR_mem, DIVS_RR_mem, DIVS_RR_mem],
    [INC_X3_mem(8), INC_X3_mem(1), INC_X3_mem(2), INC_X3_mem(3), INC_X3_mem(4), INC_X3_mem(5), INC_X3_mem(6), INC_X3_mem(7), INC_X3_mem(8), DEC_X3_mem(1), DEC_X3_mem(2), DEC_X3_mem(3), DEC_X3_mem(4), DEC_X3_mem(5), DEC_X3_mem(6), DEC_X3_mem(7)],
    [None, None, None, None, None, None, None, None, RLC_mem, RRC_mem, RL_mem, RR_mem, SLA_mem, SRA_mem, SLL_mem, SRL_mem],
    [ADD_R_mem, ADD_R_mem, ADD_R_mem, ADD_R_mem, ADD_R_mem, ADD_R_mem, ADD_R_mem, ADD_R_mem, ADD_mem_R, ADD_mem_R, ADD_mem_R, ADD_mem_R, ADD_mem_R, ADD_mem_R, ADD_mem_R, ADD_mem_R],
    [ADC_R_mem, ADC_R_mem, ADC_R_mem, ADC_R_mem, ADC_R_mem, ADC_R_mem, ADC_R_mem, ADC_R_mem, ADC_mem_R, ADC_mem_R, ADC_mem_R, ADC_mem_R, ADC_mem_R, ADC_mem_R, ADC_mem_R, ADC_mem_R],
    [SUB_R_mem, SUB_R_mem, SUB_R_mem, SUB_R_mem, SUB_R_mem, SUB_R_mem, SUB_R_mem, SUB_R_mem, SUB_mem_R, SUB_mem_R, SUB_mem_R, SUB_mem_R, SUB_mem_R, SUB_mem_R, SUB_mem_R, SUB_mem_R],
    [SBC_R_mem, SBC_R_mem, SBC_R_mem, SBC_R_mem, SBC_R_mem, SBC_R_mem, SBC_R_mem, SBC_R_mem, SBC_mem_R, SBC_mem_R, SBC_mem_R, SBC_mem_R, SBC_mem_R, SBC_mem_R, SBC_mem_R, SBC_mem_R],
    [AND_R_mem, AND_R_mem, AND_R_mem, AND_R_mem, AND_R_mem, AND_R_mem, AND_R_mem, AND_R_mem, AND_mem_R, AND_mem_R, AND_mem_R, AND_mem_R, AND_mem_R, AND_mem_R, AND_mem_R, AND_mem_R],
    [XOR_R_mem, XOR_R_mem, XOR_R_mem, XOR_R_mem, XOR_R_mem, XOR_R_mem, XOR_R_mem, XOR_R_mem, XOR_mem_R, XOR_mem_R, XOR_mem_R, XOR_mem_R, XOR_mem_R, XOR_mem_R, XOR_mem_R, XOR_mem_R],
    [OR_R_mem, OR_R_mem, OR_R_mem, OR_R_mem, OR_R_mem, OR_R_mem, OR_R_mem, OR_R_mem, OR_mem_R, OR_mem_R, OR_mem_R, OR_mem_R, OR_mem_R, OR_mem_R, OR_mem_R, OR_mem_R],
    [CP_R_mem, CP_R_mem, CP_R_mem, CP_R_mem, CP_R_mem, CP_R_mem, CP_R_mem, CP_R_mem, CP_mem_R, CP_mem_R, CP_mem_R, CP_mem_R, CP_mem_R, CP_mem_R, CP_mem_R, CP_mem_R]
]

optable_dst = [
    [LDB_m_X, None, LDW_m_X, None, POPB_mem, None, POPW_mem, None, None, None, None, None, None, None, None, None],
    [None, None, None, None, LDB_m_nn, None, LDW_m_nn, None, None, None, None, None, None, None, None, None],
    [LDAW_R_mem, LDAW_R_mem, LDAW_R_mem, LDAW_R_mem, LDAW_R_mem, LDAW_R_mem, LDAW_R_mem, LDAW_R_mem, ANDCF_A_mem, ORCF_A_mem, XORCF_A_mem, LDCF_A_mem, STCF_A_mem, None, None, None],
    [LDAL_R_mem, LDAL_R_mem, LDAL_R_mem, LDAL_R_mem, LDAL_R_mem, LDAL_R_mem, LDAL_R_mem, LDAL_R_mem, None, None, None, None, None, None, None, None],
    [LDB_mem_R, LDB_mem_R, LDB_mem_R, LDB_mem_R, LDB_mem_R, LDB_mem_R, LDB_mem_R, LDB_mem_R, None, None, None, None, None, None, None, None],
    [LDW_mem_R, LDW_mem_R, LDW_mem_R, LDW_mem_R, LDW_mem_R, LDW_mem_R, LDW_mem_R, LDW_mem_R, None, None, None, None, None, None, None, None],
    [LDL_mem_R, LDL_mem_R, LDL_mem_R, LDL_mem_R, LDL_mem_R, LDL_mem_R, LDL_mem_R, LDL_mem_R, None, None, None, None, None, None, None, None],
    [None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
    [ANDCF_X3_mem(0), ANDCF_X3_mem(1), ANDCF_X3_mem(2), ANDCF_X3_mem(3), ANDCF_X3_mem(4), ANDCF_X3_mem(5), ANDCF_X3_mem(6), ANDCF_X3_mem(7), ORCF_X3_mem(0), ORCF_X3_mem(1), ORCF_X3_mem(2), ORCF_X3_mem(3), ORCF_X3_mem(4), ORCF_X3_mem(5), ORCF_X3_mem(6), ORCF_X3_mem(7)],
    [XORCF_X3_mem(0), XORCF_X3_mem(1), XORCF_X3_mem(2), XORCF_X3_mem(3), XORCF_X3_mem(4), XORCF_X3_mem(5), XORCF_X3_mem(6), XORCF_X3_mem(7), LDCF_X3_mem(0), LDCF_X3_mem(1), LDCF_X3_mem(2), LDCF_X3_mem(3), LDCF_X3_mem(4), LDCF_X3_mem(5), LDCF_X3_mem(6), LDCF_X3_mem(7)],
    [STCF_X3_mem(0), STCF_X3_mem(1), STCF_X3_mem(2), STCF_X3_mem(3), STCF_X3_mem(4), STCF_X3_mem(5), STCF_X3_mem(6), STCF_X3_mem(7), TSET_X3_mem(0), TSET_X3_mem(1), TSET_X3_mem(2), TSET_X3_mem(3), TSET_X3_mem(4), TSET_X3_mem(5), TSET_X3_mem(6), TSET_X3_mem(7)],
    [RES_X3_mem(0), RES_X3_mem(1), RES_X3_mem(2), RES_X3_mem(3), RES_X3_mem(4), RES_X3_mem(5), RES_X3_mem(6), RES_X3_mem(7), SET_X3_mem(0), SET_X3_mem(1), SET_X3_mem(2), SET_X3_mem(3), SET_X3_mem(4), SET_X3_mem(5), SET_X3_mem(6), SET_X3_mem(7)],
    [CHG_X3_mem(0), ANDCF_X3_mem(1), ANDCF_X3_mem(2), ANDCF_X3_mem(3), ANDCF_X3_mem(4), ANDCF_X3_mem(5), ANDCF_X3_mem(6), ANDCF_X3_mem(7), BIT_X3_mem(0), BIT_X3_mem(1), BIT_X3_mem(2), BIT_X3_mem(3), BIT_X3_mem(4), BIT_X3_mem(5), BIT_X3_mem(6), BIT_X3_mem(7)],
    [JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem, JP_cc_mem],
    [CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem, CALL_cc_mem],
    [RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc, RET_cc]
]