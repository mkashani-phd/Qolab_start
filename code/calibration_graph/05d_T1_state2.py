"""
        T1 MEASUREMENT
The sequence consists in putting the qubit in the excited stated by playing the x180 pulse and measuring the resonator
after a varying time. The qubit T1 is extracted by fitting the exponential decay of the measured quadratures.

Prerequisites:
    - Having found the resonance frequency of the resonator coupled to the qubit under study (resonator_spectroscopy).
    - Having calibrated qubit pi pulse (x180) by running qubit spectroscopy, power_rabi and updated the state.
    - (optional) Having calibrated the readout (readout_frequency, amplitude, duration_optimization IQ_blobs) for better SNR.
    - Set the desired flux bias.

Next steps before going to the next node:
    - Update the qubit T1 in the state.
"""

# %% {Imports}
from qualibrate import QualibrationNode, NodeParameters
from quam_libs.components import QuAM
from quam_libs.macros import qua_declaration, active_reset
from quam_libs.lib.qua_datasets import convert_IQ_to_V
from quam_libs.lib.plot_utils import QubitGrid, grid_iter
from quam_libs.lib.save_utils import fetch_results_as_xarray, load_dataset
from quam_libs.lib.fit import decay_exp
from qualang_tools.results import progress_counter, fetching_tool
from qualang_tools.loops import from_array
from qualang_tools.multi_user import qm_session
from qualang_tools.units import unit
from qm import SimulationConfig
from qm.qua import *
from typing import Literal, Optional, List
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from quam_libs.components.qutrit import classify_batch, classify_iq
from scipy.optimize import curve_fit

# %% {Node_parameters}
class Parameters(NodeParameters):
    qubits: Optional[List[str]] = None
    num_averages: int = 1000
    min_wait_time_in_ns: int = 16
    max_wait_time_in_ns: int = 400000
    wait_time_step_in_ns: int = 5000
    flux_point_joint_or_independent_or_arbitrary: Literal["joint", "independent", "arbitrary"] = "independent"
    reset_type: Literal["active", "thermal"] = "active"
    postselect_on_initial_state2: bool = True
    simulate: bool = False
    simulation_duration_ns: int = 2500
    timeout: int = 100
    load_data_id: Optional[int] = None
    multiplexed: bool = False
    fit_skip_initial_points: int = 0
    fit_observable: Literal["I", "Q", "amp", "p2", "state"] = "amp"  # amp = magnitude (I and Q), p2 = P(|2> | not |0>), state = average state index (0-2 or 1-2 if postselected).

description = """Typical Runtime w/Default Params:
60-75s for all qubits
30-40s per qubit
"""

node = QualibrationNode(name="05d_T1_state2", description=description, parameters=Parameters())

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

flux_point = node.parameters.flux_point_joint_or_independent_or_arbitrary  # 'independent' or 'joint'
if flux_point == "arbitrary":
    detunings = {q.name: q.arbitrary_intermediate_frequency for q in qubits}
    arb_flux_bias_offset = {q.name: q.z.arbitrary_offset for q in qubits}
else:
    arb_flux_bias_offset = {q.name: 0.0 for q in qubits}
    detunings = {q.name: 0.0 for q in qubits}

