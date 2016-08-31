import getopt
import io
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import multiprocessing
import codecs

from collections import deque, Counter
from queue import Queue

import tlcs_900 as proc

# Command line arguments
INPUTFILE   = None      # Input file, required
OUTPUTFILE  = None      # Output file, optional if not silent
SILENT      = False     # Disables stdout
BOUNDS      = []        # Section to disassemble, defaults to entire file
ENTRY_POINT = 0         # Equivalent to the .org instruction, for alignment
ENCODING    = "ascii"   # Encoding for .db statements
LABELS      = True      # Tries to group branching statements to labels

def print_help():
    # TODO: Pimp help, include all options, detailed description
    print("dis.py -i <inputfile> -o <outputfile> [-s][-r <from>[:<to>]][-e <entry>]")
    sys.exit(2)

try:
    opts, args = getopt.gnu_getopt(
        args = sys.argv,
        shortopts = "hsr:i:o:e:",
        longopts = ["ifile=","ofile=", "encoding", "range", "silent", "entry", "no-labels"])

except getopt.GetoptError:
    print_help()

for opt, arg in opts:
    if opt == "-h":
        print_help()
    elif opt in ("-s", "--silent"):
        SILENT = True
    elif opt in ("-e", "--entry"):
        ENTRY_POINT = int(arg, 0)
    elif opt in ("-r", "--range"):
        try:
            BOUNDS = list(map(int, arg.split(":")))
        except:
            print_help()
        if len(BOUNDS) > 2:
            print_help()
    elif opt in ("-i", "--ifile"):
        INPUTFILE = arg
    elif opt in ("-o", "--ofile"):
        OUTPUTFILE = arg
    elif opt == "--encoding":
        try:
            codecs.lookup(arg)
        except LookupError:
            print("Codec '" + arg + "' either doesn't exist or isn't supported on this machine.")
            sys.exit(6)
        ENCODING = arg
    elif opt == "--no-labels":
        LABELS = False
    else:
        print_help()

if INPUTFILE is None:
    print("You must provide an input file with [-i <inputfile>]")
    sys.exit(3)

if OUTPUTFILE is None and SILENT:
    print("You must provide an output file with [-o <outputfile>] when in silent mode")
    sys.exit(5)

if not os.path.isfile(INPUTFILE):
    print("Input file \"" + INPUTFILE + "\" doesn't exist.")
    sys.exit(4)
    
if SILENT:
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
        self.ep = ep # int or Label
        self.to = to # int or Label
        self.conditional = conditional

    def __str__(self):
        ret = str(self.ep) + " -> " + str(self.to)
        if self.conditional:
            ret += " ?"
        return ret

def generate_name(prefix):
    ident = 0
    while True:
        yield prefix + format(ident, "X")
        ident += 1

class Label:
    name_generator = generate_name("label_")

    def __init__(self, location, count = 1, name = None):
        self.location = location
        self.count = count
        self.name = name or next(Label.name_generator)

    def __str__(self):
        return self.name

    # TODO: Better name?
    def to_str(self):
        return self.name + ": " + str(self.location) + " (" + str(self.count) + ")"

    def __int__(self):
        return self.location

class OutputBuffer:
    def __init__(self, ofile):
        self.insnmap = {}
        self.branchlist = deque()
        self.ofile = ofile
        self.labels = {} # List of labels, compute with create_labels()
        
    def insert(self, ep, lst):
        if len(lst) > 0:
            self.insnmap[ep] = lst
        
    def branch(self, ep, to, conditional = False):
        self.branchlist.append(Branch(ep, to, conditional))

    def compute_labels(self, min_occurance = 0):
        # Count occurrences of branch
        labels = Counter(map(lambda v: v.to, self.branchlist)).items()

        if min_occurance > 0:
            labels = filter(lambda v: v[1] > min_occurance, labels)

        labels = dict(map(lambda v: (v[0], Label(v[0], v[1])), labels))

        self.labels = labels

        # Update branch list with labels
        for branch in self.branchlist:
            branch.to = self.label(branch.to) or branch.to
            branch.ep = self.label(branch.ep) or branch.ep

    def label(self, location):
        return self.labels.get(location, None)


class InputBuffer:
    def __init__(self, data, available, bounds = None):
        if bounds is not None:
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
        o -= ENTRY_POINT

        if o >= len(self.buffer): return True
        o1 = o // 8
        o2 = o % 8
        return (self.access[o1] >> o2) & 0x1 == 0x1
    
    def byte(self, insn, n = 0, peek = False):
        o = insn.pc + n
        o -= ENTRY_POINT

        if o >= len(self.buffer):
            insn.kill(True)
            return -1
        o1 = o // 8
        o2 = o % 8
        if (self.access[o1] >> o2) & 0x1 == 0:
            if not peek:
                self.access[o1] |= (0x1 << o2)
            return self.buffer[o]
        insn.kill(True)
        return -1
    
    def word(self, insn, n = 0, peek = False):
        b1 = self.byte(insn, n, peek)
        b2 = self.byte(insn, n + 1, peek)
        return b1 | (b2 << 8)
        
    def lword(self, insn, n = 0, peek = False):
        w1 = self.word(insn, n, peek)
        w2 = self.word(insn, n + 2, peek)
        return w1 | (w2 << 16)
    
    # Not really needed but perhaps at one point this will turn into a framework
    def qword(self, insn, n = 0, peek = False): 
        l1 = self.lword(insn, n, peek)
        l2 = self.lword(insn, n + 4, peek)
        return l1 | (l2 << 32)

