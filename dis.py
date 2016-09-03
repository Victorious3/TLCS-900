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
ENTRY_POINT = 0         # Equivalent to the .org directive, for alignment
ENCODING    = "ascii"   # Encoding for .db directive
LABELS      = True      # Tries to group branching statements to labels
BRANCHES    = True      # Outputs branching information
RAW         = False     # Outputs the instructions only
TIMER       = True      # Records timing

def print_help():
    print("""\
Usage: py -3 dis.py -i <inputfile> [options]

Options:
    -h, --help:
        Displays this help screen.

    -i, --ifile <inputfile>:
        Specifies a file to read for binary input.
        The file has to exist and you need permission to read it.

    -o, --ofile <outputfile>:
        Specifies a file to write the source to.
        If no such file exists, a new one will be created and otherwise
        it gets overwritten. You need write permission.

        This is a required option if not in --silent mode.

    -s, --silent:
        Completely disables console output, useful if you want to
        run the script automatically.

    -e, --entry, --org <entry_point>:
        Similar to the .org directive, sets an initial offset
        to increment. Useful if you only have parts of a source file
        avalialable to align jumps properly.

        This will insert
            .org <entry_point>
        to the beginning of your source file.

    -r --range <start[:end]>:
        Specifies a byte range to disassemble. The disassembler will
        terminate if it tries to jump into a location outside of that range.

        Useful if you only want to re-create a part of your source.
        Do note that this option will not set the entry point, you need
        to use the appropriate option for that.

    --encoding <encoding>:
        Specifies an encoding for the data segments (.db).
        This option will only have an effect if not in --raw mode.
        The default encoding is ascii, see
            https://docs.python.org/3/library/codecs.html#standard-encodings
        for a list of supported encodings.

        >> Other encodings than ascii might yield to strange outputs due to
        >> unprintable characters not being escaped!

    --raw:
        Disables outputting the instruction's hex code and formats the source
        so that it can be read by a standard assembler.

        Will not output any branching or label information.


The following options are enabled by default:

    --no-labels:
        Prevents creating label information, the output will show the
        raw addresses instead.

    --no-branches:
        Prevents outputting branching information.

    --no-timer:
        Prevents outputting the elapsed time.

    """)
    sys.exit(2)

try:
    opts, args = getopt.gnu_getopt(
        args = sys.argv,
        shortopts = "hsr:i:o:e:",
        longopts = ["ifile=","ofile=", "help", "encoding", "range", "silent", "entry", "org", "no-labels", "no-branches", "no-timer", "raw"])

except getopt.GetoptError:
    print_help()

for opt, arg in opts:
    if opt in ("-h", "--help"):
        print_help()
    elif opt in ("-s", "--silent"):
        SILENT = True
    elif opt in ("-e", "--entry", "--org"):
        ENTRY_POINT = int(arg, 0)
    elif opt in ("-r", "--range"):
        try:
            BOUNDS = list(map(int, arg.split(":")))
        except:
            print("Invalid range specified.")
            sys.exit(6)
        if len(BOUNDS) > 2:
            print("Invalid range specified.")
            sys.exit(6)
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
    elif opt == "--no-branches":
        BRANCHES = False
    elif opt == "--no-timer":
        TIMER = False
    elif opt == "--raw":
        RAW = True
    else:
        print_help()

if INPUTFILE is None:
    print("You must provide an input file with [-i <inputfile>]")
    sys.exit(3)

if OUTPUTFILE is None and SILENT:
    print("You must provide an output file with [-o <outputfile>] when in silent mode")
    sys.exit(5)

if not os.path.isfile(INPUTFILE):
    print("Input file \"" + INPUTFILE + "\" does not exist.")
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

    if TIMER:
        start = time.time()

    with io.open(INPUTFILE, 'rb') as f:
        ib = InputBuffer(f, file_len, BOUNDS, ENTRY_POINT)
        ob = OutputBuffer(OUTPUTFILE)

        import tlcs_900 as proc

        pool = InsnPool(proc)
        insn = Insn(pool, ib, ob, ENTRY_POINT)

    pool.query(insn)
    pool.poll_all()

    if OUTPUTFILE is not None:
        f = io.open(OUTPUTFILE, 'w')

        def output(*args):
            print(*args)
            f.write(" ".join(args) + "\n")
    else:
        output = print

    if LABELS:
        ob.compute_labels(ENTRY_POINT, file_len + ENTRY_POINT)  # Labels aren't computed by default

    if not RAW:
        output("Result: ")
        output("=" * (shutil.get_terminal_size((30, 0))[0] - 1))

        # Labels
        if LABELS:
            output("\nLabels:\n")
            output(", ".join(sorted(map(Label.to_str, ob.labels.values()))))

        # Branches
        if BRANCHES:
            output("\nBranches:\n")
            output(", ".join(map(str, ob.branchlist)))

        # Instructions
        output("\nInstructions:\n")

    if ENTRY_POINT != 0:
        output("\t.org " + format(ENTRY_POINT, "x") + "h")

    # Padding for byte numbers
    padding = len(str(file_len))

    def output_db(nxt, last):
        diff = nxt - last
        if diff < 1: return

        output("; Data Section at " + str(last) + ": ")
        while diff > 0:
            i = nxt - diff
            i2 = min(i + 5, nxt)
            b = ib.buffer[i - ENTRY_POINT:i2 - ENTRY_POINT]

            if not RAW:
                dstr = " ".join([format(i, "0>2X") for i in b])
                # Decode and replace garbage sequences with dots
                decoded = decode_db(b)
                output("\t\t" + str(i).ljust(padding) + ": " + dstr.ljust(14) + " | .db \"" + decoded + "\"")
            else:
                # In raw mode output actual hex codes
                dstr = ", ".join([format(i, "0>2x") + "h" for i in b])
                output("\t.db " + dstr)

            diff -= 5

    last = ENTRY_POINT
    for k, v in sorted(ob.insnmap.items()):
        # Fill with db statements
        output_db(v[0].pc, last)

        output("; Section at " + str(k) + ": ")

        for i in range(0, len(v)):
            v2 = v[i]
            #Label if present
            label = ob.label(v2.pc)

            if not RAW:
                if label is not None:
                    output("\t" + str(label) + ":")

                output("\t\t" + str(v2.pc).ljust(padding) + ": " + " ".join([format(i, "0>2X") for i in v2.bytes(ib)]).ljust(14) + " | " + insnentry_to_str(v2, ob))
            else:
                if label is not None:
                    output((str(label) + ": ").ljust(12) + insnentry_to_str(v2, ob))
                else:
                    output("".ljust(12) + insnentry_to_str(v2, ob))

        last = v2.pc + v2.length

    output_db(file_len + ENTRY_POINT, last)

    if TIMER:
        end = round(time.time() - start, 3)
        output("; Done in " + str(end) + " seconds.")

    if OUTPUTFILE is not None:
        f.close()

except KeyboardInterrupt:
    print("\n! Received keyboard interrupt, quitting threads.\n")