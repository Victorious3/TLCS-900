import colorama
import os, sys

Cursor  = colorama.Cursor
Style   = colorama.Style
Fore    = colorama.Fore
Back    = colorama.Back

_WIN32  = os.name == "nt"

KEY_BACK    = 8
KEY_ENTER   = 13

KEY_UP      = 1 << 8
KEY_DOWN    = 2 << 8
KEY_RIGHT   = 3 << 8
KEY_LEFT    = 4 << 8

if _WIN32:
    colorama.init()
    import msvcrt, ctypes

    class _CursorInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_int),
                    ("visible", ctypes.c_byte)]

else:
    import tty

def print_raw(*args):
    print(*args, end = "")

def print_c(*args):
    print(*args, end = Style.RESET_ALL)

def move_cursor(x, y):
    print_raw(Cursor.POS(x, y))

def clear_screen():
    print_raw(colorama.ansi.clear_screen())

# Returns a tuple with the character and key code
def get_key():
    c = getch()
    k = ord(c)
    if k == 224:
        nxt = ord(getch())
        if nxt == 72:
            k = KEY_UP
        elif nxt == 80:
            k = KEY_DOWN
        elif nxt == 77:
            k = KEY_RIGHT
        elif nxt == 75:
            k = KEY_LEFT
    elif k == 0:
        # We don't know how to decode this, skip
        getch()

    return c, k

# Platform specific functions
def getch():
    return _getch()

def set_cursor(visible):
    _set_cursor(visible)

def setup():
    global _getch
    global _set_cursor

    colorama.init()

    if _WIN32:
        def _set_cursor(visible):
            ci = _CursorInfo()
            handle = ctypes.windll.kernel32.GetStdHandle(-11)
            ctypes.windll.kernel32.GetConsoleCursorInfo(handle, ctypes.byref(ci))
            ci.visible = visible
            ctypes.windll.kernel32.SetConsoleCursorInfo(handle, ctypes.byref(ci))

        _getch = msvcrt.getch
        _set_cursor = _set_cursor
    else:
        def _set_cursor(visible):
            sys.stdout.write("\033[?25h" if visible else "\033[?25l")
            sys.stdout.flush()

        tty.setraw(sys.stdin)

        _getch = lambda: sys.stdin.read(1)

def finalize():
    if not _WIN32:
        tty.setcbreak(sys.stdin)

    set_cursor(True)

    # Reset colors and style
    print_raw(Style.RESET_ALL)