class InsnPool:
    def __init__(self, max_threads = None):
        self.numThreads = 0
        if max_threads is None:
            max_threads = multiprocessing.cpu_count() * 5
        self.max_threads = max_threads
        self.queue = Queue()

    def query(self, insn):
        self.queue.put(insn)

    def done(self):
        self.numThreads -= 1

    def poll(self):
        # Batch processing, we only start a new batch when the old
        # one has finished. It is only possible to jump to a location once.
        locations = set()
        if self.numThreads != 0: return
        while self.numThreads < self.max_threads and not self.queue.empty():
            insn = self.queue.get_nowait()
            if insn.pc in locations:
                continue
            else:
                locations.add(insn.pc)

            insn.start()
            self.numThreads += 1

class InsnEntry:
    def __init__(self, pc, length, opcode, instructions):
        self.pc = pc
        self.length = length
        self.opcode = opcode
        self.instructions = instructions

    def __str__(self):
        return self.opcode + " " + ", ".join(map(str, self.instructions))

    def bytes(self, ibuffer):
        return ibuffer.buffer[self.pc - ENTRY_POINT:self.pc + self.length - ENTRY_POINT]

class Insn(threading.Thread):
    def __init__(self, executor, ibuffer, obuffer, pc = 0):
        threading.Thread.__init__(self, daemon = True)

        self.pc = pc
        self.ep = pc # Entry point
        self.executor = executor
        self.ibuffer = ibuffer
        self.obuffer = obuffer
        
        self.lastinsn = 0 # Last instruction, this is only set if necessary
        self.lastsize = 0
        self.lastr = "INVALID"
        self.lastmem = "INVALID"
        
        # List of processed instructions to insert at the entry point
        self.__instructions = deque()
        
        # Flag to kill of the thread
        self.__dead = False
        # Flag to check if the last byte should be written.
        # This is used if the Insn runs into an already processed segment,
        # In this case the last byte is -1 and should not be written.
        self.__nowrite = False
        
    def run(self):
        while not self.__dead:
            pc = self.pc
            opc = proc.next_insn(self)
            self.__instructions.append(InsnEntry(pc, self.pc - pc, opc[0], opc[1:]))
        if self.__nowrite:
            self.__instructions.pop()
        self.obuffer.insert(self.ep, self.__instructions)
        self.executor.done()

    def kill(self, nowrite = False):
        self.__dead = True
        self.__nowrite = nowrite
    
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
            self.executor.query(Insn(self.executor, self.ibuffer, self.obuffer, to))

# Helper function to decode db statements
def decode_db(buffer):

    # Replace unprintable ascii characters with dots
    if ENCODING == "ascii":
        for i, v in enumerate(buffer):
            if v < 0x20 or v > 0x7E:
                buffer[i] = 0x2E
        return buffer.decode("ascii")

    # Else we go with a more general escape sequence
    # This might not align perfectly, more codecs aren't
    # supported as of now.
    # TODO: Support more codecs, do ascii replace for derived encodings as well

    buffer = buffer.decode(ENCODING, "replace") \
        .replace("\0", ".") \
        .replace("\n", ".") \
        .replace("\r", ".") \
        .replace("\a", ".") \
        .replace("\t", ".") \
        .replace("\uFFFD", ".")

    return buffer

try:
    file_len = os.path.getsize(INPUTFILE)
    start = time.time()

    with io.open(INPUTFILE, 'rb') as f:
        ib = InputBuffer(f, file_len, BOUNDS)
        ob = OutputBuffer(OUTPUTFILE)
        executor = InsnPool()
        insn = Insn(executor, ib, ob, ENTRY_POINT)

    executor.query(insn)
    executor.poll()

    while executor.numThreads > 0 and not executor.queue.empty():  # Wait for all threads to process
        time.sleep(0.1)
        executor.poll()

    end = round(time.time() - start, 3)

    if OUTPUTFILE is not None:
        f = io.open(OUTPUTFILE, 'w')

        def output(*args):
            print(*args)
            f.write(" ".join(args) + "\n")
    else:
        output = print

    output("Result: ")
    output("=" * (shutil.get_terminal_size((30, 0))[0] - 1))

    # Labels
    if LABELS:
        output("\nLabels:\n")
        ob.compute_labels() # Labels aren't computed by default
        output(", ".join(sorted(map(Label.to_str, ob.labels.values()))))

    # Branches
    output("\nBranches:\n")
    output(", ".join(map(str, ob.branchlist)))

    # Instructions
    output("\nInstructions:\n")

    # Padding for byte numbers
    padding = len(str(file_len))

    last = ENTRY_POINT
    for k, v in sorted(ob.insnmap.items()):
        nxt = v[0].pc
        diff = nxt - last

        # Fill with db statements
        if diff > 1:
            output("Data Section at " + str(last) + ": ")
            while diff > 0:
                i = nxt - diff
                i2 = min(i + 5, nxt)
                b = ib.buffer[i - ENTRY_POINT:i2 - ENTRY_POINT]
                dstr = " ".join([format(i, "0>2X") for i in b])

                # Decode and replace garbage sequences with dots
                decoded = decode_db(b)

                output("\t\t" + str(i).ljust(padding) + ": " + dstr.ljust(14) + " | db \"" + decoded + "\"")
                diff -= 5

        output("Section at " + str(k) + ": ")

        for i in range(0, len(v)):
            v2 = v[i]
            #Label if present
            label = ob.label(v2.pc)
            if label is not None:
                output("\t" + str(label) + ":")

            output("\t\t" + str(v2.pc).ljust(padding) + ": " + " ".join([format(i, "0>2X") for i in v2.bytes(ib)]).ljust(14) + " | " + str(v2))
        last = v2.pc + v2.length

    output("Done in " + str(end) + " seconds.")

    if OUTPUTFILE is not None:
        f.close()

except KeyboardInterrupt:
    print("\n! Received keyboard interrupt, quitting threads.\n")