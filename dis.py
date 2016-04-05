import sys, getopt, os, io, struct, math, threading, time

class InputBuffer():
    def __init__(self, data, available):
        self.buffer = bytearray(available)
        # Stores which bytes have already been read
        self.access = bytearray(math.ceil(available / 8))
        data.readinto(self.buffer)
    
    def byte(self, insn, n = 0, peek = False):
        o = insn.pc + n
        if o >= len(self.buffer):
            insn.kill()
            return -1
        if ((self.access[o // 8] >> o % 8) & 0x1 == 0):
            return struct.unpack('<B', self.buffer[o:o + 1])[0]
        else:
            insn.kill()
            return -1
    
    def word(self, insn, n = 0, peek = False):
        b1 = self.byte(insn, n)
        b2 = self.byte(insn, n + 1)
        return b1 | b2 >> 8
        
    def lword(self, insn, n = 0, peek = False):
        w1 = self.word(insn, n)
        w2 = self.word(insn, n + 2)
        return w1 | w2 >> 16
    
    # Not really needed but perhaps at one point this will turn into a framework
    def qword(self, insn, n = 0, peek = False): 
        l1 = self.lword(insn, n)
        l2 = self.lword(insn, n + 4)
        return l1 | l2 >> 32

class Insn(threading.Thread):
    def __init__(self, ibuffer, obuffer, pc = 0):
        threading.Thread.__init__(self)
        self.daemon = True # We want them to die if somebody force quits the program
        
        self.pc = pc
        self.ibuffer = ibuffer
        self.obuffer = obuffer
        
        self.lastinsn = 0 # Last instruction, this is only set if necessary
        self.lastsize = 0
        self.lastr = "INVALID"
        self.lastmem = "INVALID"
        
        # Flag to kill of the thead and let the obuffer refuse input
        self.dead = False 
        
    def run(self):
        while not self.dead:
            opc = tlcs_900.next_insn(insn, None)
            asm = opc[0] + " " + (", ".join(map(str, opc[1:])))
                    
            print(">>> " + asm + "\n")

    def kill(self):
        self.dead = True
    
    def peek(self, n = 0):
        return self.ibuffer.byte(self, n)
    
    def popn(self, n):
        if n == 0: 
            return self.pop()
        elif n == 1: 
            return self.popw()
        elif n == 4:
            return self.popl()
    
    def pop(self):
        b = self.ibuffer.byte(self)
        self.pc += 1
        return b
    def popw(self):
        w = self.ibuffer.word(self)
        self.pc += 2
        return w
    def popl(self):
        l = self.ibuffer.lword(self)
        self.pc += 4
        return l
    def popq(self):
        q = self.ibuffer.qword(self)
        self.pc += 4
        return q
        
inputfile = None
outputfile = None

try:
    opts, args = getopt.getopt(sys.argv[1:],"hi:o:",["ifile=","ofile="])
except getopt.GetoptError:
    print("dis.py -i <inputfile> -o <outputfile>")
    sys.exit(2)
for opt, arg in opts:
    if opt == '-h':
        print("dis.py -i <inputfile> -o <outputfile>")
        sys.exit()
    elif opt in ("-i", "--ifile"):
        inputfile = arg
    elif opt in ("-o", "--ofile"):
        outputfile = arg
    else:
        print("dis.py -i <inputfile> -o <outputfile>")
        sys.exit(3)
if inputfile is None or outputfile is None:
    print("dis.py -i <inputfile> -o <outputfile>")
    sys.exit(3)

if not os.path.isfile(inputfile):
    print("Input file \"" + inputfile + "\" doesn't exist.")
    sys.exit(4)
    
import tlcs_900

try:
    with io.open(inputfile, 'rb') as f:
        ib = InputBuffer(f, os.path.getsize(inputfile))
        insn = Insn(ib, None)
        insn.start()
    while threading.active_count() > 1: # Wait for all threads to die
        time.sleep(0.1)
    print("Done!")
except KeyboardInterrupt:
    print("\n! Received keyboard interrupt, quitting threads.\n")