with program() as t1:
    I, I_st, Q, Q_st, n, n_st = qua_declaration(num_qubits=num_qubits)

    shot = [declare(int) for _ in range(num_qubits)]
    t = [declare(int) for _ in range(num_qubits)]

    if node.parameters.multiplexed:
        for i , qubit in enumerate(qubits):
            machine.set_all_fluxes(flux_point=flux_point, target=qubit)

    for i, qubit in enumerate(qubits):

        if not node.parameters.multiplexed:
            # Bring the active qubits to the desired frequency point
            machine.set_all_fluxes(flux_point=flux_point, target=qubit)

        with for_(shot[i], 0, shot[i] < n_avg, shot[i] + 1):
            save(shot[i], n_st)

            with for_(*from_array(t[i], idle_times)):
                if node.parameters.reset_type == "active":
                    active_reset(qubit, "readout")
                else:
                    qubit.resonator.wait(qubit.thermalization_time * u.ns)
                    qubit.align()

                qubit.xy.play("x180")
                qubit.align()

                qubit.xy.update_frequency(qubit.xy.intermediate_frequency - qubit.anharmonicity)
                align(qubit.xy.name, qubit.resonator.name)
                qubit.xy.play("EF_x180")
                qubit.align()
                qubit.xy.update_frequency(qubit.xy.intermediate_frequency)
                align(qubit.xy.name, qubit.resonator.name)

                # Extra x180 for post-selection: ideally does nothing to |2>, maps misprepared |1> ↔ |0>
                if node.parameters.postselect_on_initial_state2:
                    qubit.xy.play("x180")
                    qubit.align()
                 
                qubit.z.wait(20)
                qubit.z.play(
                    "const",
                    amplitude_scale=arb_flux_bias_offset[qubit.name] / qubit.z.operations["const"].amplitude,
                    duration=t[i],
                )
                qubit.z.wait(20)
                qubit.align()

                # Measure the state of the resonators (analog IQ)
                qubit.resonator.measure("readout", qua_vars=(I[i], Q[i]))
                # save data
                save(I[i], I_st[i])
                save(Q[i], Q_st[i])
        # Measure sequentially
        if not node.parameters.multiplexed:
            align()

    with stream_processing():
        n_st.save("n")
        for i in range(num_qubits):
            # Buffer over idle_time (inner loop), then over shot (outer loop) to keep per-shot IQ
            I_st[i].buffer(len(idle_times)).buffer(n_avg).save(f"I{i + 1}")
            Q_st[i].buffer(len(idle_times)).buffer(n_avg).save(f"Q{i + 1}")


# %% {Simulate_or_execute}
if node.parameters.simulate:
    # Simulates the QUA program for the specified duration
    simulation_config = SimulationConfig(duration=node.parameters.simulation_duration_ns * 4)  # In clock cycles = 4ns
    job = qmm.simulate(config, t1, simulation_config)
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
        job = qm.execute(t1)
        results = fetching_tool(job, ["n"], mode="live")
        while results.is_processing():
            # Fetch results
            n = results.fetch_all()[0]
            # Progress bar
            progress_counter(n, n_avg, start_time=results.start_time)

def fit_decay_exp(da, dim):
    """
    Local exponential decay fit used only in this node.

    Fits y(x) ≈ a * exp(decay * x) + offset along the specified dimension.
    Returns an xarray DataArray with a 'fit_vals' axis containing:
    [a, offset, decay, a_a, a_offset, a_decay, offset_a, offset_offset,
     offset_decay, decay_a, decay_offset, decay_decay],
    where the last 9 entries are the flattened 3x3 covariance matrix from curve_fit.
    """

    def apply_fit(x, y):
        # Ensure 1D numpy arrays
        x = np.asarray(x)
        y = np.asarray(y)

        # Mask NaNs (from postselection or other issues)
        mask = ~np.isnan(y)
        x_valid = x[mask]
        y_valid = y[mask]

        # Need at least 3 valid points to attempt a fit
        if x_valid.size < 3:
            return np.full(12, np.nan, dtype=float)

        # Initial guesses
        y_min = np.min(y_valid)
        y_max = np.max(y_valid)
        amp0 = (y_max - y_min) / 2.0
        offset0 = y_min
        if amp0 <= 0:
            amp0 = 1.0

        # Crude decay guess based on first and last valid points
        eps = 1e-12
        y0 = y_valid[0]
        y1 = y_valid[-1]
        dt = x_valid[-1] - x_valid[0] if x_valid[-1] != x_valid[0] else 1.0
        if (y0 - offset0) <= eps or (y1 - offset0) <= eps or (y0 - offset0) * (y1 - offset0) <= 0:
            decay0 = -1.0 / dt
        else:
            ratio = (y1 - offset0) / (y0 - offset0)
            if ratio <= 0:
                decay0 = -1.0 / dt
            else:
                decay0 = np.log(ratio) / dt

        try:
            popt, pcov = curve_fit(decay_exp, x_valid, y_valid, p0=[amp0, offset0, decay0])
            # Flatten covariance; expect 3x3, otherwise fill with NaNs
            if pcov.shape == (3, 3):
                cov_flat = pcov.reshape(-1)
            else:
                cov_flat = np.full(9, np.nan, dtype=float)
            return np.concatenate([popt, cov_flat])
        except Exception as e:
            # On fit failure, print some debug info and return NaNs for all fit parameters
            print("Fit failed in local fit_decay_exp.apply_fit:")
            print(f"Error: {e}")
            print(f"p0 = {[amp0, offset0, decay0]}")
            return np.full(12, np.nan, dtype=float)

    # Vectorize over any non-'dim' dimensions (e.g. qubit) using apply_ufunc
    fit_res = xr.apply_ufunc(
        apply_fit,
        da[dim],
        da,
        input_core_dims=[[dim], [dim]],
        output_core_dims=[["fit_vals"]],
        vectorize=True,
    )

    return fit_res.assign_coords(
        fit_vals=(
            "fit_vals",
            [
                "a",
                "offset",
                "decay",
                "a_a",
                "a_offset",
                "a_decay",
                "offset_a",
                "offset_offset",
                "offset_decay",
                "decay_a",
                "decay_offset",
                "decay_decay",
            ],
        )
    )

