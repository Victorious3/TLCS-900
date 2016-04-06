import sys, getopt, os, subprocess, io, struct, math, time, shutil, concurrent.futures
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import tlcs_900 as proc

inputfile = None
outputfile = None
silent = False
bounds = []

def print_help():
    print("dis.py -i <inputfile> -o <outputfile> [-s][-r <from>[:<to>]]")
    sys.exit(2)

print(sys.argv)
try:
    opts, args = getopt.gnu_getopt(sys.argv[0:],"hsr:i:o:",["ifile=","ofile="])
except getopt.GetoptError:
    try:
        opts, args = getopt.gnu_getopt(sys.argv[10:], "hsr:i:o:", ["ifile=", "ofile="])
        #pycharm inserts more commandline options in the beginning that break it, so we skip them
    except getopt.GetoptError:
        print_help()
for opt, arg in opts:
    if opt == "-h":
        print_help()
        sys.exit()
    elif opt == "-s":
        silent = True
    elif opt == "-r":
        try:
            bounds = list(map(int, arg.split(":")))
        except Exception:
            print_help()
        if len(bounds) > 2:
            print_help()
    elif opt in ("-i", "--ifile"):
        inputfile = arg
    elif opt in ("-o", "--ofile"):
        outputfile = arg
    else:
        print_help()

if inputfile is None or outputfile is None:
    print_help()
    sys.exit(3)

if not os.path.isfile(inputfile):
    print("Input file \"" + inputfile + "\" doesn't exist.")
    sys.exit(4)
    
if silent:
    # Silent flag overrides print and clear to do nothing
    sys.stdout = open(os.devnull, 'a')
    clear = lambda: None
else:
    # Setup clear function

    if os.name in ("nt", "dos"):
        clear = lambda: subprocess.call("cls")
    elif os.name in ("linux", "osx", "posix"):
        clear = lambda: subprocess.call("clear")
    else:
        clear = lambda: print("\n" * 120)

class Branch:
    def __init__(self, ep, to, conditional):
        self.ep = ep;
        self.to = to;
        self.conditional = conditional
    def __str__(self):
        ret = str(self.ep) + " -> " + str(self.to)
        if self.conditional:
            ret += " (C)"
        return ret

class OutputBuffer:
    def __init__(self, ofile):
        self.insnmap = {}
        self.branchlist = deque()
        self.ofile = ofile
        
    def insert(self, ep, list):
        self.insnmap[ep] = list
        
    def branch(self, ep, to, conditional = False):
        self.branchlist.append(Branch(ep, to, conditional))
    
class InputBuffer:
    def __init__(self, data, available, bounds = []):
        if len(bounds) > 0:
            mn = bounds[0]
            if mn > 0:
                available = available - mn
                data.read(mn) # Skip bytes
        if len(bounds) > 1:
            available = bounds[1] - bounds[0]
                
        self.buffer = bytearray(available)
        # Stores which bytes have already been read
        self.access = bytearray(math.ceil(available / 8))
        data.readinto(self.buffer)
        
    def was_read(self, o):
        if o >= len(self.buffer): return True
        o1 = o // 8
        o2 = o % 8
        return (self.access[o1] >> o2) & 0x1 == 0x1
    
    def byte(self, insn, n = 0, peek = False):
        o = insn.pc + n
        if o >= len(self.buffer):
            insn.kill()
            return -1
        o1 = o // 8
        o2 = o % 8
        if ((self.access[o1] >> o2) & 0x1 == 0):
            if not peek: self.access[o1] = 0x1 << o2 
            return self.buffer[o]
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

class InsnExecutor:
    def __init__(self, max_workers):
        self.executor = ThreadPoolExecutor(max_workers)
        self.taskCounter = 0

    def execute(self, insn):
        future = self.executor.submit(insn.run)
        future.add_done_callback(self.is_done)
        self.taskCounter += 1

    def is_done(self, result):
        self.taskCounter -= 1

class Insn:
    tasks = 0

    def __init__(self, max_workers, ibuffer, obuffer, pc = 0):
        self.pc = pc
        self.ep = pc # Entry point
        self.executor = executor
        self.ibuffer = ibuffer
        self.obuffer = obuffer
        
        self.lastinsn = 0 # Last instruction, this is only set if necessary
        self.lastsize = 0
        self.lastr = "INVALID"
        self.lastmem = "INVALID"
        
        # List of processed instructions to instert at the entry point
        self.instructions = deque()
        
        # Flag to kill of the thead
        self.dead = False
        
    def run(self):
        while not self.dead:
            opc = proc.next_insn(self)
            self.instructions.append(opc)
        self.obuffer.insert(self.ep, self.instructions)

    def kill(self):
        self.dead = True
    
    def peek(self, n = 0):
        return self.ibuffer.byte(self, n, True)
    
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
    
    # Used by JR, JP/etc to branch
    def branch(self, to, conditional = False):
        if to < 0: return # We don't want to start jumping to invalid addresses
        self.obuffer.branch(self.pc, to, conditional)
        # We don't need this one anymore if we know that we have to branch
        if not conditional: self.kill()
        if not self.ibuffer.was_read(to):
            self.executor.execute(Insn(self.executor, self.ibuffer, self.obuffer, to))

try:
    start = time.time()
    with io.open(inputfile, 'rb') as f:
        ib = InputBuffer(f, os.path.getsize(inputfile), bounds)
        ob = OutputBuffer(outputfile)
        executor = InsnExecutor(6)
        insn = Insn(executor, ib, ob)
        executor.execute(insn)

    while executor.taskCounter > 0:  # Wait for all threads to die
       time.sleep(0.1)
    print("Done in " + str(round(time.time() - start, 3)) + " seconds.")
    if not silent:
        print("Result: ")
        print("=" * (shutil.get_terminal_size((30, 0))[0] - 1))
        print("Branches: ")
        print("\n".join(map(str, ob.branchlist)))
        print("Instructions: ")
        for (k, v) in ob.insnmap.items():
            print("\tSection at " + str(k) + ": ")
            for i in range(0, len(v)):
                v2 = v[i]
                print("\t\t" + str(i + k) + ": " + v2[0] + " " + ", ".join(map(str, v2[1:])))
except KeyboardInterrupt:
    print("\n! Received keyboard interrupt, quitting threads.\n")