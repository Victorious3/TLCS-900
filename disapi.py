import math
import threading
import multiprocessing
import sys

from collections import deque, Counter
from queue import Queue

def insnentry_to_str(entry, ob):
    return entry.opcode + " " + ", ".join(map(lambda v: insn_to_str(v, ob), entry.instructions))

def insn_to_str(insn, ob):
    if isinstance(insn, Loc):
        label = ob.label(insn.loc)
        if label is not None:
            return str(label)
        return str(insn.loc)
    else:
        return str(insn)

def label_to_str(label):
    if isinstance(label, Label):
        return str(label)
    else: return format(label, "X")

# Holder for a location, used by branching instructions
class Loc:
    def __init__(self, loc):
        self.loc = loc

    def __int__(self):
        return self.loc

    def __str__(self):
        return str(self.loc)

class Branch:
    def __init__(self, ep, to, conditional):
        self.ep = ep # int or Label
        self.to = to # int or Label
        self.conditional = conditional

    def __str__(self):
        ret = label_to_str(self.ep) + " -> " + label_to_str(self.to)
        if self.conditional:
            ret += " ?"
        return ret

class Label:
    def __init__(self, location, count = 1, name = None):
        self.location = location
        self.count = count
        self.name = name or "label_" + format(location, "X")

    def __str__(self):
        return self.name

    # TODO: Better name?
    def to_str(self):
        return self.name + ": " + format(self.location, "X") + " (" + str(self.count) + ")"

    def __int__(self):
        return self.location

class OutputBuffer:
    def __init__(self, ofile):
        self.insnmap = {}
        self.branchlist = deque()
        self.ofile = ofile
        self.labels = {} # List of labels, compute with compute_labels

    def insert(self, ep, lst):
        if len(lst) > 0:
            self.insnmap[ep] = lst

    def datalabel(self, ep):
        name = "data_" + format(ep, "X")
        self.labels[ep] = name

    def branch(self, ep, to, conditional = False):
        self.branchlist.append(Branch(ep, to, conditional))

    def compute_labels(self, lower = 0, upper = sys.maxsize, min_occurance = 0):
        # Count occurrences of branch
        labels = Counter(map(lambda v: v.to, self.branchlist)).items()
        labels = filter(lambda v: v[1] > min_occurance and lower <= v[0] <= upper, labels)
        labels = dict(map(lambda v: (v[0], Label(v[0], v[1])), labels))

        self.labels = labels

        # Update branch list with labels
        for branch in self.branchlist:
            branch.to = self.label(branch.to) or branch.to
            # Misleading information, ep points to the next instruction
            # branch.ep = self.label(branch.ep) or branch.ep

    def label(self, location):
        return self.labels.get(location, None)


class InputBuffer:
    def __init__(self, data, available, bounds = None, entry_point = 0):
        self.min = 0
        self.max = available
        if bounds is not None:
            if len(bounds) > 0:
                mn = bounds[0]
                if mn > 0:
                    available = available - mn
                    data.read(mn) # Skip bytes
                    self.mind = mn
            if len(bounds) > 1:
                available = bounds[1] - bounds[0]
                self.max = bounds[1]

        self.min += entry_point
        self.max += entry_point

        self.buffer = bytearray(available)
        # Stores which bytes have already been read
        self.access = bytearray(math.ceil(available / 8))
        self.entry_point = entry_point
        data.readinto(self.buffer)

    def was_read(self, o):
        o -= self.entry_point
        o1 = o // 8
        o2 = o % 8
        try:
            return (self.access[o1] >> o2) & 0x1 == 0x1
        except IndexError:
            return True

    def byte(self, insn, n = 0, peek = False):
        o = insn.pc + n
        o -= self.entry_point

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
    def __init__(self, proc, max_threads = None):
        self.numThreads = 0
        if max_threads is None:
            max_threads = multiprocessing.cpu_count() * 5
        self.max_threads = max_threads
        self.queue = Queue()
        self.proc = proc

        # A lock used to wake up the polling thread if asynchronous
        self.lock = threading.Semaphore()

    def query(self, insn):
        self.queue.put(insn)

    def signal(self):
        self.numThreads -= 1
        if self.has_cycled():
            # Wake up the polling thread if batch is done processing
            self.lock.release()

    def has_cycled(self):
        return self.numThreads == 0

    def has_finished(self):
        return self.has_cycled() and self.queue.empty()

    def poll_all(self, blocking = True, callback = None):
        if not blocking and callback is None:
            raise ValueError("If called in a non blocking way you must provide a callback function.")

        def poll_all_impl():
            while not self.has_finished():  # Wait for all threads to process
                self.poll()
                self.lock.acquire()  # Pauses the current thread and waits till batch is processed
            if callback:
                callback()

        if blocking:
            poll_all_impl()
        else:
            thread = threading.Thread(daemon = True, target = poll_all_impl)
            thread.start()

    def poll(self):
        # Batch processing, we only start a new batch when the old
        # one has finished. It is only possible to jump to a location once.
        if not self.has_cycled(): return

        locations = set()
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

    def bytes(self, ibuffer):
        return ibuffer.buffer[self.pc - ibuffer.entry_point:self.pc + self.length - ibuffer.entry_point]

class Insn(threading.Thread):
    def __init__(self, pool, ibuffer, obuffer, pc = 0):
        threading.Thread.__init__(self, daemon = True, name = "Insn at " + str(pc))

        self.pc = pc
        self.ep = pc # Entry point
        self.pool = pool
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
            opc = self.pool.proc.next_insn(self)
            self.__instructions.append(InsnEntry(pc, self.pc - pc, opc[0], opc[1:]))
        if self.__nowrite:
            self.__instructions.pop()
        self.obuffer.insert(self.ep, self.__instructions)
        self.pool.signal()

    def kill(self, nowrite = False):
        self.__dead = True
        self.__nowrite = nowrite

    def peek(self, n = 0):
        return self.ibuffer.byte(self, n, True)

    def popn(self, n):
        if n == 1:
            return self.pop()
        elif n == 2:
            return self.popw()
        elif n == 4:
            return self.popl()
        elif n == 8:
            return self.popq()
        raise ValueError("Invalid number of bytes to pop")

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
        self.pc += 8
        return q

    # Used by JR, JP/etc to branch
    def branch(self, to, conditional = False):
        to = int(to)
        if to < 0: return # We don't want to start jumping to invalid addresses
        self.obuffer.branch(self.pc, to, conditional)
        # We don't need this one anymore if we know that we have to branch
        if not conditional: self.kill()
        if not self.ibuffer.was_read(to):
            self.pool.query(Insn(self.pool, self.ibuffer, self.obuffer, to))