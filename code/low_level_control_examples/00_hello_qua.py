"""
A simple sandbox to showcase different QUA functionalities during the installation.
"""

from qm.qua import *
from qm import QuantumMachinesManager
from qm import SimulationConfig
from hello_config import *
from iqcc_cloud_client import IQCC_Cloud

###################
# The QUA program #
###################
with program() as hello_qua:
    a = declare(fixed,value=0)
    play("pi" * amp(a), "qubit")
    wait(25, "qubit")

#####################################
#  Open Communication with the QOP  #
#####################################
# qmm = QuantumMachinesManager(host=qop_ip, port=qop_port, cluster_name=cluster_name, octave=octave_config)

###########################
# Run or Simulate Program #
###########################

# simulate = False

# if simulate:
#     # Simulates the QUA program for the specified duration
#     simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
#     # Simulate blocks python until the simulation is done
#     job = qmm.simulate(config, hello_qua, simulation_config)
#     # Plot the simulated samples
#     job.get_simulated_samples().con1.plot()
# else:
qc = IQCC_Cloud(
    quantum_computer_backend="qolab") # token

run_data = qc.execute(hello_qua, config, True) # 60 seconds by default
