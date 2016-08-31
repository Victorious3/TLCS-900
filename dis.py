import getopt
import io
import os
import shutil
import subprocess
import sys
import time
import codecs

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

# Now import everything from the api
from disapi import *

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
        ib = InputBuffer(f, file_len, BOUNDS, ENTRY_POINT)
        ob = OutputBuffer(OUTPUTFILE)
        import tlcs_900 as proc
        executor = InsnPool(proc)
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
        ob.compute_labels(ENTRY_POINT, file_len + ENTRY_POINT) # Labels aren't computed by default
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

            output("\t\t" + str(v2.pc).ljust(padding) + ": " + " ".join([format(i, "0>2X") for i in v2.bytes(ib)]).ljust(14) + " | " + insnentry_to_str(v2, ob))
        last = v2.pc + v2.length

    output("Done in " + str(end) + " seconds.")

    if OUTPUTFILE is not None:
        f.close()

except KeyboardInterrupt:
    print("\n! Received keyboard interrupt, quitting threads.\n")