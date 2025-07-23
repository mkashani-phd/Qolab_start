"""
RAMSEY WITH VIRTUAL Z ROTATIONS
The program consists in playing a Ramsey sequence (x90 - idle_time - x90 - measurement) for different idle times.
Instead of detuning the qubit gates, the frame of the second x90 pulse is rotated (de-phased) to mimic an accumulated
phase acquired for a given detuning after the idle time.
This method has the advantage of playing resonant gates.

From the results, one can fit the Ramsey oscillations and precisely measure the qubit resonance frequency and T2*.

Prerequisites:
    - Having found the resonance frequency of the resonator coupled to the qubit under study (resonator_spectroscopy).
    - Having calibrated qubit pi pulse (x180) by running qubit, spectroscopy, rabi_chevron, power_rabi and updated the state.
    - (optional) Having calibrated the readout (readout_frequency, amplitude, duration_optimization IQ_blobs) for better SNR.

Next steps before going to the next node:
    - Update the qubits frequency (f_01) in the state.
    - Save the current state by calling machine.save("quam")
"""


# %% {Imports}
from qualibrate import QualibrationNode, NodeParameters
from quam_libs.components import QuAM
from quam_libs.macros import qua_declaration, readout_state
from quam_libs.lib.qua_datasets import convert_IQ_to_V
from quam_libs.lib.plot_utils import QubitGrid, grid_iter
from quam_libs.lib.save_utils import fetch_results_as_xarray, load_dataset
from quam_libs.lib.fit import fit_oscillation_decay_exp, oscillation_decay_exp, decay_exp, fit_decay_exp
from qualang_tools.results import progress_counter, fetching_tool
from qualang_tools.loops import from_array
from qualang_tools.multi_user import qm_session
from qualang_tools.units import unit
from qm import SimulationConfig
from qm.qua import *
from typing import Literal, Optional, List
import matplotlib.pyplot as plt
import numpy as np


# %% {Node_parameters}
class Parameters(NodeParameters):
    qubits: Optional[List[str]] = None
    num_averages: int = 120
    frequency_detuning_in_mhz: float = 4.0
    min_wait_time_in_ns: int = 16
    max_wait_time_in_ns: int = 10000
    wait_time_step_in_ns: int = 10
    num_time_steps: int = 150
    flux_span: float = 0.1
    flux_step: float = 0.005
    flux_point_joint_or_independent: Literal["joint", "independent"] = "independent"
    simulate: bool = False
    simulation_duration_ns: int = 2500
    timeout: int = 100
    load_data_id: Optional[int] = None
    multiplexed: bool = False

node = QualibrationNode(name="08_Ramsey_vs_Flux_Calibration", parameters=Parameters())


# %% {Initialize_QuAM_and_QOP}
# Class containing tools to help handle units and conversions.
u = unit(coerce_to_integer=True)
# Instantiate the QuAM class from the state file
machine = QuAM.load()
# Generate the OPX and Octave configurations
config = machine.generate_config()
# Open Communication with the QOP
if node.parameters.load_data_id is None:
    qmm = machine.connect()

# Get the relevant QuAM components
if node.parameters.qubits is None or node.parameters.qubits == "":
    qubits = machine.active_qubits
else:
    qubits = [machine.qubits[q] for q in node.parameters.qubits]
num_qubits = len(qubits)


# %% {QUA_program}
n_avg = node.parameters.num_averages  # The number of averages

# Dephasing time sweep (in clock cycles = 4ns) - minimum is 4 clock cycles
idle_times = np.arange(
    node.parameters.min_wait_time_in_ns // 4,
    node.parameters.max_wait_time_in_ns // 4,
    node.parameters.wait_time_step_in_ns // 4,
)


idle_times = np.unique(
    np.geomspace(
        node.parameters.min_wait_time_in_ns, node.parameters.max_wait_time_in_ns, node.parameters.num_time_steps
    )
    // 4
).astype(int)

