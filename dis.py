import sys, getopt, os, io, struct

class Insn:
    def __init__(self, data):
        self.data = data
        self.pc = 0
        self.lastsize = 0
        self.lastr = "INVALID"
        self.lastmem = "INVALID"
    
    def peek(self, n = 1): 
        return struct.unpack('<B', self.data.peek(n)[n - 1])[0]
    
    def popn(self, n):
        if n == 0: 
            return self.pop()
        elif n == 1: 
            return self.popw()
        else:
            return self.popl()
    
    def pop(self):
        self.pc += 1
        return struct.unpack('<B', self.data.read(1))[0]

    def popw(self):
        self.pc += 2
        return struct.unpack('<H', self.data.read(2))[0]

    def popl(self):
        self.pc += 4   
        return struct.unpack('<I', self.data.read(4))[0]
         
        
inputfile = None
outputfile = None

try:
    opts, args = getopt.getopt(sys.argv[1:],"hi:o:",["ifile=","ofile="])
except getopt.GetoptError:
    print "dis.py -i <inputfile> -o <outputfile>"
    sys.exit(2)
for opt, arg in opts:
    if opt == '-h':
        print "dis.py -i <inputfile> -o <outputfile>"
        sys.exit()
    elif opt in ("-i", "--ifile"):
        inputfile = arg
    elif opt in ("-o", "--ofile"):
        outputfile = arg
    else:
        print "dis.py -i <inputfile> -o <outputfile>"
        sys.exit(3)
if inputfile is None or outputfile is None:
    print "dis.py -i <inputfile> -o <outputfile>"
    sys.exit(3)

if not os.path.isfile(inputfile):
    print "Input file \"" + inputfile + "\" doesn't exist."
    sys.exit(4)
    
from instructions import next_insn 

with io.open(inputfile, 'rb', buffering = 30) as f:
    insn = Insn(f)
    while f.peek(1) != b'':
        next_insn(insn, None)