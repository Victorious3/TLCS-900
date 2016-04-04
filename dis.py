import sys, getopt, os, io, struct

class Insn:
    def __init__(self, data):
        self.data = data
        self.pc = 0
        self.lastinsn = 0 # Last instruction, this is only set if necessary
        self.lastsize = 0
        self.lastr = "INVALID"
        self.lastmem = "INVALID"
        self.eof = False # Saves if the EOF was reached while parsing
    
    def peek(self, n = 1):
        r = self.data.peek(n)
        if len(r) < n: 
            self.eof = True
            return -1
        return struct.unpack('<B', r[n - 1:n])[0]
    
    def popn(self, n):
        if n == 0: 
            return self.pop()
        elif n == 1: 
            return self.popw()
        else:
            return self.popl()
    
    def pop(self):
        self.pc += 1
        r = self.data.read(1)
        if len(r) < 1:
            self.eof = True 
            return -1
        return struct.unpack('<B', r)[0]

    def popw(self):
        self.pc += 2
        r = self.data.read(2)
        if len(r) < 2:
            self.eof = True
            return -1
        return struct.unpack('<H', r)[0]

    def popl(self):
        self.pc += 4 
        r = self.data.read(4)
        if len(r) < 4:
            self.eof = True
            return -1
        return struct.unpack('<I', r)[0]
         
        
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

with io.open(inputfile, 'rb', buffering = 30) as f:
    insn = Insn(f)
    while f.peek(1) != b'':
        opc = tlcs_900.next_insn(insn, None)
        asm = opc[0] + " " + (", ".join(map(str, opc[1:])))
                
        print(">>> " + asm + "\n")
    if insn.eof:
        print("Reached EOF while parsing!")
        print("The last instruction may be corrupted.")
        