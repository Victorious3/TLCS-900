from pathlib import Path
from tcls_900 import microc

from kivy.config import Config
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

from ui import main
if __name__ == "__main__":
    microc.load_microcontroller("TMP91C016")
    eps = [
        0xFFEC19, 0xFFEC18, 0xFFBFA4, 0xFFBFA0, 
        0xFFBFAC, 0xFFBFB0, 0xFFBF94, 0xFFBF98, 
        0xFFF10E, 0xFFBF9C, 0xFFBFA8
    ]
    main.main(Path("el9900.disproj/el9900.rom"), eps, 0xF00000)