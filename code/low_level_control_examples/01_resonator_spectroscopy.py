"""
        RESONATOR SPECTROSCOPY
This sequence involves measuring the resonator by sending a readout pulse and demodulating the signals to extract the
'I' and 'Q' quadratures across varying readout intermediate frequencies.
The data can then be post-processed to determine the resonator resonance frequency.
This frequency can be used to update the readout intermediate frequency in the configuration under "resonator_IF".

Prerequisites:
    - Ensure calibration of the time of flight, offsets, and gains (default hello_config is calibrated).
    - Define the readout pulse amplitude and duration in the configuration.
    - Specify the expected resonator depletion time in the configuration.
"""

from qm.qua import *
from qm import QuantumMachinesManager
from qm import SimulationConfig
from hello_config import *
from qualang_tools.results import progress_counter, fetching_tool
from qualang_tools.plot import interrupt_on_close
from qualang_tools.loops import from_array
import matplotlib.pyplot as plt
from scipy import signal
from iqcc_cloud_client import IQCC_Cloud


###################
# The QUA program #
###################
n_avg = 100  # The number of averages
# The frequency sweep parameters
f_min = 30 * u.MHz
f_max = 70 * u.MHz
df = 100 * u.kHz
frequencies = np.arange(f_min, f_max + 0.1, df)  # The frequency vector (+ 0.1 to add f_max to frequencies)

with program() as resonator_spec:
    n = declare(int)  # QUA variable for the averaging loop
    f = declare(int)  # QUA variable for the readout frequency
    I = declare(fixed)  # QUA variable for the measured 'I' quadrature
    Q = declare(fixed)  # QUA variable for the measured 'Q' quadrature
    I_st = declare_stream()  # Stream for the 'I' quadrature
    Q_st = declare_stream()  # Stream for the 'Q' quadrature
    n_st = declare_stream()  # Stream for the averaging iteration 'n'

    with for_(n, 0, n < n_avg, n + 1):  # QUA for_ loop for averaging
        with for_(*from_array(f, frequencies)):  # QUA for_ loop for sweeping the frequency
            # Update the frequency of the digital oscillator linked to the resonator element
            update_frequency("resonator", f)
            # Measure the resonator (send a readout pulse and demodulate the signals to get the 'I' & 'Q' quadratures)
            measure(
                "readout",
                "resonator",
                None,
                dual_demod.full("cos", "sin", I),
                dual_demod.full("minus_sin", "cos", Q),
            )
            # Wait for the resonator to deplete
            wait(2500, "resonator")
            # Save the 'I' & 'Q' quadratures to their respective streams
            save(I, I_st)
            save(Q, Q_st)
        # Save the averaging iteration to get the progress bar
        save(n, n_st)

    with stream_processing():
        # Cast the data into a 1D vector, average the 1D vectors together and store the results on the OPX processor
        I_st.buffer(len(frequencies)).average().save("I")
        Q_st.buffer(len(frequencies)).average().save("Q")
        n_st.save("iteration")

#######################
# Simulate or execute #
#######################
qc = IQCC_Cloud(quantum_computer_backend="qolab")

run_data = qc.execute(resonator_spec, config, True) # 60 seconds by default

print(run_data)