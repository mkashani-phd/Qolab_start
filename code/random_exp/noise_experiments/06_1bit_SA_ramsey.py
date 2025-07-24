# %%
"""
        QUBIT SPECTROSCOPY VERSUS FLUX
This sequence involves doing a qubit spectroscopy for several flux biases in order to exhibit the qubit frequency
versus flux response.

Prerequisites:
    - Identification of the resonator's resonance frequency when coupled to the qubit in question (referred to as "resonator_spectroscopy").
    - Calibration of the IQ mixer connected to the qubit drive line (whether it's an external mixer or an Octave port).
    - Identification of the approximate qubit frequency ("qubit_spectroscopy").

Before proceeding to the next node:
    - Update the qubit frequency, labeled as "f_01", in the state.
    - Update the relevant flux points in the state.
    - Save the current state by calling machine.save("quam")
"""
from qualibrate import QualibrationNode, NodeParameters
from typing import Optional, Literal, List


class Parameters(NodeParameters):
    qubits: Optional[List[str]] = None
    num_averages: int = 200
    dc_offset: float = 0.015
    flux_point_joint_or_independent: Literal['joint', 'independent'] = "joint"
    simulate: bool = False
    timeout: int = 100


node = QualibrationNode(name="99_1bit_SA_ramsey", parameters=Parameters())


from qm.qua import *
from qm import SimulationConfig
from qualang_tools.results import progress_counter, fetching_tool
from qualang_tools.plot import interrupt_on_close
from qualang_tools.loops import from_array
from qualang_tools.units import unit
from quam_libs.components import QuAM
from quam_libs.macros import qua_declaration, active_reset, readout_state
import xarray as xr
import xrft
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from qualang_tools.multi_user import qm_session
from quam_libs.macros import active_reset
import matplotlib
from quam_libs.lib.plot_utils import QubitGrid, grid_iter
from quam_libs.lib.save_utils import fetch_results_as_xarray
from quam_libs.lib.fit import peaks_dips

# matplotlib.use("TKAgg")


###################################################
#  Load QuAM and open Communication with the QOP  #
###################################################
# Class containing tools to help handling units and conversions.
u = unit(coerce_to_integer=True)
# Instantiate the QuAM class from the state file
machine = QuAM.load()
# Generate the OPX and Octave configurations
config = machine.generate_config()
octave_config = machine.get_octave_config()
# Open Communication with the QOP
qmm = machine.connect()

# Get the relevant QuAM components
if node.parameters.qubits is None:
    qubits = machine.active_qubits
else:
    qubits = [machine.qubits[q] for q in node.parameters.qubits]
num_qubits = len(qubits)

freqs = np.arange(-5000000, -2000000, 25000, dtype=np.int32)  # Integer values from -5e6 to 0 with step 50000
idle_times = np.arange(420, 601, 100, dtype=np.int32)  # Integer values from 20 to 1000 with step 100
flux_point = node.parameters.flux_point_joint_or_independent  # 'independent' or 'joint'
dc = node.parameters.dc_offset
n_avg = node.parameters.num_averages
###################
# The QUA program #
###################

# %% program for finding optimal freq offset and idle time
with program() as find_optimal_freq_offset_and_idle_time:

    I, I_st, Q, Q_st, n, n_st = qua_declaration(num_qubits=num_qubits)
    state = [declare(int) for _ in range(num_qubits)]
    state_st = [declare_stream() for _ in range(num_qubits)]
    freq = declare(int)  # QUA variable for the flux dc level
    idle_time = declare(int)
    init_state = declare(int)
    
    for i, qubit in enumerate(qubits):

        # Bring the active qubits to the minimum frequency point
        machine.set_all_fluxes(flux_point=flux_point, target=qubit)
        
        with for_(n, 0, n < n_avg, n + 1):
            save(n, n_st)
            
            with for_(*from_array(freq, freqs)):
                with for_(*from_array(idle_time, idle_times)):
                    update_frequency(qubit.xy.name, freq + qubit.xy.intermediate_frequency)
                    # active_reset(qubit, "readout")
                    readout_state(qubit, init_state)
                    align()
                    qubit.xy.play("x90")
                    align()
                    qubit.z.play("const", amplitude_scale=dc / qubit.z.operations["const"].amplitude, duration=idle_time / 4)
                    align()
                    qubit.xy.play("x90")
                    align()
                    # Measure the state of the resonators
                    readout_state(qubit, state[i])
                    assign(state[i], init_state ^ state[i])
                    save(state[i], state_st[i])
                    reset_frame(qubit.xy.name)

    with stream_processing():
        n_st.save("n")
        for i in range(num_qubits):
            state_st[i].buffer(len(idle_times)).buffer(len(freqs)).average().save(f"state{i + 1}")



# %%

###########################
# Run or Simulate Program #
###########################
simulate = node.parameters.simulate

if simulate:
    # Simulates the QUA program for the specified duration
    simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
    job = qmm.simulate(config, find_optimal_freq_offset_and_idle_time, simulation_config)
    job.get_simulated_samples().con1.plot()
    node.results = {"figure": plt.gcf()}
else:
    with qm_session(qmm, config, timeout=node.parameters.timeout) as qm:
        job = qm.execute(find_optimal_freq_offset_and_idle_time)
        results = fetching_tool(job, ["n"], mode="live")
        while results.is_processing():
            # Fetch results
            n = results.fetch_all()[0]
            # Progress bar
            progress_counter(n, n_avg, start_time=results.start_time)


# %%
# %%
if not simulate:
    handles = job.result_handles
    ds = fetch_results_as_xarray(handles, qubits, {"idle_time": idle_times, "freq": freqs})

    node.results = {}
    node.results['ds'] = ds

# %%

# %%
   
