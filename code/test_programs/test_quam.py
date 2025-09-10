from pprint import pprint
from quam_libs.components import QuAM
machine = QuAM.load()
config = machine.generate_config()
pprint(config)