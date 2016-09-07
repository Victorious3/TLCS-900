import os
import sys
import shutil
import atexit

import colorama

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

M_LEFT      = 1
M_RIGHT     = 2
M_MIDDLE    = 3

if _WIN32:
    import ui.term_win32 as term
else:
    import ui.term_unix as term

def print_raw(*args):
    print(*args, end = "")

def print_c(*args):
    print(*args, end = Style.RESET_ALL)

def move_cursor(x, y):
    print_raw(Cursor.POS(x, y))

def clear_screen():
    print_raw(colorama.ansi.clear_screen())

def screen_size():
    return shutil.get_terminal_size()

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
    return term.getch()

def poll_event():
    term.poll_event()

def set_cursor(visible):
    term.set_cursor(visible)


_resize_handler = None
_mouse_handler = None
_keyboard_handler = None

# handler: (width, height)
def set_resize_handler(handler):
    global _resize_handler
    _resize_handler = handler

# handler: (x, y, down, key, dwheel)
def set_mouse_handler(handler):
    global _mouse_handler
    _mouse_handler = handler

# handler: (down, key, char)
def set_keyboard_handler(handler):
    global _keyboard_handler
    _keyboard_handler = handler

def finalize():
    term.finalize()

    set_cursor(True)

    # Reset colors and style
    print_raw(Style.RESET_ALL)

atexit.register(finalize)
