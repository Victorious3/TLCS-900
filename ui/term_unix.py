#import tty, sys
import sys
import colorama


#tty.setraw(sys.stdin)

colorama.init(strip=False, convert=False)

def set_cursor(visible):
    sys.stdout.write("\033[?25h" if visible else "\033[?25l")
    sys.stdout.flush()


getch = lambda: sys.stdin.read(1)

def finalize():
    #tty.setcbreak(sys.stdin)
    pass