# Detuning converted into virtual Z-rotations to observe Ramsey oscillation and get the qubit frequency
detuning = int(1e6 * node.parameters.frequency_detuning_in_mhz)
flux_point = node.parameters.flux_point_joint_or_independent  # 'independent' or 'joint'
fluxes = np.arange(
    0, node.parameters.flux_span + 0.001, step=node.parameters.flux_step
)
quads = {qubit.name: int(qubit.freq_vs_flux_01_quad_term) for qubit in qubits}
freqs = {qubit.name: (fluxes**2 * qubit.freq_vs_flux_01_quad_term).astype(int) for qubit in qubits}


with program() as ramsey:
    I, I_st, Q, Q_st, _, n_st = qua_declaration(num_qubits=num_qubits)
    init_state = [declare(int) for _ in range(num_qubits)]
    state = [declare(int) for _ in range(num_qubits)]
    state_st = [declare_stream() for _ in range(num_qubits)]

    shots = [declare(int) for _ in range(num_qubits)]

    t = [declare(int) for _ in range(num_qubits)]  # QUA variable for the idle time
    phi = [declare(fixed) for _ in range(num_qubits)]  # QUA variable for dephasing the second pi/2 pulse (virtual Z-rotation)
    phi2 = [declare(fixed) for _ in range(num_qubits)]  # QUA variable for correcting the flux effect on the phase (virtual Z-rotation)
    freq = [declare(int) for _ in range(num_qubits)]  # QUA variable for the frequency
    flux = [declare(fixed) for _ in range(num_qubits)]  # QUA variable for the flux dc level
    flux_index = [declare(int) for _ in range(num_qubits)]  # QUA variable for the flux index
    fluxes_qua = declare(fixed, value=fluxes)
    
    if node.parameters.multiplexed:
        for i , qubit in enumerate(qubits):
            machine.set_all_fluxes(flux_point=flux_point, target=qubit)

    for i, qubit in enumerate(qubits):
        if not node.parameters.multiplexed:
            # Bring the active qubits to the desired frequency point
            machine.set_all_fluxes(flux_point=flux_point, target=qubit)

        with for_(shots[i], 0, shots[i] < n_avg, shots[i] + 1):
            save(shots[i], n_st)

            # with for_(*from_array(flux[i], fluxes)):
            with for_(flux_index[i], 0, flux_index[i] < len(fluxes), flux_index[i] + 1):
                assign(flux[i], fluxes_qua[flux_index[i]])
                with for_each_(t[i], idle_times):
                    # Read the state of the qubit before Ramsey starts
                    readout_state(qubit, init_state[i])
                    qubit.align()
                    # Rotate the frame of the second x90 gate to implement a virtual Z-rotation
                    # Echo sequence
                    qubit.xy.play("x90")
                    qubit.align()
                    qubit.z.play("const", amplitude_scale=flux[i] / qubit.z.operations["const"].amplitude, duration=t[i])
                    qubit.align()
                    qubit.xy.play("x180")
                    qubit.align()
                    qubit.z.play("const", amplitude_scale=flux[i] / qubit.z.operations["const"].amplitude, duration=t[i])
                    qubit.align()                    
                    qubit.xy.play("x90")
                    qubit.xy.play("x180")
                    # Align the elements to measure after playing the qubit pulse.
                    align()
                    # Measure the state of the resonators
                    readout_state(qubit, state[i])
                    assign(state[i], init_state[i] ^ state[i])
                    save(state[i], state_st[i])

                    # Reset the frame of the qubits in order not to accumulate rotations
                    reset_frame(qubit.xy.name)
                    qubit.align()

        if not node.parameters.multiplexed:
            align()

    with stream_processing():
        n_st.save("n")
        for i in range(num_qubits):
            state_st[i].buffer(len(idle_times)).buffer(len(fluxes)).average().save(f"state{i + 1}")


