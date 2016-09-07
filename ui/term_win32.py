import shutil
import threading
import time

import colorama
import ui.term

from ctypes import *

colorama.init()

win32 = windll.kernel32

# C types
class _CONSOLE_CURSOR_INFO(Structure):
    _fields_ = [
        ("size", c_uint32),
        ("visible", c_int)
    ]

class _COORD(Structure):
    _fields_ = [
        ("X", c_short),
        ("Y", c_short)
    ]

class _uChar_U(Union):
    _fields_ = [
        ("UnicodeChar", c_wchar),
        ("AsciiChar", c_char)
    ]

class _KEY_EVENT_RECORD(Structure):
    _fields_ = [
        ("bKeyDown", c_int),
        ("wRepeatCount", c_uint16),
        ("wVirtualKeyCode", c_uint16),
        ("wVirtualScanCode", c_uint16),
        ("uChar", _uChar_U),
        ("dwControlKeyState", c_uint32)
    ]

class _MOUSE_EVENT_RECORD(Structure):
    _fields_ = [
        ("dwMousePosition", _COORD),
        ("dwButtonState", c_uint32),
        ("dwControlKeyState", c_uint32),
        ("dwEventFlags", c_uint32)
    ]

class _WINDOW_BUFFER_SIZE_RECORD(Structure):
    _fields = [("dwSize", _COORD)]

class _MENU_EVENT_RECORD(Structure):
    _fields_ = [("dwCommandId", c_uint32)]

class _FOCUS_EVENT_RECORD(Structure):
    _fields_ = [("bSetFocus", c_int)]

class _Event_U(Union):
    _fields_ = [
        ("KeyEvent",                _KEY_EVENT_RECORD),
        ("MouseEvent",              _MOUSE_EVENT_RECORD),
        ("WindowBufferSizeEvent",   _WINDOW_BUFFER_SIZE_RECORD),
        ("MenuEvent",               _MENU_EVENT_RECORD),
        ("FocusEvent",              _FOCUS_EVENT_RECORD)
    ]

class _INPUT_RECORD(Structure):
    _fields_ = [
        ("EventType", c_uint16),
        ("Event", _Event_U)
    ]


STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11

_stdin  = win32.GetStdHandle(STD_INPUT_HANDLE)
_stdout = win32.GetStdHandle(STD_OUTPUT_HANDLE)

_char = None
_char_lock = threading.Semaphore(0)

_width  = 0
_height = 0

def _resize():
    global _width, _height
    (w, h) = shutil.get_terminal_size()
    print(w, h)
    if w != _width or h != _height:
        crd = _COORD()
        (crd.X, crd.Y) = (w, h)
        (_width, _height) = (w, h)
        win32.SetConsoleScreenBufferSize(_stdout, crd)

def set_cursor(visible):
    ci = _CONSOLE_CURSOR_INFO()
    win32.GetConsoleCursorInfo(_stdout, byref(ci))
    ci.visible = visible
    win32.SetConsoleCursorInfo(_stdout, byref(ci))

def _read_console_input():
    input_record = (_INPUT_RECORD * 16)()
    n_read = c_longlong()

    while True:
        err = win32.ReadConsoleInputA(_stdin, byref(input_record), 16, byref(n_read))
        if err != 0 and n_read.value > 0:
            i = n_read.value
            while i != 0:
                record = input_record[i - 1]
                i -= 1

                tpe = record.EventType
                if tpe == 1: # KEY_EVENT
                    event = record.Event.KeyEvent

                    if ui.term._keyboard_handler:
                        ui.term._keyboard_handler(event.bKeyDown, event.wVirtualScanCode, event.uChar.AsciiChar)

                    if event.bKeyDown == 0: continue

                    global _char, _char_lock
                    _char = event.uChar.AsciiChar
                    _char_lock.release()

                    #print(event.bKeyDown, event.wRepeatCount, event.wVirtualKeyCode, event.wVirtualScanCode, event.uChar.AsciiChar, event.dwControlKeyState)
                elif tpe == 2: # MOUSE_EVENT
                    if ui.term._mouse_handler:
                        event = record.Event.MouseEvent
                        pos = event.dwMousePosition
                        # TODO: Universal format for mouse buttons
                        ui.term._mouse_handler(pos.X, pos.Y, event.dwButtonState, event.d)
                elif tpe == 4: # WINDOW_BUFFER_SIZE_EVENT
                    _resize()
                    if ui.term._resize_handler:
                        event = record.Event.WindowBufferSizeEvent
                        size = event.dwSize
                        ui.term._resize_handler(size.X, size.Y)

        time.sleep(0)

def getch():
    _char_lock.acquire()
    return _char

def finalize():
    set_cursor(True)

_resize()
threading.Thread(daemon = True, target = _read_console_input).start()