idle_time_to_run = 520 
opt_freq = {}
if not simulate:
    grid_names = [q.grid_location for q in qubits]
    grid = QubitGrid(ds, grid_names)
    for ax, qubit in grid_iter(grid):
        opt_freq[qubit['qubit']] = np.abs(ds.sel(qubit = qubit['qubit']).state.sel(idle_time=idle_time_to_run)-0.45).idxmin('freq')
        ds.sel(qubit = qubit['qubit']).state.sel(idle_time=idle_time_to_run).plot(ax =ax)
        ax.axhline(0.45, color='k')
        ax.plot(opt_freq[qubit['qubit']], 0.45, 'o')
        ax.set_title(qubit['qubit'])
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('State')
    grid.fig.suptitle('Avg state vs. detuning')
    plt.tight_layout()
    plt.show()
    node.results['figure_raw'] = grid.fig
# %%
n_avg = 5_000_000


# %% create program for T2 spectoscopy
with program() as Ramsey_noise_spec:

    I, I_st, Q, Q_st, n, n_st = qua_declaration(num_qubits=num_qubits)
    state = [declare(int) for _ in range(num_qubits)]
    state_st = [declare_stream() for _ in range(num_qubits)]
    init_state = declare(int)
    
    for i, qubit in enumerate(qubits):

        # Bring the active qubits to the minimum frequency point
        machine.set_all_fluxes(flux_point=flux_point, target=qubit)
        
        update_frequency(qubit.xy.name, int(opt_freq[qubit.name]) + qubit.xy.intermediate_frequency)

        with for_(n, 0, n < n_avg, n + 1):
            save(n, n_st)
            wait(250)
            readout_state(qubit, init_state)
            align()
            qubit.xy.play("x90", timestamp_stream=f'time_stamp{i+1}')
            align()
            qubit.z.play("const", amplitude_scale=dc / qubit.z.operations["const"].amplitude, duration=idle_time_to_run / 4)
            align()
            qubit.xy.play("x90")
            align()
            # Measure the state of the resonators
            readout_state(qubit, state[i])
            assign(state[i], init_state ^ state[i])
            save(state[i], state_st[i])

    with stream_processing():
        n_st.save("n")
        for i in range(num_qubits):
            state_st[i].buffer(n_avg).save(f"state{i + 1}")

# %% 
###########################
# Run or Simulate Program #
###########################
simulate = node.parameters.simulate

if simulate:
    # Simulates the QUA program for the specified duration
    simulation_config = SimulationConfig(duration=10_000)  # In clock cycles = 4ns
    job = qmm.simulate(config, Ramsey_noise_spec, simulation_config)
    job.get_simulated_samples().con1.plot()
    node.results = {"figure": plt.gcf()}
else:
    with qm_session(qmm, config, timeout=node.parameters.timeout) as qm:
        job = qm.execute(Ramsey_noise_spec)
        results = fetching_tool(job, ["n"], mode="live")
        while results.is_processing():
            # Fetch results
            n = results.fetch_all()[0]
            # Progress bar
            progress_counter(n, n_avg, start_time=results.start_time)


# %%
if not simulate:
    handles = job.result_handles
    ds = fetch_results_as_xarray(handles, qubits, {"n": np.arange(0,n_avg,1)})

    extracted_values = np.array([v for v in ds.time_stamp.values.flatten()]).reshape(ds.time_stamp.values.shape)
    ds['time_stamp'] = xr.DataArray(extracted_values, dims=ds['time_stamp'].dims, coords=ds['time_stamp'].coords)
    ds['time_stamp'] = ds['time_stamp']*4
    node.results['ds_final'] = ds

# %%
if not simulate:
    grid_names = [q.grid_location for q in qubits]
    grid = QubitGrid(ds, grid_names)
    for ax, qubit in grid_iter(grid):
        ds.sel(qubit = qubit['qubit']).state.plot.hist(bins=3,ax=ax)
        ax.set_title(qubit['qubit'])
        ax.set_xlabel('State')
        ax.set_ylabel('Counts')
    grid.fig.suptitle('Histogram of qubit states')
    plt.tight_layout()
    plt.show()
    node.results['figure_bins'] = grid.fig

# %%
if not simulate:
    dat_fft = {}    

    for qubit in qubits:
        data_q = ds.state.sel(qubit = qubit.name)
        time_stamp_q = ds.time_stamp.sel(qubit = qubit.name).values
        
        f, Pxx_den = signal.welch(data_q-data_q.mean(),  1e9/np.mean(np.diff(time_stamp_q)), 
                          nperseg=8192*8)
        dat_fft[qubit.name] = xr.Dataset({'Pxx_den': (['freq'], Pxx_den)}, coords={'freq': f}).Pxx_den

        # dat_fft[qubit.name] = xrft.power_spectrum(data_q, real_dim='n')
        # dat_fft[qubit.name] = dat_fft[qubit.name].assign_coords(freq_n=1e9*dat_fft[qubit.name].freq_n/np.mean(np.diff(time_stamp_q)))
    
# %%    
if not simulate:
    grid_names = [q.grid_location for q in qubits]
    grid = QubitGrid(ds, grid_names, size = 5)
    for ax, qubit in grid_iter(grid):
        dat_fft[qubit['qubit']].plot(yscale='log', xscale='log', ax =ax)
        ax.grid(which='both')
        ax.set_xlabel('frequency [Hz]')
        ax.set_ylabel('power spectrum [arb.]')
        ax.set_title(qubit['qubit'])
    grid.fig.suptitle('Histogram of qubit states')
    plt.tight_layout()
    node.results['figure_fft'] = grid.fig


# %%
# %%
node.results['initial_parameters'] = node.parameters.model_dump()
node.machine = machine
node.save()
# %%
