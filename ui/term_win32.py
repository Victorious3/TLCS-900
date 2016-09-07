import msvcrt, ctypes, shutil
import colorama

win32 = ctypes.windll.kernel32

# C types
class _CursorInfo(ctypes.Structure):
    _fields_ = [("size", ctypes.c_int),
                ("visible", ctypes.c_byte)]

class _COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short),
                ("Y", ctypes.c_short)]

STD_OUTPUT_HANDLE = -11

colorama.init()

stdout = win32.GetStdHandle(STD_OUTPUT_HANDLE)
crd = _COORD()
(crd.X, crd.Y) = shutil.get_terminal_size()
win32.SetConsoleScreenBufferSize(stdout, crd)


def set_cursor(visible):
    ci = _CursorInfo()
    stdout = win32.GetStdHandle(STD_OUTPUT_HANDLE)
    win32.GetConsoleCursorInfo(stdout, ctypes.byref(ci))
    ci.visible = visible
    win32.SetConsoleCursorInfo(stdout, ctypes.byref(ci))

getch = msvcrt.getch

def finalize():
    pass
