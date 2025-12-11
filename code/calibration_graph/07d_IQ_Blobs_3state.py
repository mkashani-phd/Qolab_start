"""
        IQ BLOBS
This sequence involves measuring the state of the resonator 'N' times, first after thermalization (with the qubit
in the |g> state) and then after applying a pi pulse to the qubit (bringing the qubit to the |e> state) successively.
The resulting IQ blobs are displayed, and the data is processed to determine:
    - The rotation angle required for the integration weights, ensuring that the separation between |g> and |e> states
      aligns with the 'I' quadrature.
    - The threshold along the 'I' quadrature for effective qubit state discrimination.
    - The readout fidelity matrix, which is also influenced by the pi pulse fidelity.

Prerequisites:
    - Having found the resonance frequency of the resonator coupled to the qubit under study (resonator_spectroscopy).
    - Having calibrated qubit pi pulse (x180) by running qubit.wait(qubit.thermalization_time * u.ns) spectroscopy, power_rabi and updated the state.
    - Set the desired flux bias
    - Run 02a_Resonator_Spectroscopy and update the readout frequency accordingly. This will yield a new frequency that is 
      approximately 700 KHz below the default-calibrated value (which comes from running 02b_Resonator_Spectroscopy_vs_Flux).
      The lower readout frequency makes leakage "visible" in readout; higher states result in larger shifts of the resonator 
      resonance, and you want your shifted resonator resonance to have a decent slope where it intersects your chosen readout
      frequency, for all qubit states of interest.
    - Use 03c_Qubit_ef_Spectroscopy to identify the EF transition frequency (if necessary, edit your qubit's "anharmonicity" 
      in state.json to modify the search location). Update "anharmonicity" parameter for your qubit(s) accordingly.
      (This node will also initialize EF_x180 amplitude to a reasonable value).
      You should see a peak at the anharmonicity (approximately 300 MHz below the qubit frequency) to check that
      readout frequency setting is good. It won't be a sharp peak but it should be clear that there is one.
      Go back and adjust your resonator frequency if you are not getting an unambiguous peak, or try adjusting the anharmonicity
      (it should be set to ~300 MHz by default).
      Note that the readout frequency calibrated by 02a_Resonator_Spectroscopy is best for identifying the anharmonicity.
      We will adjust the readout frequency again below -- but after that adjustment you may not be able to see the
      EF transition in spectroscopy anymore!
    - Run 02b_Resonator_Spectroscopy_vs_Flux to obtain a second calibration value for the resonator frequency. 
    - Edit your state.json file to set the readout frequency for your qubit to the *average* of the two calibration values
      (the first from 02a and the second from 02b). This will give a good separation between |0> |1> and |2> without seeing 
      additional leakage to higher states (unless you want to see that, in which case you should just use the value from 02a).
      02b gives a very nice separation between |0> and |1> but |2> is not visible; 02a gives visibility of all 3 states 
      (and more) but the separation between |0> and |1> is much poorer. The average seems to be a good compromise.
    - Use 04_Power_Rabi_ef to tune up your EF_x180 gate, making it possible to prepare the |2> state via |1>.
      The range of amplitudes depends on the previous "amplitude" setting for EF_x180 gate so you may want to 
      edit that value in state.json first, and/or you can adjust Max Amp Factor and Amp Factor Step in until
      you can see 1.5-2 Rabi oscillations for a good fit.
      If you have trouble tuning up the EF_x180 gate you can still proceed, but you should use the settings 
      ef_operation="saturation", ef_op_amplitude=0.8 and enable_x180_pre=True
      and set your qubit's anharmonicity=150MHz (location of 2-photon GF transition) in state.json. Then you will still see
      some population in the |2> state when you run 07d_IQ_Blobs_3state.
    - Run 07b_IQ_Blobs to re-calibrate |0> and |1> state detection at the new readout frequency. This 
      is necessary in order for active state preparation to work properly. Make sure to use "thermal" reset.
    - Now you are ready to run 07d_IQ_Blobs_3state (this node).

Next steps before going to the next node:
    - Save the 3-level state discrimination parameters and 3x3 confusion matrix. Other nodes can then use
      classify_iq() and/or classify_batch() to perform 3-level state detection for new I,Q shots,
      by passing in those saved calibration parameters.
"""
# %%
from typing import List, Literal, Optional

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from qm import SimulationConfig
from qm.qua import *
from qualang_tools.analysis.discriminator import two_state_discriminator
from qualang_tools.multi_user import qm_session
from qualang_tools.results import fetching_tool, progress_counter
from qualang_tools.units import unit

# %% {Imports}
from qualibrate import NodeParameters, QualibrationNode
from quam_libs.components import QuAM
from quam_libs.lib.plot_utils import QubitGrid, grid_iter
from quam_libs.lib.qua_datasets import convert_IQ_to_V
from quam_libs.lib.save_utils import fetch_results_as_xarray, load_dataset
from quam_libs.macros import active_reset, qua_declaration