# %% {Simulate_or_execute}
if node.parameters.simulate:
    # Simulates the QUA program for the specified duration
    simulation_config = SimulationConfig(duration=node.parameters.simulation_duration_ns * 4)  # In clock cycles = 4ns
    job = qmm.simulate(config, ramsey, simulation_config)
    # Get the simulated samples and plot them for all controllers
    samples = job.get_simulated_samples()
    fig, ax = plt.subplots(nrows=len(samples.keys()), sharex=True)
    for i, con in enumerate(samples.keys()):
        plt.subplot(len(samples.keys()), 1, i + 1)
        samples[con].plot()
        plt.title(con)
    plt.tight_layout()
    # Save the figure
    node.results = {"figure": plt.gcf()}
    node.machine = machine
    node.save()

elif node.parameters.load_data_id is None:
    with qm_session(qmm, config, timeout=node.parameters.timeout) as qm:
        job = qm.execute(ramsey)
        results = fetching_tool(job, ["n"], mode="live")
        while results.is_processing():
            # Fetch results
            n = results.fetch_all()[0]
            # Progress bar
            progress_counter(n, n_avg, start_time=results.start_time)

# %% {Data_fetching_and_dataset_creation}
if not node.parameters.simulate:
    if node.parameters.load_data_id is None:
        ds = fetch_results_as_xarray(job.result_handles, qubits, {"idle_time": idle_times, "flux": fluxes})
        # Add the absolute time in µs to the dataset
        ds = ds.assign_coords(idle_time=8 * ds.idle_time / 1e3)
        ds.flux.attrs = {"long_name": "flux", "units": "V"}
        ds.idle_time.attrs = {"long_name": "idle time", "units": "µs"}
    else:
        node = node.load_from_id(node.parameters.load_data_id)
        ds = node.results["ds"]
    # Add the dataset to the node
    node.results = {"ds": ds}

# %% {Data_analysis}

# %%

if not node.parameters.simulate:
    ds.flux.attrs = {'long_name': 'flux', 'units': 'V'}
    ds.idle_time.attrs = {'long_name': 'idle time', 'units': 'usec'}
    
    def detuning(q, flux):
        return -1e-6 * q.freq_vs_flux_01_quad_term * flux**2

    ds = ds.assign_coords(
        {"detuning": (["qubit", "flux"], np.array([detuning(q, fluxes) for q in qubits]))}
    )
    ds.detuning.attrs["long_name"] = "Detuning"
    ds.detuning.attrs["units"] = "MHz"

    def df_dphi(q, flux):
        return -1e-9 * 2 * q.freq_vs_flux_01_quad_term * flux * q.phi0_voltage * 2 * np.pi

    ds = ds.assign_coords(
        {"df_dphi": (["qubit", "flux"], np.array([df_dphi(q, fluxes) for q in qubits]))}
    )
    ds.detuning.attrs["long_name"] = "df_dphi"
    ds.detuning.attrs["units"] = "GHz/V"
    

# %%

