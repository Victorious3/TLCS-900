import math
import threading
import multiprocessing
import sys

from collections import deque, Counter
from queue import Queue
from typing import Any
from enum import Enum

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
    def __init__(self, ep, to, conditional, call = False):
        self.ep = ep # int or Label
        self.to = to # int or Label
        self.conditional = conditional
        self.call = call

    def __str__(self):
        ret = label_to_str(self.ep) + " -> " + label_to_str(self.to)
        if self.conditional:
            ret += " ?"
        return ret
    
class LabelKind(Enum):
    FUNCTION = 1
    LABEL = 2
    DATA = 3

class Label:
    def __init__(self, location, count = 1, name = None, kind = LabelKind.LABEL):
        self.location = location
        self.count = count
        if name is None:
           loc = format(location, "X")
           if kind == LabelKind.FUNCTION: name = "fun_" + loc
           elif kind == LabelKind.LABEL: name = "label_" + loc
           elif kind == LabelKind.DATA: name = "data_" + loc
           else: assert False
        self.name = name
        self.kind = kind

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
        self.calls = set()
        self.ofile = ofile
        self.labels = {} # List of labels, compute with compute_labels

    def insert(self, ep, lst):
        if len(lst) > 0:
            self.insnmap[ep] = lst

    def datalabel(self, ep):
        label = Label(ep, kind=LabelKind.DATA)
        self.labels[ep] = label
        return label

    def branch(self, ep, to, conditional = False, call = False):
        self.branchlist.append(Branch(ep, to, conditional, call))
        if call: self.calls.add(to)

    def compute_labels(self, lower = 0, upper = sys.maxsize, min_occurance = 0):
        # Count occurrences of branch
        labels = Counter(map(lambda v: int(v.to), self.branchlist)).items()
        labels = filter(lambda v: v[1] > min_occurance and lower <= v[0] <= upper, labels)
        labels = dict(map(lambda v: (v[0], Label(v[0], v[1], kind=(LabelKind.FUNCTION if v[0] in self.calls else LabelKind.LABEL))), labels))

        self.labels.update(labels)

        # Update branch list with labels
        for branch in self.branchlist:
            branch.to = self.label(branch.to) or branch.to
            # Misleading information, ep points to the next instruction
            # branch.ep = self.label(branch.ep) or branch.ep

    def label(self, location):
        return self.labels.get(location, None)


class InputBuffer:
    def __init__(self, data, available, bounds = None, entry_point = 0, exit_on_invalid = False):
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
        self.exit_on_invalid = exit_on_invalid
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

        if o >= len(self.buffer) or o < 0:
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
        self.locations = set()
        self.__error = False

        # A lock used to wake up the polling thread if asynchronous
        self.lock = threading.Semaphore()

    def clear_visited_locations(self):
        self.locations.clear()

    def query(self, insn):
        self.queue.put(insn)

    # Error might point at a PC where it encountered an invalid instruction
    def signal(self, error = -1):
        self.numThreads -= 1
        # Kill all threads
        if error > 0: self.__error = error
        if self.has_cycled():
            # Wake up the polling thread if batch is done processing
            self.lock.release()

    def has_cycled(self):
        return self.numThreads == 0

    def has_finished(self):
        return self.has_cycled() and self.queue.empty()

    # Returns a location if there has been an error and blocking,
    # otherwise calls the callback with the location
    def poll_all(self, blocking = True, callback = None, threaded = True) -> int:
        self.__error = False
        if not blocking and callback is None:
            raise ValueError("If called in a non blocking way you must provide a callback function.")

        def poll_all_impl():
            while not self.has_finished():  # Wait for all threads to process
                self.poll(threaded)
                self.lock.acquire()  # Pauses the current thread and waits till batch is processed
            if callback:
                callback(self.__error)

        if blocking:
            poll_all_impl()
            return self.__error
        else:
            thread = threading.Thread(daemon = True, target = poll_all_impl)
            thread.start()

        return 0

    def poll(self, threaded = True):
        # Batch processing, we only start a new batch when the old
        # one has finished. It is only possible to jump to a location once.
        if not self.has_cycled(): return

        while self.numThreads < self.max_threads and not self.queue.empty():
            insn = self.queue.get_nowait()
            if insn.pc in self.locations:
                continue
            else:
                self.locations.add(insn.pc)

            self.numThreads += 1
            if threaded: 
                insn.start()
            else: insn.run()

class InsnEntry:
    def __init__(self, pc, length, opcode, instructions):
        self.pc = pc
        self.length = length
        self.opcode = opcode
        self.instructions = instructions

    def bytes(self, ibuffer):
        return ibuffer.buffer[self.pc - ibuffer.entry_point:self.pc + self.length - ibuffer.entry_point]

class Insn(threading.Thread):
    def __init__(self, pool, ibuffer, obuffer, pc = 0, do_branch = True):
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
        self.exit_on_invalid = ibuffer.exit_on_invalid
        self.do_branch = do_branch

        # List of processed instructions to insert at the entry point
        self.__instructions = deque()

        # Flag to kill of the thread
        self.__dead = False
        # Flag to check if the last byte should be written.
        # This is used if the Insn runs into an already processed segment,
        # In this case the last byte is -1 and should not be written.
        self.__nowrite = False
        self.__error = False

    def run(self):
        while not self.__dead:
            pc = self.pc
            opc = self.pool.proc.next_insn(self)
            self.__instructions.append(InsnEntry(pc, self.pc - pc, opc[0], opc[1:]))
        if self.__nowrite:
            self.__instructions.pop()
        self.obuffer.insert(self.ep, self.__instructions)
        self.pool.signal(self.pc if self.__error else -1)

    def kill(self, nowrite = False, error = False):
        self.__dead = True
        self.__nowrite = nowrite
        self.__error = error

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
    def branch(self, to, conditional = False, call = False):
        to = int(to)

        # We don't want to start jumping to invalid addresses
        if to < self.ibuffer.min or to > self.ibuffer.max: return

        if self.do_branch:
            self.obuffer.branch(self.pc, to, conditional, call)

        # We don't need this one anymore if we know that we have to branch
        if not conditional: self.kill()
        if not self.ibuffer.was_read(to) and self.do_branch:
            self.pool.query(Insn(self.pool, self.ibuffer, self.obuffer, to))