# Making a fake Quam class so it will let me store paramters in state.json
from quam.core import quam_dataclass
from quam import QuamComponent, components
@quam_dataclass
class DummyClass(components.pulses.SquarePulse):
    W: list = None
    C: float = 0.0


# %% {Node_parameters}
class Parameters(NodeParameters):
    # Default settings assume you have a tuned-up EF gate.
    # If your EF gate is not tuned up, set anharmonicity~=150MHz (location of 2-photon GF transition),
    # use ef_operation="saturation", ef_op_amplitude=0.8 and enable_x180_pre=True

    qubits: Optional[List[str]] = None
    num_runs: int = 2000

    # What operation to use to try to excite |2>
    ef_operation: str = "EF_x180"  # "EF_x180" or "saturation"
    ef_op_amplitude: Optional[float] = None  # Uses operation default settings if None
    ef_op_duration_ns: Optional[int] = None  # Uses operation default settings if None

    # Steps applied to prepare the second state. Default will prepare |1>. Other options attempt to prepare |2>.
    enable_x180_pre: bool = True
    num_EF_op_repeats: int = 1  # Number of times to repeat the EF-excitation operation. (0 = don't apply).
    enable_x180_post: bool = False  # If it was in state |1> it should go back to |0> so any blob overlapping with |1> is the real deal.

    reset_type_thermal_or_active: Literal["thermal", "active"] = "active"
    flux_point_joint_or_independent: Literal["joint", "independent"] = "independent"
    operation_name: str = "readout"  # or "readout_QND"
    simulate: bool = False
    simulation_duration_ns: int = 2500
    timeout: int = 100
    load_data_id: Optional[int] = None
    multiplexed: bool = False

description = """Typical Runtime w/Default Params:
30-35s for all qubits
8-10s per qubit
"""

node = QualibrationNode(name="07d_IQ_Blobs_3state", description=description, parameters=Parameters())