# %% {Data_fetching_and_dataset_creation}
if not node.parameters.simulate:
    if node.parameters.load_data_id is None:
        # Fetch the data from the OPX and convert it into a xarray with corresponding axes (from most inner to outer loop)
        axes = {"idle_time": idle_times, "shot": np.arange(n_avg)}
        ds = fetch_results_as_xarray(job.result_handles, qubits, axes)
        # Convert IQ data into volts
        ds = convert_IQ_to_V(ds, qubits)
        # Convert time into µs
        ds = ds.assign_coords(idle_time=4 * ds.idle_time / u.us)  # convert to µs
        ds.idle_time.attrs = {"long_name": "idle time", "units": "µs"}
    else:
        node = node.load_from_id(node.parameters.load_data_id)
        ds = node.results["ds"]
    # Add the dataset to the node
    node.results = {"ds": ds}

    # Optional classification / post-selection:
    #  - If postselect_on_initial_state2 is True, drop shots classified as |0⟩.
    #  - If fit_observable in {"p2", "state"}, compute state-based observables for use in the fit.
    if node.parameters.postselect_on_initial_state2 or node.parameters.fit_observable in ("p2", "state"):
        if "shot" not in ds.dims:
            raise ValueError(
                "State classification requires a 'shot' dimension in the dataset."
            )
        if len(qubits) != 1:
            raise ValueError(
                "State classification / postselection currently supports only a single qubit."
            )

        q = qubits[0]
        dsi = ds.sel(qubit=q.name)
        I_vals = dsi.I.values  # shape: (idle_time, shot) or (shot, idle_time)
        Q_vals = dsi.Q.values  # same shape as I_vals

        # Stack IQ for all idle_times and shots, classify, then reshape
        iq = np.stack([I_vals, Q_vals], axis=-1)  # shape: (*idle_time, *shot, 2)
        iq_flat = iq.reshape(-1, 2)               # shape: (idle_time * shot, 2)

        W = q.resonator.matched_filter_W
        C = q.resonator.matched_filter_C

        # Classify all points and reshape back to the I-shape
        states_flat = classify_batch(iq_flat, {"W": W, "C": C})
        states = states_flat.reshape(I_vals.shape)

        # Wrap states in a DataArray aligned with I/Q for convenience
        states_da = xr.DataArray(states, coords=dsi.I.coords, dims=dsi.I.dims)

        # Build conditional probability P(|2⟩ | not |0⟩) vs idle_time from the raw states
        excited_mask = states_da != 0
        count_excited = excited_mask.sum(dim="shot")
        count_2 = (states_da == 2).sum(dim="shot")
        p2_da = (count_2 / count_excited).where(count_excited > 0)

        # Build an average "state index" observable:
        #  - If postselect_on_initial_state2 is True: average over excited manifold only (1 and 2), ranges ~[1,2].
        #  - Else: unconditional average over {0,1,2}, ranges ~[0,2].
        if node.parameters.postselect_on_initial_state2:
            count_1 = (states_da == 1).sum(dim="shot")
            state_exc = (1.0 * count_1 + 2.0 * count_2) / count_excited.where(count_excited > 0)
            state_da = state_exc
        else:
            state_da = states_da.mean(dim="shot")

        # Attach P(|2⟩ | not |0⟩) and average state index to the dataset for later use in analysis/plotting.
        ds = ds.assign(p2=p2_da, state_index=state_da)

        # If requested, use the classification to drop shots classified as |0⟩
        if node.parameters.postselect_on_initial_state2:
            # Keep shots that are not classified as |0⟩
            good_mask = states != 0  # True for states 1 or 2

            # Turn mask into an xarray DataArray aligned with the I-data layout
            # (dims may be ("shot", "idle_time") or ("idle_time", "shot"), so use dsi.I.dims/coords)
            good_mask_da = xr.DataArray(
                good_mask,
                coords=dsi.I.coords,
                dims=dsi.I.dims,
            )

            # Apply mask elementwise; invalid points become NaN and will be ignored in averaging
            ds = ds.where(good_mask_da)
        
    # %% {Data_analysis}
    # Optionally drop initial points from the fit to mitigate mis-preparation / settling
    skip = node.parameters.fit_skip_initial_points
    if skip > 0:
        ds_fit = ds.isel(idle_time=slice(skip, None))
    else:
        ds_fit = ds

    # For fitting, average over shots if present (ignore NaNs from post-selection)
    if "shot" in ds_fit.dims:
        ds_fit_mean = ds_fit.mean(dim="shot", skipna=True)
    else:
        ds_fit_mean = ds_fit

    # Choose observable for fitting based on parameter
    if node.parameters.fit_observable == "I":
        y_for_fit = ds_fit_mean.I
        fit_ylabel = "I (V)"
    elif node.parameters.fit_observable == "Q":
        y_for_fit = ds_fit_mean.Q
        fit_ylabel = "Q (V)"
    elif node.parameters.fit_observable == "amp":
        # Amplitude from I and Q
        y_for_fit = np.sqrt(ds_fit_mean.I**2 + ds_fit_mean.Q**2)
        fit_ylabel = "Amplitude (V)"
    elif node.parameters.fit_observable == "p2":
        if "p2" not in ds_fit_mean:
            raise ValueError(
                "fit_observable='p2' requires state classification, "
                "which is triggered by postselect_on_initial_state2=True or fit_observable in {'p2','state'}."
            )
        y_for_fit = ds_fit_mean["p2"]
        fit_ylabel = "P(|2⟩ | not |0⟩)"
    elif node.parameters.fit_observable == "state":
        if "state_index" not in ds_fit_mean:
            raise ValueError(
                "fit_observable='state' requires state classification, "
                "which is triggered by postselect_on_initial_state2=True or fit_observable in {'p2','state'}."
            )
        y_for_fit = ds_fit_mean["state_index"]
        fit_ylabel = "⟨state index⟩"
    else:
        raise ValueError(f"Unknown fit_observable: {node.parameters.fit_observable}")

    # Guard against the case where all points were removed by postselection,
    # which would cause the fitter to receive an all-NaN array.
    if np.isnan(y_for_fit.values).all():
        raise ValueError(
            "All values of the chosen fit observable are NaN after postselection/averaging. "
            "This usually means the classifier labeled every shot as state |0>. "
            "Try disabling 'postselect_on_initial_state2' or check the qutrit classifier parameters."
        )
    # has_columns_that_are_all_nans = np.any([not np.any(good_mask_da[:,s]) for s in range(0,good_mask_da.shape[1])])  # todo: skip time delays that were all |0> states

    # Fit the exponential decay on the chosen observable
    fit_data = fit_decay_exp(y_for_fit, "idle_time")
    fit_data.attrs = {"long_name": "time", "units": "µs"}

    # Fitted decay
    fitted = decay_exp(
        ds.idle_time,
        fit_data.sel(fit_vals="a"),
        fit_data.sel(fit_vals="offset"),
        fit_data.sel(fit_vals="decay"),
    )
    # Decay rate and its uncertainty
    decay = fit_data.sel(fit_vals="decay")
    decay.attrs = {"long_name": "decay", "units": "ns"}
    decay_res = fit_data.sel(fit_vals="decay_decay")
    decay_res.attrs = {"long_name": "decay", "units": "ns"}
    # T1 and its uncertainty
    tau = -1 / fit_data.sel(fit_vals="decay")
    tau.attrs = {"long_name": "T1", "units": "µs"}
    tau_error = -tau * (np.sqrt(decay_res) / decay)
    tau_error.attrs = {"long_name": "T1 error", "units": "µs"}

    # %% {Plotting}
    # For plotting, use the shot-averaged dataset if available (ignore NaNs from post-selection)
    if "shot" in ds.dims:
        ds_plot = ds.mean(dim="shot", skipna=True)
    else:
        ds_plot = ds

    grid = QubitGrid(ds_plot, [q.grid_location for q in qubits])
    for ax, qubit in grid_iter(grid):
        ds_q = ds_plot.sel(qubit=qubit["qubit"])
        if node.parameters.fit_observable == "I":
            y_plot = ds_q.I
            ylabel = "I (V)"
        elif node.parameters.fit_observable == "Q":
            y_plot = ds_q.Q
            ylabel = "Q (V)"
        elif node.parameters.fit_observable == "amp":
            y_plot = np.sqrt(ds_q.I**2 + ds_q.Q**2)
            ylabel = "Amplitude (V)"
        elif node.parameters.fit_observable == "p2":
            if "p2" not in ds_q:
                raise ValueError(
                    "fit_observable='p2' selected, but 'p2' variable is missing from the dataset."
                )
            y_plot = ds_q.p2
            ylabel = "P(|2⟩ | not |0⟩)"
        elif node.parameters.fit_observable == "state":
            if "state_index" not in ds_q:
                raise ValueError(
                    "fit_observable='state' selected, but 'state_index' variable is missing from the dataset."
                )
            y_plot = ds_q.state_index
            ylabel = "⟨state index⟩"
        else:
            y_plot = ds_q.I
            ylabel = "I (V)"

        # Plot the chosen observable
        y_plot.plot(ax=ax)
        ax.set_ylabel(ylabel)

        # Select the fitted curve; handle both with and without a 'qubit' dimension
        if "qubit" in fitted.dims:
            fit_curve = fitted.sel(qubit=qubit["qubit"])
        else:
            fit_curve = fitted

        ax.plot(ds.idle_time, fit_curve, "r--")
        ax.set_title(qubit["qubit"])
        ax.set_xlabel("Idle_time ($\\mu$s)")

        # Extract scalar T1 and error; handle both single-qubit (no 'qubit' dim) and multi-qubit cases.
        if "qubit" in tau.dims:
            tau_val = float(tau.sel(qubit=qubit["qubit"]).values)
            tau_err_val = float(tau_error.sel(qubit=qubit["qubit"]).values)
        else:
            tau_val = float(tau.values)
            tau_err_val = float(tau_error.values)

        ax.text(
            0.1,
            0.9,
            f"T1 = {tau_val:.1f} ± {tau_err_val:.1f} µs",
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            bbox=dict(facecolor="white", alpha=0.5),
        )
    grid.fig.suptitle("T1 of $\\left | 2 \\right \\rangle$")
    plt.tight_layout()
    plt.show()
    node.results["figure_raw"] = grid.fig

    # %% {Update_state}
    if node.parameters.load_data_id is None:
        with node.record_state_updates():
            for index, q in enumerate(qubits):
                # Extract scalar T1 and error for this qubit; handle both single-qubit
                # (no 'qubit' dim) and multi-qubit fits.
                if "qubit" in tau.dims:
                    tau_val = float(tau.sel(qubit=q.name).values)
                    tau_err_val = float(tau_error.sel(qubit=q.name).values)
                else:
                    tau_val = float(tau.values)
                    tau_err_val = float(tau_error.values)

                if tau_val > 0 and (tau_err_val / tau_val) < 1:
                    q.T1_state2 = tau_val * 1e-6

        # %% {Save_results}
        node.results["initial_parameters"] = node.parameters.model_dump()
        node.machine = machine
        node.save()
