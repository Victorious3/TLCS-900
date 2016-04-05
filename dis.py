import sys, getopt, os, io, struct

BUFFER_SIZE = 1048576

class Insn:
    def __init__(self, data, available):
        self.data = data
        self.pc = 0
        self.lastinsn = 0 # Last instruction, this is only set if necessary
        self.lastsize = 0
        self.lastr = "INVALID"
        self.lastmem = "INVALID"
        self.offset = 0
        self.buffer = bytearray(BUFFER_SIZE) # Bytearray for buffering, reads 1MB at a time
        self.available = available
        self.eof = False # Saves if the EOF was reached while parsing
                
        data.readinto(self.buffer)
    
    # Reads the next section into the buffer, resets offset to 0
    def __next(self):
        self.data.readinto(self.buffer)
        self.offset = 0
    
    def peek(self, n = 1):
        o = self.offset + n
        if o > len(self.buffer):
            self.__next()
            o = self.offset + n
        if self.available < n:
            self.eof = True
            return -1
        
        return struct.unpack('<B', self.buffer[o - 1:o])[0]
    
    def popn(self, n):
        if n == 0: 
            return self.pop()
        elif n == 1: 
            return self.popw()
        elif n == 4:
            return self.popl()
    
    def pop(self):
        b = self.peek()
        self.pc += 1
        self.offset += 1
        self.available -= 1
        return b

    def popw(self):
        b1 = self.pop()
        b2 = self.pop()
        return b1 | b2 >> 8

    def popl(self):
        w1 = self.popw()
        w2 = self.popw()
        return w1 | w2 >> 16     
        
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

with io.open(inputfile, 'rb') as f:
    insn = Insn(f, os.path.getsize(inputfile))
    while insn.available > 0:
        opc = tlcs_900.next_insn(insn, None)
        asm = opc[0] + " " + (", ".join(map(str, opc[1:])))
                
        print(">>> " + asm + "\n")
    if insn.eof:
        print("Reached EOF while parsing!")
        print("The last instruction may be corrupted.")
        