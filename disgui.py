from ui import main
from tcls_900 import microc

from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

if __name__ == "__main__":
    microc.load_microcontroller("TMP91C016")
    main.main("rom/el9900.rom", 0xFFEC19, 0xF00000)