# %% {Initialize_QuAM_and_QOP}
# Class containing tools to help handling units and conversions.
u = unit(coerce_to_integer=True)
# Instantiate the QuAM class from the state file
machine = QuAM.load(fix_attrs=False)
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
n_runs = node.parameters.num_runs  # Number of runs
flux_point = node.parameters.flux_point_joint_or_independent  # 'independent' or 'joint'
reset_type = node.parameters.reset_type_thermal_or_active  # "active" or "thermal"
operation_name = node.parameters.operation_name
if node.parameters.ef_op_duration_ns is not None:
    ef_op_duration_ns = (node.parameters.ef_op_duration_ns // 4)  # divide by 4 to convert ns into clock cycles @ 4ns.
else:
    ef_op_duration_ns = None

with program() as iq_blobs:
    n = declare(int)
    n_st = declare_stream()
    # Single pair of per-qubit IQ variables reused for all prepared states
    I = [declare(fixed) for _ in range(num_qubits)]
    Q = [declare(fixed) for _ in range(num_qubits)]

    # Separate streams for each prepared state
    I_g_st = [declare_stream() for _ in range(num_qubits)]
    Q_g_st = [declare_stream() for _ in range(num_qubits)]
    I_e_st = [declare_stream() for _ in range(num_qubits)]
    Q_e_st = [declare_stream() for _ in range(num_qubits)]
    I_f_st = [declare_stream() for _ in range(num_qubits)]
    Q_f_st = [declare_stream() for _ in range(num_qubits)]

    # I_g, I_g_st, Q_g, Q_g_st, n, n_st = qua_declaration(num_qubits=num_qubits)
    # I_e, I_e_st, Q_e, Q_e_st, _, _ = qua_declaration(num_qubits=num_qubits)
    # I_f, I_f_st, Q_f, Q_f_st, _, _ = qua_declaration(num_qubits=num_qubits)

    shot = [declare(int) for _ in range(num_qubits)]

    if node.parameters.multiplexed:
        for i , qubit in enumerate(qubits):
            machine.set_all_fluxes(flux_point=flux_point, target=qubit)

    for i, qubit in enumerate(qubits):

        if not node.parameters.multiplexed:
            # Bring the active qubits to the desired frequency point
            machine.set_all_fluxes(flux_point=flux_point, target=qubit)

        with for_(shot[i], 0, shot[i] < n_runs, shot[i] + 1):
            save(shot[i], n_st)
            # ground iq blobs for all qubits
            
            if reset_type == "active":
                active_reset(qubit, "readout")
            elif reset_type == "thermal":
                qubit.wait(qubit.thermalization_time * u.ns)
            else:
                raise ValueError(f"Unrecognized reset type {reset_type}.")

            qubit.align()
            qubit.resonator.measure(operation_name, qua_vars=(I[i], Q[i]))
            qubit.resonator.wait(qubit.resonator.depletion_time * u.ns)
        
            # save data
            save(I[i], I_g_st[i])
            save(Q[i], Q_g_st[i])

            # Prepare state |1>
            qubit.align()
            if reset_type == "active":
                active_reset(qubit, "readout")
            elif reset_type == "thermal":
                qubit.wait(machine.thermalization_time * u.ns)
            else:
                raise ValueError(f"Unrecognized reset type {reset_type}.")
            
            qubit.align()
            qubit.xy.play("x180")

            qubit.align()
            qubit.resonator.measure(operation_name, qua_vars=(I[i], Q[i]))
            qubit.resonator.wait(qubit.resonator.depletion_time * u.ns)

            # save data
            save(I[i], I_e_st[i])
            save(Q[i], Q_e_st[i])

            # Try to prepare state |2>
            qubit.align()
            if reset_type == "active":
                active_reset(qubit, "readout")
            elif reset_type == "thermal":
                qubit.wait(machine.thermalization_time * u.ns)
            else:
                raise ValueError(f"Unrecognized reset type {reset_type}.")
            
            if node.parameters.enable_x180_pre:
                qubit.align()
                qubit.xy.play("x180")

            if node.parameters.num_EF_op_repeats > 0:
                qubit.align()   
                qubit.xy.update_frequency(qubit.xy.intermediate_frequency - qubit.anharmonicity)
                align(qubit.xy.name, qubit.resonator.name)
                for _ in range(0,node.parameters.num_EF_op_repeats):
                    # Attempt to prepare |2>
                    qubit.align()
                    qubit.xy.play(
                        node.parameters.ef_operation,
                        amplitude_scale=node.parameters.ef_op_amplitude,
                        duration=ef_op_duration_ns
                    )
                qubit.xy.update_frequency(qubit.xy.intermediate_frequency)
                align(qubit.xy.name, qubit.resonator.name)
            
            if node.parameters.enable_x180_post:
                # Apply a second x180 gate. If state was |1> it will go back down to |0>.
                # If state was |2> it will stay there.
                qubit.align()
                qubit.xy.play("x180")

            qubit.align()
            qubit.resonator.measure(operation_name, qua_vars=(I[i], Q[i]))
            qubit.resonator.wait(qubit.resonator.depletion_time * u.ns)

            # Save data
            save(I[i], I_f_st[i])
            save(Q[i], Q_f_st[i])

        # Measure sequentially
        if not node.parameters.multiplexed:
            align()

    with stream_processing():
        n_st.save("n")
        for i in range(num_qubits):
            I_g_st[i].save_all(f"I_g{i + 1}")
            Q_g_st[i].save_all(f"Q_g{i + 1}")
            I_e_st[i].save_all(f"I_e{i + 1}")
            Q_e_st[i].save_all(f"Q_e{i + 1}")
            I_f_st[i].save_all(f"I_f{i + 1}")
            Q_f_st[i].save_all(f"Q_f{i + 1}")


# %% {Simulate_or_execute}
if node.parameters.simulate:
    # Simulates the QUA program for the specified duration
    simulation_config = SimulationConfig(duration=node.parameters.simulation_duration_ns * 4)  # In clock cycles = 4ns
    job = qmm.simulate(config, iq_blobs, simulation_config)
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
        job = qm.execute(iq_blobs)
        for i in range(num_qubits):
            results = fetching_tool(job, ["n"], mode="live")
            while results.is_processing():
                n = results.fetch_all()[0]
                progress_counter(n, n_runs, start_time=results.start_time)

# %% {Data_fetching_and_dataset_creation}
if not node.parameters.simulate:
    if node.parameters.load_data_id is None:
        # Fetch the data from the OPX and convert it into a xarray with corresponding axes (from most inner to outer loop)
        ds = fetch_results_as_xarray(job.result_handles, qubits, {"N": np.linspace(1, n_runs, n_runs)})

        # Fix the structure of ds to avoid tuples
        def extract_value(element):
            if isinstance(element, tuple):
                return element[0]
            return element

        ds = xr.apply_ufunc(
            extract_value,
            ds,
            vectorize=True,  # This ensures the function is applied element-wise
            dask="parallelized",  # This allows for parallel processing
            output_dtypes=[float],  # Specify the output data type
        )
        # Convert IQ data into volts (include all three prepared states)
        ds = convert_IQ_to_V(ds, qubits, ["I_g", "Q_g", "I_e", "Q_e", "I_f", "Q_f"])
    else:
        node = node.load_from_id(node.parameters.load_data_id)
        ds = node.results["ds"]



    # %% {Data_analysis}

    def three_state_discriminator_simple(iq_0,iq_1,iq_2):
        # First version that works well if you can reliably prepare |2>.
        # Calibration IQ data: each is array of shape (N_k, 2) with columns [I, Q]
        
        # Means
        mu0 = iq_0.mean(axis=0)  # (2,)
        mu1 = iq_1.mean(axis=0)
        mu2 = iq_2.mean(axis=0)

        # Shared covariance (2x2)
        all_iq = np.vstack([iq_0, iq_1, iq_2])
        Sigma = np.cov(all_iq.T)
        Sigma_inv = np.linalg.inv(Sigma)

        # Optional: priors (equal here)
        log_p = np.log(np.array([1/3, 1/3, 1/3]))

        # Precompute w_k and c_k
        mus = np.stack([mu0, mu1, mu2])  # (3, 2)
        W = Sigma_inv @ mus.T            # (2, 3) -> columns are w_k
        W = W.T                          # (3, 2) each row is w_k
        c = -0.5 * np.einsum('ki,ij,kj->k', mus, Sigma_inv, mus) + log_p  # (3,)
        return {"W": W,"C": c}

    def robust_circular_gaussian(iq, trim_quantile: float = 0.8):
        """
        Fit a robust, circularly symmetric 2D Gaussian:

        - Center is estimated from the high-density core (median, then trimmed by radius).
        - Covariance is constrained to sigma^2 * I, estimated from the core points.
        """
        iq = np.asarray(iq)

        if iq.ndim != 2 or iq.shape[1] != 2:
            raise ValueError("robust_circular_gaussian expects an array of shape (N, 2)")

        # Initial robust center via component-wise median
        center0 = np.median(iq, axis=0)
        r = np.linalg.norm(iq - center0, axis=1)

        # Keep only the central fraction of points to reject outliers
        if iq.shape[0] < 10:
            core = iq
        else:
            r_thresh = np.quantile(r, trim_quantile)
            core = iq[r <= r_thresh]
            if core.shape[0] < 10:
                core = iq

        # Final mean from the core
        mu = core.mean(axis=0)

        # Isotropic variance: for a 2D isotropic Gaussian, E[||x - mu||^2] = 2 * sigma^2
        r2 = np.sum((core - mu) ** 2, axis=1)
        if core.shape[0] > 0:
            sigma_sq = float(np.mean(r2) / 2.0)
        else:
            sigma_sq = 1.0

        if sigma_sq <= 0 or not np.isfinite(sigma_sq):
            sigma_sq = 1.0

        return mu, sigma_sq

    def three_state_discriminator(
        iq_0, iq_1, iq_2, exclusion_quantile: float = 0.95, trim_quantile: float = 0.8
    ):
        """
        Build a 3-state linear discriminator with robust, circularly symmetric Gaussians.

        - For each state, estimate a robust center and an isotropic variance (sigma^2 I)
          by focusing on the high-density core and rejecting outliers.
        - Use |0> and |1> to define circular Mahalanobis ellipses in a shared 0/1 metric
          and exclude |2> shots that fall inside those ellipses.
        - Fit the final 3-class linear model using the cleaned |2> set and a shared
          isotropic covariance for all three classes.

        Args:
            iq_0, iq_1, iq_2: Arrays of shape (N_k, 2) with columns [I, Q] for calibration shots.
            exclusion_quantile: Quantile of the Mahalanobis radius defining the |0> / |1> ellipses.
            trim_quantile: Fraction of points kept in the robust core when estimating each state's
                           circular Gaussian (used to downweight outliers / leakage).

        Returns:
            dict with:
                "W": (3, 2) matrix, each row is w_k for class k in g_k(x) = w_k^T x + c_k
                "C": (3,) vector of offsets c_k
                "mu": (3, 2) array of class centers [mu0, mu1, mu2]
                "Sigma": (2, 2) shared isotropic covariance used for the discriminator
                "Sigma_01": (2, 2) isotropic covariance used for the 0/1 ellipses
                "Sigma_01_inv": inverse of Sigma_01
                "r0_sq", "r1_sq": squared Mahalanobis radii for the |0> and |1> ellipses
                "mask_2": boolean mask selecting |2> shots that were treated as genuine |2>
                "sigma_sq_per_class": array of per-class isotropic variances [sigma0^2, sigma1^2, sigma2^2]
        """
        # Ensure numpy arrays
        iq_0 = np.asarray(iq_0)
        iq_1 = np.asarray(iq_1)
        iq_2 = np.asarray(iq_2)

        # ---------- Stage 1: robust circular fits for |0> and |1> ----------
        mu0, sigma0_sq = robust_circular_gaussian(iq_0, trim_quantile)
        mu1, sigma1_sq = robust_circular_gaussian(iq_1, trim_quantile)

        # Use a shared isotropic covariance for the 0/1 metric
        sigma01_sq = 0.5 * (sigma0_sq + sigma1_sq)
        Sigma_01 = np.eye(2) * sigma01_sq
        Sigma_01_inv = np.eye(2) / sigma01_sq

        def mahalanobis_sq(x, mu, Sigma_inv):
            """Squared Mahalanobis distance for each row x."""
            d = x - mu
            return np.einsum("...i,ij,...j->...", d, Sigma_inv, d)

        # Radii for |0> and |1> clouds in the shared 0/1 metric.
        # Use a fixed k·sigma radius rather than a sample quantile, to avoid being inflated by outliers.
        d0_sq = mahalanobis_sq(iq_0, mu0, Sigma_01_inv)
        d1_sq = mahalanobis_sq(iq_1, mu1, Sigma_01_inv)
        k_sigma = 2.0  # ellipse radius in Mahalanobis units (~2σ circle)
        r0_sq = k_sigma**2
        r1_sq = k_sigma**2

        # ---------- Stage 2: filter iq_2 using the circular 0/1 ellipses ----------
        d0_sq_2 = mahalanobis_sq(iq_2, mu0, Sigma_01_inv)
        d1_sq_2 = mahalanobis_sq(iq_2, mu1, Sigma_01_inv)

        # Keep only points that lie outside both |0> and |1> ellipses
        mask_2 = (d0_sq_2 > r0_sq) & (d1_sq_2 > r1_sq)
        iq_2_clean = iq_2[mask_2]

        # If the filter is too aggressive and we lose almost everything, fall back to unfiltered iq_2
        if iq_2_clean.shape[0] < 10:
            iq_2_clean = iq_2
            mask_2 = np.ones(iq_2.shape[0], dtype=bool)

        # ---------- Stage 3: robust circular fit for |2> on the cleaned set ----------
        mu2, sigma2_sq = robust_circular_gaussian(iq_2_clean, trim_quantile)

        # Shared isotropic covariance for all three classes in the final discriminator
        sigma_shared_sq = np.mean([sigma0_sq, sigma1_sq, sigma2_sq])
        Sigma = np.eye(2) * sigma_shared_sq
        Sigma_inv = np.eye(2) / sigma_shared_sq

        # Priors (equal)
        log_p = np.log(np.array([1.0 / 3, 1.0 / 3, 1.0 / 3]))

        # Precompute w_k and c_k for the linear classifier
        mus = np.stack([mu0, mu1, mu2])  # (3, 2)
        W = Sigma_inv @ mus.T            # (2, 3) -> columns are w_k
        W = W.T                          # (3, 2) each row is w_k
        c = -0.5 * np.einsum("ki,ij,kj->k", mus, Sigma_inv, mus) + log_p  # (3,)

        return {
            "W": W,
            "C": c,
            # Store class means and shared covariance used for the final discriminator
            "mu": mus,
            "Sigma": Sigma,
            # Store the 0/1-only covariance and its inverse (used to define circular ellipses)
            "Sigma_01": Sigma_01,
            "Sigma_01_inv": Sigma_01_inv,
            # Radii and mask that define the exclusion region for |2>
            "r0_sq": float(r0_sq),
            "r1_sq": float(r1_sq),
            "mask_2": mask_2,
            # Per-class isotropic variances for diagnostics
            "sigma_sq_per_class": np.array([sigma0_sq, sigma1_sq, sigma2_sq]),
        }

    def classify_iq(x,calibration):
        """
        x: shape (2,) array [I, Q]
        returns: 0, 1, or 2
        """
        W = calibration['W']
        c = calibration['C']
        # scores g_k(x) = w_k^T x + c_k
        g = W @ x + c
        return int(np.argmax(g))

    def classify_batch(X,calibration):
        """
        X: shape (N, 2)
        """
        return np.array([classify_iq(x,calibration) for x in X])

    node.results = {"ds": ds, "figs": {}, "results": {}}
    plot_individual = False
    for qubit in qubits:
        # Calibrate three state discriminator
        iq_0 = np.stack([ds.I_g.sel(qubit=qubit.name), ds.Q_g.sel(qubit=qubit.name)], axis=1)  # |0> shots
        iq_1 = np.stack([ds.I_e.sel(qubit=qubit.name), ds.Q_e.sel(qubit=qubit.name)], axis=1)  # |1> shots
        iq_2 = np.stack([ds.I_f.sel(qubit=qubit.name), ds.Q_f.sel(qubit=qubit.name)], axis=1)  # |2> shots
        matched_filter_calibration = three_state_discriminator(iq_0, iq_1, iq_2)  # Calibrate the discriminator

        # Build effective "ground truth" labels that take into account the 0/1-based exclusion of some |2> shots.
        #   - 0-block (first n_runs): always label 0
        #   - 1-block (second n_runs): always label 1
        #   - 2-block (third n_runs): label as 2 if outside both 0/1 ellipses, otherwise relabel as 0 or 1
        mf = matched_filter_calibration
        mus = np.asarray(mf["mu"])
        mu0 = mus[0]
        mu1 = mus[1]
        Sigma_01_inv = np.asarray(mf["Sigma_01_inv"])
        mask_2 = np.asarray(mf["mask_2"], dtype=bool)

        def mahalanobis_sq(x, mu, Sigma_inv):
            d = x - mu
            return np.einsum("...i,ij,...j->...", d, Sigma_inv, d)

        # Distances of the |2> calibration shots to the |0> and |1> means in the 0/1 metric
        d0_sq_2 = mahalanobis_sq(iq_2, mu0, Sigma_01_inv)
        d1_sq_2 = mahalanobis_sq(iq_2, mu1, Sigma_01_inv)

        labels = np.zeros(3 * n_runs, dtype=int)
        labels[:n_runs] = 0
        labels[n_runs:2 * n_runs] = 1

        # Effective labels for the "third" preparation
        effective_labels_2 = np.empty(n_runs, dtype=int)
        # Shots outside both 0/1 ellipses are treated as genuine |2>
        effective_labels_2[mask_2] = 2
        # Shots inside one of the ellipses are relabeled as whichever state they are closer to
        closer_to_0 = d0_sq_2 < d1_sq_2
        effective_labels_2[~mask_2 & closer_to_0] = 0
        effective_labels_2[~mask_2 & ~closer_to_0] = 1

        labels[2 * n_runs:] = effective_labels_2

        # Classifier predictions on all shots (no exclusions)
        iq_all = np.concatenate((iq_0, iq_1, iq_2), axis=0)
        predictions = classify_batch(iq_all, matched_filter_calibration)

        # Build 3×3 confusion matrix using the effective labels
        confusion_matrix = np.zeros((3, 3))
        for i in range(0, 3):
            for j in range(0, 3):
                # m_ij = Pr(predicted_i ^ effective_label_j) / Pr(effective_label_j)
                confusion_matrix[i, j] = (
                    np.count_nonzero((predictions == i) & (labels == j))
                ) / np.count_nonzero(labels == j)
        node.results["results"][qubit.name] = {}
        node.results["results"][qubit.name]["matched_filter"] = matched_filter_calibration  # Save discriminator calibration for future use
        node.results["results"][qubit.name]["confusion_matrix"] = confusion_matrix
        
        if 1:  # Plot the ellipses
            # Debug plot: show 0/1 ellipses and filtered vs discarded |2> points
            # This reuses the Mahalanobis-based exclusion computed in three_state_discriminator.

            # Pull intermediate quantities from the calibration dict
            mus = matched_filter_calibration["mu"]
            mu0 = mus[0]
            mu1 = mus[1]
            Sigma_01 = matched_filter_calibration["Sigma_01"]
            r0_sq = matched_filter_calibration["r0_sq"]
            r1_sq = matched_filter_calibration["r1_sq"]
            mask_2 = matched_filter_calibration["mask_2"]

            # Recover which |2> shots were kept vs discarded
            iq_2_kept = iq_2[mask_2]
            iq_2_discarded = iq_2[~mask_2]

            # Build ellipse shapes from Sigma_01
            theta = np.linspace(0, 2 * np.pi, 200)
            circle = np.stack([np.cos(theta), np.sin(theta)])  # (2, N)
            eigvals, eigvecs = np.linalg.eigh(Sigma_01)
            # Guard against tiny negative eigenvalues from numerical noise
            eigvals = np.maximum(eigvals, 0)
            L = eigvecs @ np.diag(np.sqrt(eigvals))

            def ellipse_points(mu, r_sq):
                r = np.sqrt(max(r_sq, 0))
                pts = mu[:, None] + L @ (r * circle)
                return pts[0, :], pts[1, :]

            ell0_x, ell0_y = ellipse_points(mu0, r0_sq)
            ell1_x, ell1_y = ellipse_points(mu1, r1_sq)

            # ---------- Plot data and ellipses ----------
            fig_ell, ax_ell = plt.subplots(figsize=(6, 6))
            ax_ell.scatter(1e3 * iq_0[:, 0], 1e3 * iq_0[:, 1],
                           s=3, alpha=0.3, label="|0> shots", color="C0")
            ax_ell.scatter(1e3 * iq_1[:, 0], 1e3 * iq_1[:, 1],
                           s=3, alpha=0.3, label="|1> shots", color="C1")

            if iq_2_discarded.size > 0:
                ax_ell.scatter(1e3 * iq_2_discarded[:, 0], 1e3 * iq_2_discarded[:, 1],
                               s=4, alpha=0.2, label="|2> (discarded)", color="C2")
            if iq_2_kept.size > 0:
                ax_ell.scatter(1e3 * iq_2_kept[:, 0], 1e3 * iq_2_kept[:, 1],
                               s=6, alpha=0.7, label="|2> (kept)", color="C3")

            # Fill ellipses as shaded regions
            ax_ell.fill(1e3 * ell0_x, 1e3 * ell0_y, color="C0", alpha=0.1)
            ax_ell.plot(1e3 * ell0_x, 1e3 * ell0_y, color="C0", lw=1, label="|0> ellipse")
            ax_ell.fill(1e3 * ell1_x, 1e3 * ell1_y, color="C1", alpha=0.1)
            ax_ell.plot(1e3 * ell1_x, 1e3 * ell1_y, color="C1", lw=1, label="|1> ellipse")

            ax_ell.set_xlabel("I [mV]")
            ax_ell.set_ylabel("Q [mV]")
            ax_ell.set_title(f"IQ with 0/1 ellipses — {qubit.name}")
            ax_ell.axis("equal")
            ax_ell.grid(False)
            ax_ell.legend(loc="best", fontsize="small")

            plt.tight_layout()
            if "figs" not in node.results:
                node.results["figs"] = {}
            node.results["figs"][f"ellipses_{qubit.name}"] = fig_ell
            plt.show()
            
        # End of 3-state... below is original 2-state code.


    # Plot raw IQ streams (no subplots) and annotate with the prepared state for each qubit
    show_three_state_ellipses = True  # hard-coded option to toggle ellipses on/off
    if "figs" not in node.results:
        node.results["figs"] = {}

    for i, qubit in enumerate(qubits):
        fig, ax = plt.subplots(figsize=(6, 6))
        plotted_any = False

        # Define bases and colors for the IQ pairs
        pairs = [("I_g", "Q_g", "$\\left | 0 \\right >$", "C0"), ("I_e", "Q_e", "$\\left | 1 \\right >$", "C1"), ("I_f", "Q_f", "$\\left | 2 \\right >$", "C2")]

        # Try to find matching I/Q pairs, including suffixed variants (e.g., I_g1 / Q_g1)
        for I_base, Q_base, label_base, color in pairs:
            # find any I keys that start with the I_base
            I_candidates = [k for k in ds.data_vars if k.startswith(I_base)]
            for I_key in I_candidates:
                suffix = I_key[len(I_base) :]  # may be empty or like '1', '2', etc.
                Q_key = Q_base + suffix
                if Q_key not in ds.data_vars:
                    continue
                try:
                    I_series = ds[I_key].sel(qubit=qubit.name).values
                    Q_series = ds[Q_key].sel(qubit=qubit.name).values
                except Exception:
                    continue

                shots = np.arange(1, I_series.size + 1)
                ax.plot(
                    1e3 * I_series,
                    1e3 * Q_series,
                    ".",
                    alpha=0.25, #if label_base != "|2>" else .95,
                    # markersize=1.5,
                    color=color,
                    label=f"{label_base}{suffix}" if suffix else label_base,
                )
                plotted_any = True

        # If nothing plotted, fall back to plotting any I/Q named exactly (no suffix)
        if not plotted_any:
            for I_base, Q_base, label_base, color in pairs:
                if I_base in ds.data_vars and Q_base in ds.data_vars:
                    try:
                        I_series = ds[I_base].sel(qubit=qubit.name).values
                        Q_series = ds[Q_base].sel(qubit=qubit.name).values
                        ax.plot(1e3 * I_series, 1e3 * Q_series, ".", alpha=0.25, markersize=1.5, color=color, label=label_base)
                        plotted_any = True
                    except Exception:
                        pass

        # Optionally overlay the final 3-state ellipses on this raw-IQ plot
        if show_three_state_ellipses:
            state = node.results.get("results", {}).get(qubit.name, {})
            mf = state.get("matched_filter")
            if mf is not None and "mu" in mf and "Sigma" in mf:
                mus = np.asarray(mf["mu"])
                Sigma = np.asarray(mf["Sigma"])
                # Protect against malformed Sigma
                try:
                    Sigma_inv = np.linalg.inv(Sigma)
                except np.linalg.LinAlgError:
                    Sigma_inv = None

                if Sigma_inv is not None:
                    # Reconstruct IQ arrays for this qubit
                    iq_0 = np.stack(
                        [ds.I_g.sel(qubit=qubit.name), ds.Q_g.sel(qubit=qubit.name)],
                        axis=1,
                    )
                    iq_1 = np.stack(
                        [ds.I_e.sel(qubit=qubit.name), ds.Q_e.sel(qubit=qubit.name)],
                        axis=1,
                    )
                    iq_2 = np.stack(
                        [ds.I_f.sel(qubit=qubit.name), ds.Q_f.sel(qubit=qubit.name)],
                        axis=1,
                    )

                    # Use the same |2>-filter mask as the discriminator, if available
                    mask_2 = mf.get("mask_2", None)
                    if mask_2 is not None:
                        mask_2 = np.asarray(mask_2, dtype=bool)
                        if mask_2.shape[0] == iq_2.shape[0]:
                            iq_2_clean = iq_2[mask_2]
                        else:
                            iq_2_clean = iq_2
                    else:
                        iq_2_clean = iq_2

                    def mahalanobis_sq(x, mu, Sigma_inv):
                        d = x - mu
                        return np.einsum("...i,ij,...j->...", d, Sigma_inv, d)

                    # Radii for each class in the final shared covariance metric.
                    # Use a fixed k·sigma circle for all three states so the ellipses are comparable in size
                    # and not blown up by outliers.
                    k_sigma_plot = 2.0  # ellipse radius in Mahalanobis units (~2σ)
                    r0_sq = k_sigma_plot**2
                    r1_sq = k_sigma_plot**2
                    r2_sq = k_sigma_plot**2 if iq_2_clean.shape[0] > 0 else None

                    # Build ellipse shapes from the final Sigma
                    eigvals, eigvecs = np.linalg.eigh(Sigma)
                    eigvals = np.maximum(eigvals, 0)
                    L = eigvecs @ np.diag(np.sqrt(eigvals))

                    theta = np.linspace(0, 2 * np.pi, 200)
                    circle = np.stack([np.cos(theta), np.sin(theta)])  # (2, N)

                    def ellipse_points(mu, r_sq):
                        if r_sq is None:
                            return None, None
                        r = np.sqrt(max(r_sq, 0))
                        pts = mu[:, None] + L @ (r * circle)
                        return pts[0, :], pts[1, :]

                    ellipses = [
                        (ellipse_points(mus[0], r0_sq), "C0", "|0> ellipse"),
                        (ellipse_points(mus[1], r1_sq), "C1", "|1> ellipse"),
                        (ellipse_points(mus[2], r2_sq), "C2", "|2> ellipse"),
                    ]

                    for (ex, ey), color, _label in ellipses:
                        if ex is None or ey is None:
                            continue
                        # Use the same color as the points, with light fill and outline
                        ax.fill(1e3 * ex, 1e3 * ey, color=color, alpha=0.08)
                        ax.plot(1e3 * ex, 1e3 * ey, color=color, lw=1)

        ax.set_xlabel("I [mV]")
        ax.set_ylabel("Q [mV]")
        ax.set_title(f"I vs Q — {qubit.name}")
        # ax.set_title(f"I vs Q — {q.name} - Intermidiate freq. { q.xy.intermediate_frequency/1e6} MHz , {(q.anharmonicity)/1e6} MHz")
        ax.axis("equal")
        ax.grid(False)
        if plotted_any:
            ax.legend(loc="upper right", fontsize="small", markerscale=3)

        # annotate with the computed state if available
        state = node.results.get("results", {}).get(qubit.name, {})
        angle = state.get("angle", np.nan)
        threshold = state.get("threshold", np.nan)
        rus_threshold = state.get("rus_threshold", np.nan)
        fidelity = state.get("fidelity", np.nan)
        conf = state.get("confusion_matrix", None)

        info_lines = [
            # f"angle = {angle:.6f}",
            # f"threshold = {threshold:.6f}",
            # f"RUS threshold = {rus_threshold:.6f}",
            # f"fidelity = {fidelity:.4f}",
        ]
        if conf is not None:
            info_lines.append("confusion:")
            try:
                cm = np.array(conf)
                # Format full 3×3 confusion matrix
                cm_lines = []
                for r in range(3):
                    cm_lines.append(
                        f"[{cm[r,0]:.3f} {cm[r,1]:.3f} {cm[r,2]:.3f}]"
                    )
                info_lines += cm_lines
            except Exception:
                info_lines.append(str(conf))

        ax.text(
            0.99,
            0.01,
            "\n".join(info_lines),
            ha="right",
            va="bottom",
            transform=ax.transAxes,
            fontsize=8,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
        )

        plt.tight_layout()
        node.results["figs"][f"raw_IQ_{qubit.name}"] = fig
        plt.show()

    # %% {Update_state}
    if node.parameters.load_data_id is None:
        with node.record_state_updates():
            for qubit in qubits:
                if operation_name == "readout":
                    qubit.resonator.matched_filter_W = node.results["results"][qubit.name]["matched_filter"]['W'].tolist()
                    qubit.resonator.matched_filter_C = node.results["results"][qubit.name]["matched_filter"]['C'].tolist()
                    qubit.resonator.confusion_matrix_3x3 = node.results["results"][qubit.name]["confusion_matrix"].tolist()

        # %% {Save_results}
        node.outcomes = {q.name: "successful" for q in qubits}
        node.results["initial_parameters"] = node.parameters.model_dump()
        node.machine = machine
        node.save()