import xarray as xr
if not node.parameters.simulate:
    fit_data = fit_decay_exp(ds.state, 'idle_time')
    fit_data.attrs = {'long_name' : 'time', 'units' : 'usec'}
    fitted =  decay_exp(ds.state.idle_time,
                                                    fit_data.sel(
                                                        fit_vals="a"),
                                                    fit_data.sel(
                                                        fit_vals="offset"),
                                                    fit_data.sel(fit_vals="decay"))


    decay = -fit_data.sel(fit_vals = 'decay',drop = True)
    decay.attrs = {'long_name' : 'decay', 'units' : 'nSec'}

    decay_error = np.sqrt(fit_data.sel(fit_vals = 'decay_decay',drop = True))
    decay_error.attrs = {'long_name' : 'decay', 'units' : 'nSec'}
    
    tau = 1/fit_data.sel(fit_vals='decay',drop = True)
    tau.attrs = {'long_name' : 'T2*', 'units' : 'uSec'}

    tau_error = -tau * (decay_error/decay)
    tau_error.attrs = {'long_name' : 'T2* error', 'units' : 'uSec'}

    # Combine fitted data arrays into a dataset
    fit_dataset = xr.Dataset({
        'decay': decay,
        'decay_error': decay_error,
        'T2_star': tau,
        'T2_star_error': tau_error
    })
    # Linear fit of decay vs df_dphi for all qubits using scipy's curve_fit
    from scipy.optimize import curve_fit

    def linear_model(x, m, b):
        return m * x + b

    slopes = []
    intercepts = []
    slope_errors = []
    intercept_errors = []
    all_residuals = []

    for qubit in fit_dataset.qubit:
        x = fit_dataset.df_dphi.sel(qubit=qubit).values[3:-3]
        y = fit_dataset.decay.sel(qubit=qubit).values[3:-3]
        y_err = fit_dataset.decay_error.sel(qubit=qubit).values[3:-3]

        # Perform weighted curve fit
        popt, pcov = curve_fit(linear_model, x, y, sigma=y_err, absolute_sigma=True)
        slope, intercept = popt
        slope_err, intercept_err = np.sqrt(np.diag(pcov))

        x = fit_dataset.df_dphi.sel(qubit=qubit).values
        y = fit_dataset.decay.sel(qubit=qubit).values
        y_err = fit_dataset.decay_error.sel(qubit=qubit).values

        # Calculate fitted y values and residuals
        y_fit = linear_model(x, slope, intercept)
        residuals = y - y_fit

        slopes.append(slope)
        intercepts.append(intercept)
        slope_errors.append(slope_err)
        intercept_errors.append(intercept_err)
        all_residuals.append(residuals)

    # Add linear fit results to fit_dataset
    fit_dataset['decay_vs_df_dphi_slope'] = xr.DataArray(slopes, dims=['qubit'], attrs={'long_name': 'Slope of decay vs df/dphi', 'units': 'MHz/(GHz/V)'})
    fit_dataset['decay_vs_df_dphi_slope_error'] = xr.DataArray(slope_errors, dims=['qubit'], attrs={'long_name': 'Error in slope of decay vs df/dphi', 'units': 'MHz/(GHz/V)'})
    fit_dataset['decay_vs_df_dphi_intercept'] = xr.DataArray(intercepts, dims=['qubit'], attrs={'long_name': 'Intercept of decay vs df/dphi', 'units': 'MHz'})
    fit_dataset['decay_vs_df_dphi_intercept_error'] = xr.DataArray(intercept_errors, dims=['qubit'], attrs={'long_name': 'Error in intercept of decay vs df/dphi', 'units': 'MHz'})
    fit_dataset['decay_vs_df_dphi_residuals'] = xr.DataArray(all_residuals, dims=['qubit', 'flux'], attrs={'long_name': 'Residuals of decay vs df/dphi fit', 'units': 'MHz'})

    # Add the fit dataset to the node results
    node.results['fit_dataset'] = fit_dataset


