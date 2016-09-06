import time
import shutil

from disapi import *
from gui.functions import *

COLUMNS = 0
ROWS = 0

setup()

clear_screen()
set_cursor(False)

move_cursor(20, 20)
print_c("This is " + Fore.RED + " a TEST.")

(c, k) = get_key()
while k != 3:
    print(c, k)
    (c, k) = get_key()

# Finalize

finalize()
