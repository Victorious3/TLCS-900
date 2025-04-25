import yaml, sys

class Location:
    def __init__(self, name, address, constants):
        self.name = name
        self.address = address
        self.constants = constants

ADDRESS_TABLE = {}

def load_microcontroller(name):
    with open(name + ".yaml", "rb") as fp:
        data = yaml.safe_load(fp)
    
    for k, v in data.items():
        constants = None
        if isinstance(v, dict):
            address = v["$"]
            constants = v.copy()
            del constants["$"]
        else: address = v

        ADDRESS_TABLE[address] = Location(k, address, constants)
        
def check_address(loc):
    if loc in ADDRESS_TABLE:
        return ADDRESS_TABLE[loc]
    return None