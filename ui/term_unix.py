import tty
import sys
import shutil
import signal
import colorama

import ui.term as term


#tty.setraw(sys.stdin)

colorama.init(strip = False, convert = False)

def set_cursor(visible):
    sys.stdout.write("\033[?25h" if visible else "\033[?25l")
    sys.stdout.flush()

def getch():
    return sys.stdin.read(1)

def _on_resize():
    if term._resize_handler:
        (width, height) = shutil.get_terminal_size()
        term._resize_handler(width, height)

def finalize():
    #tty.setcbreak(sys.stdin)
    pass