# %%
if not node.parameters.simulate:
    grid_names = [q.grid_location for q in qubits]
    grid = QubitGrid(ds, grid_names)
    for ax, qubit in grid_iter(grid):
        ds.sel(qubit = qubit['qubit']).state.plot(ax = ax)
        ax.set_title(qubit['qubit'])
        ax.set_xlabel('Idle_time (uS)')
        ax.set_ylabel(' Flux (V)')
    grid.fig.suptitle('Ramsey freq. Vs. flux')
    plt.tight_layout()
    plt.show()
    node.results['figure_raw'] = grid.fig

    grid_names = [q.grid_location for q in qubits]
    grid = QubitGrid(ds, grid_names)
    for ax, qubit in grid_iter(grid):
        tau_data = -tau.sel(qubit = qubit['qubit'])
        flux_data = tau_data.flux
        ax.errorbar(flux_data, tau_data, 
                    yerr=tau_error.sel(qubit = qubit['qubit']), 
                    fmt='o-', capsize=5)
        ax.set_yscale('log')
        ax.set_title(qubit['qubit'])
        ax.set_ylabel('T2* (uS)')
        ax.set_xlabel(' Flux (V)')
        ax.set_ylim(0, 25)
    grid.fig.suptitle('T2*. Vs. flux')
    plt.tight_layout()
    plt.show()
    node.results['figure_t2'] = grid.fig

    grid_names = [q.grid_location for q in qubits]
    grid = QubitGrid(ds, grid_names)
    for ax, qubit in grid_iter(grid):
        tau_data = fit_dataset.decay.sel(qubit = qubit['qubit'])
        flux_data = tau_data.flux
        ax.errorbar(fit_dataset.df_dphi.sel(qubit = qubit['qubit']), fit_dataset.decay.sel(qubit = qubit['qubit']), 
                    yerr=fit_dataset.decay_error.sel(qubit = qubit['qubit']), 
                    fmt='o-', capsize=5)
        ax.plot(fit_dataset.df_dphi.sel(qubit = qubit['qubit']), fit_dataset.decay_vs_df_dphi_slope.sel(qubit = qubit['qubit']) * fit_dataset.df_dphi.sel(qubit = qubit['qubit']) + fit_dataset.decay_vs_df_dphi_intercept.sel(qubit = qubit['qubit']), 'r--')
        ax.text(0.05, 0.95, f"$\kappa_R$: {1e3*fit_dataset.decay_vs_df_dphi_slope.sel(qubit = qubit['qubit']):.0f} $\pm$ {1e3*fit_dataset.decay_vs_df_dphi_slope_error.sel(qubit = qubit['qubit']):.0f} $\mu \phi_0$", transform=ax.transAxes, fontsize=10, verticalalignment='top')
        ax.set_title(qubit['qubit'])
        ax.set_ylabel('$\Gamma_R$ (MHz)')
        ax.set_xlabel("$(2\pi)^{-1}$ $df/d\phi$ (GHz/$\phi_0$)")
        
        
        slope = 1e-3*fit_dataset.decay_vs_df_dphi_slope.sel(qubit = qubit['qubit'])
        print(f"{qubit['qubit']}: slope = {slope:.6f} MHz/(GHz/V)")
        A_phi = (slope / (2 * np.pi) )**2 / np.log(2 )
        print(f"{qubit['qubit']}: A_phi = {1e6*np.sqrt(A_phi):.6f} $\mu \phi_0$")
        ax.text(0.05, 0.75, "$\sqrt{A_{\phi}}$" + f": {1e6*np.sqrt(A_phi):.1f} $\mu \phi_0$", transform=ax.transAxes, fontsize=10, verticalalignment='top')

        
        # Add extra coordinates to the ax axis representing detuning
        detuning_data = fit_dataset.detuning.sel(qubit=qubit['qubit'])
        df_dphi_data = fit_dataset.df_dphi.sel(qubit=qubit['qubit'])
        
        def detuning_to_df_dphi(det):
            return np.interp(det, detuning_data, df_dphi_data)
        
        def df_dphi_to_detuning(dfp):
            return np.interp(dfp, df_dphi_data, detuning_data)
        
        ax2 = ax.secondary_xaxis('top', functions=(df_dphi_to_detuning, detuning_to_df_dphi))
        ax2.set_xlabel("Detuning (MHz)")

        # ax.set_ylim(0, 4)
    grid.fig.suptitle('T2*. Vs. flux')
    plt.tight_layout()
    plt.show()
    node.results['figure_decay'] = grid.fig

    # %% {Update_state}
    if node.parameters.load_data_id is None:

        
        node.outcomes = {q.name: "successful" for q in qubits}
        node.results["initial_parameters"] = node.parameters.model_dump()
        node.machine = machine
        node.save()

# %%
# for q in qubits:
#     slope = 1e-3*fit_dataset.decay_vs_df_dphi_slope.sel(qubit = q.name)
#     print(f"{q.name}: slope = {slope:.6f} MHz/(GHz/V)")
#     A_phi = (slope / (2 * np.pi) )**2 / np.abs(np.log(2 * np.pi * 1 * 1.5e-6))
#     print(f"{q.name}: A_phi = {1e6*np.sqrt(A_phi):.6f} $\mu \phi_0$")

# # %%
