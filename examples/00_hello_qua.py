"""
A simple sandbox to showcase different QUA functionalities during the installation.
"""

from qm.qua import *
from qm import QuantumMachinesManager
from qm import SimulationConfig
from configuration_with_lf_fem_and_mw_fem import *
from iqcc_cloud_client import IQCC_Cloud

###################
# The QUA program #
###################
with program() as hello_qua:
    a = declare(fixed)
    with infinite_loop_():
        with for_(a, 0, a < 1.1, a + 0.05):
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
    quantum_computer_backend="qc_qolab",
    api_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoicXVhbnR1bV9tYWNoaW5lcyIsInFwdSI6eyJxY19xb2xhYiI6eyJmcm9tIjoxNzMzMzQ2MDAwLjAsInRvIjoxNzMzNTY5MjAwLjB9fSwiZXhwaXJlcyI6MTczMzU2OTIwMC4wfQ.euxYU1sVI9QT3Un5P-cmncyp2iS42oPcyl3UPLQt0To"
) # token

run_data = qc.execute(hello_qua, config, True) # 60 seconds by default
