"""
        SINGLE QUBIT LEAKY RANDOMIZED BENCHMARKING
The program consists in playing random sequences of Clifford gates and measuring the state of the resonator afterward.
Each random sequence is derived on the FPGA for the maximum depth (specified as an input) and played for each depth
asked by the user (the sequence is truncated to the desired depth). Each truncated sequence ends with the recovery gate,
found at each step thanks to a preloaded lookup table (Cayley table), that will bring the qubit back to its ground state.

Leaky RB extends standard RB by using a 3-state readout to explicitly monitor leakage into |2>.
In addition to the standard RB survival curve, we extract:
    - p0(m), p1(m), p2(m)  (p2 is leakage)
    - p_comp(m) = p0(m) + p1(m)  (population remaining in computational subspace)

If the readout has been calibrated and is good enough, then state discrimination can be applied to only return the state
of the qubit. Otherwise, the 'I' and 'Q' quadratures are returned.
Each sequence is played n_avg times for averaging. A second averaging is performed by playing different random sequences.

Prerequisites:
    - Having found the resonance frequency of the resonator coupled to the qubit under study (resonator_spectroscopy).
    - Having calibrated qubit pi pulse (x180) by running qubit spectroscopy, rabi_chevron, power_rabi and updated the state.
    - Having the qubit frequency perfectly calibrated (ramsey).
    - (recommended) Having calibrated 3-state readout (IQ_blobs) and stored matched_filter_W/C in the state.json.
    - Set the desired flux bias.
"""

# %% {Imports}
from qualibrate import QualibrationNode, NodeParameters
from quam_libs.components import QuAM, Transmon
from quam_libs.macros import qua_declaration, active_reset, readout_state
from quam_libs.lib.plot_utils import QubitGrid, grid_iter
from quam_libs.lib.save_utils import fetch_results_as_xarray, load_dataset
from quam_libs.lib.fit import fit_decay_exp, decay_exp
from qualang_tools.results import progress_counter, fetching_tool
from qualang_tools.bakery.randomized_benchmark_c1 import c1_table
from qualang_tools.multi_user import qm_session
from qualang_tools.units import unit
from qm import SimulationConfig
from qm.qua import *
from typing import Literal, Optional, List, Dict, Any
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from scipy.optimize import curve_fit


# %% {Node_parameters}
class Parameters(NodeParameters):
    qubits: Optional[List[str]] = ["q6"]
    use_state_discrimination: bool = True
    use_strict_timing: bool = False
    num_random_sequences: int = 1000
    num_averages: int = 1
    max_circuit_depth: int = 1000
    delta_clifford: int = 50
    seed: int = 345324
    flux_point_joint_or_independent: Literal["joint", "independent"] = "independent"
    reset_type_thermal_or_active: Literal["thermal", "active"] = "active"
    simulate: bool = False
    simulation_duration_ns: int = 2500
    timeout: int = 100
    load_data_id: Optional[int] = None
    multiplexed: bool = False

    # leaky-RB specific
    fit_leakage_curve: bool = True


description = """Typical Runtime w/Default Params:
40-50s for all qubits
8-10s per qubit
"""

node = QualibrationNode(name="10a_Single_Qubit_Leaky_RB", description=description, parameters=Parameters())


# %% {Initialize_QuAM_and_QOP}
u = unit(coerce_to_integer=True)
machine = QuAM.load()
config = machine.generate_config()

if node.parameters.load_data_id is None:
    qmm = machine.connect()

if node.parameters.qubits is None or node.parameters.qubits == "":
    qubits = machine.active_qubits
else:
    qubits = [machine.qubits[q] for q in node.parameters.qubits]
num_qubits = len(qubits)


# %% {QUA_program_parameters}
num_of_sequences = node.parameters.num_random_sequences
n_avg = node.parameters.num_averages
max_circuit_depth = node.parameters.max_circuit_depth

if node.parameters.delta_clifford < 1:
    raise NotImplementedError("Delta clifford < 2 is not supported.")
delta_clifford = node.parameters.delta_clifford

flux_point = node.parameters.flux_point_joint_or_independent
reset_type = node.parameters.reset_type_thermal_or_active

assert (max_circuit_depth / delta_clifford).is_integer(), "max_circuit_depth / delta_clifford must be an integer."
num_depths = max_circuit_depth // delta_clifford + 1

seed = node.parameters.seed
state_discrimination = node.parameters.use_state_discrimination
strict_timing = node.parameters.use_strict_timing

inv_gates = [int(np.where(c1_table[i, :] == 0)[0][0]) for i in range(24)]


# %% {Utility functions}
def generate_sequence():
    cayley = declare(int, value=c1_table.flatten().tolist())
    inv_list = declare(int, value=inv_gates)
    current_state = declare(int)
    step = declare(int)
    sequence = declare(int, size=max_circuit_depth + 1)
    inv_gate = declare(int, size=max_circuit_depth + 1)
    i = declare(int)
    rand = Random(seed=seed)

    assign(current_state, 0)
    with for_(i, 0, i < max_circuit_depth, i + 1):
        assign(step, rand.rand_int(24))
        assign(current_state, cayley[current_state * 24 + step])
        assign(sequence[i], step)
        assign(inv_gate[i], inv_list[current_state])

    return sequence, inv_gate


def play_sequence(sequence_list, depth, qubit: Transmon):
    i = declare(int)
    with for_(i, 0, i <= depth, i + 1):
        with switch_(sequence_list[i], unsafe=True):
            with case_(0):
                qubit.xy.wait(qubit.xy.operations["x180"].length // 4)
            with case_(1):
                qubit.xy.play("x180")
            with case_(2):
                qubit.xy.play("y180")
            with case_(3):
                qubit.xy.play("y180")
                qubit.xy.play("x180")
            with case_(4):
                qubit.xy.play("x90")
                qubit.xy.play("y90")
            with case_(5):
                qubit.xy.play("x90")
                qubit.xy.play("-y90")
            with case_(6):
                qubit.xy.play("-x90")
                qubit.xy.play("y90")
            with case_(7):
                qubit.xy.play("-x90")
                qubit.xy.play("-y90")
            with case_(8):
                qubit.xy.play("y90")
                qubit.xy.play("x90")
            with case_(9):
                qubit.xy.play("y90")
                qubit.xy.play("-x90")
            with case_(10):
                qubit.xy.play("-y90")
                qubit.xy.play("x90")
            with case_(11):
                qubit.xy.play("-y90")
                qubit.xy.play("-x90")
            with case_(12):
                qubit.xy.play("x90")
            with case_(13):
                qubit.xy.play("-x90")
            with case_(14):
                qubit.xy.play("y90")
            with case_(15):
                qubit.xy.play("-y90")
            with case_(16):
                qubit.xy.play("-x90")
                qubit.xy.play("y90")
                qubit.xy.play("x90")
            with case_(17):
                qubit.xy.play("-x90")
                qubit.xy.play("-y90")
                qubit.xy.play("x90")
            with case_(18):
                qubit.xy.play("x180")
                qubit.xy.play("y90")
            with case_(19):
                qubit.xy.play("x180")
                qubit.xy.play("-y90")
            with case_(20):
                qubit.xy.play("y180")
                qubit.xy.play("x90")
            with case_(21):
                qubit.xy.play("y180")
                qubit.xy.play("-x90")
            with case_(22):
                qubit.xy.play("x90")
                qubit.xy.play("y90")
                qubit.xy.play("x90")
            with case_(23):
                qubit.xy.play("-x90")
                qubit.xy.play("y90")
                qubit.xy.play("-x90")


# %% {Leaky RB analysis helpers}
def leakage_model(m, p2_inf, gamma, p2_0):
    return p2_0 + p2_inf * (1 - np.exp(-gamma * m))


def compute_probabilities_from_labels(ds: xr.Dataset) -> xr.Dataset:
    s = ds["state"]
    mean_dims = []
    for cand in ["sequence", "n_avg", "avg", "shot", "repetition"]:
        if cand in s.dims:
            mean_dims.append(cand)
    if not mean_dims:
        raise ValueError(f"Could not find averaging dims in state dims={s.dims}.")

    p0 = (s == 0).mean(dim=mean_dims)
    p1 = (s == 1).mean(dim=mean_dims)
    p2 = (s == 2).mean(dim=mean_dims)
    pcomp = p0 + p1
    return xr.Dataset({"p0": p0, "p1": p1, "p2": p2, "pcomp": pcomp})


def fit_leakage_vs_depth(m: np.ndarray, p2: np.ndarray) -> Dict[str, float]:
    p2_0_guess = float(p2[0])
    p2_inf_guess = float(max(p2) - p2[0])
    gamma_guess = 1e-3
    popt, _ = curve_fit(
        leakage_model,
        m.astype(float),
        p2.astype(float),
        p0=[p2_inf_guess, gamma_guess, p2_0_guess],
        bounds=([0.0, 0.0, 0.0], [1.0, 10.0, 1.0]),
        maxfev=20000,
    )
    return {"p2_inf": float(popt[0]), "gamma": float(popt[1]), "p2_0": float(popt[2])}


def probs_to_jsonable(probs: xr.Dataset, qubits) -> Dict[str, Any]:
    """
    Convert probs Dataset (p0/p1/p2/pcomp vs depths/qubit) into JSON-friendly dict.
    """
    out: Dict[str, Any] = {}
    # store depth axis once (use the native 'depths' coord)
    depths = probs["p0"].coords["depths"].values.astype(float).tolist()
    out["depths"] = depths

    per_qubit: Dict[str, Any] = {}
    for q in qubits:
        qq = q.name
        per_qubit[qq] = {
            "p0": probs["p0"].sel(qubit=qq).values.astype(float).tolist(),
            "p1": probs["p1"].sel(qubit=qq).values.astype(float).tolist(),
            "p2": probs["p2"].sel(qubit=qq).values.astype(float).tolist(),
            "pcomp": probs["pcomp"].sel(qubit=qq).values.astype(float).tolist(),
        }
    out["per_qubit"] = per_qubit
    return out


# %% {QUA_programs}
# IMPORTANT: we save RAW state labels (0/1/2). Do NOT average integer labels on the OPX.
with program() as randomized_benchmarking_individual:
    depth = declare(int)
    depth_target = declare(int)
    saved_gate = declare(int)
    m = declare(int)
    I, I_st, Q, Q_st, n, n_st = qua_declaration(num_qubits=num_qubits)
    state = [declare(int) for _ in range(num_qubits)]
    m_st = declare_stream()
    state_st = [declare_stream() for _ in range(num_qubits)]

    for i, qubit in enumerate(qubits):
        align()
        machine.set_all_fluxes(flux_point=flux_point, target=qubit)

        with for_(m, 0, m < num_of_sequences, m + 1):
            sequence_list, inv_gate_list = generate_sequence()
            assign(depth_target, 0)

            with for_(depth, 1, depth <= max_circuit_depth, depth + 1):
                assign(saved_gate, sequence_list[depth])
                assign(sequence_list[depth], inv_gate_list[depth - 1])

                with if_((depth == 1) | (depth == depth_target)):
                    with for_(n, 0, n < n_avg, n + 1):
                        if reset_type == "active":
                            active_reset(qubit, "readout")
                        else:
                            qubit.resonator.wait(qubit.thermalization_time * u.ns)

                        qubit.align()

                        if strict_timing:
                            with strict_timing_():
                                play_sequence(sequence_list, depth, qubit)
                        else:
                            play_sequence(sequence_list, depth, qubit)

                        qubit.align()
                        readout_state(qubit, state[i])  # must output 0/1/2 for leaky RB
                        save(state[i], state_st[i])

                    assign(depth_target, depth_target + delta_clifford)

                assign(sequence_list[depth], saved_gate)

            save(m, m_st)

    with stream_processing():
        m_st.save("iteration")
        for i in range(num_qubits):
            state_st[i].buffer(n_avg).buffer(num_depths).buffer(num_of_sequences).save(f"state{i + 1}")


with program() as randomized_benchmarking_multiplexed:
    depth = declare(int)
    depth_target = declare(int)
    saved_gate = declare(int)
    m = declare(int)
    I, I_st, Q, Q_st, n, n_st = qua_declaration(num_qubits=num_qubits)
    state = [declare(int) for _ in range(num_qubits)]
    m_st = declare_stream()
    state_st = [declare_stream() for _ in range(num_qubits)]

    for i, qubit in enumerate(qubits):
        machine.set_all_fluxes(flux_point=flux_point, target=qubit)

    with for_(m, 0, m < num_of_sequences, m + 1):
        sequence_list, inv_gate_list = generate_sequence()
        assign(depth_target, 0)

        with for_(depth, 1, depth <= max_circuit_depth, depth + 1):
            assign(saved_gate, sequence_list[depth])
            assign(sequence_list[depth], inv_gate_list[depth - 1])

            with if_((depth == 1) | (depth == depth_target)):
                with for_(n, 0, n < n_avg, n + 1):

                    for i, qubit in enumerate(qubits):
                        if reset_type == "active":
                            active_reset(qubit, "readout")
                        else:
                            qubit.resonator.wait(qubit.thermalization_time * u.ns)

                    align()

                    for i, qubit in enumerate(qubits):
                        if strict_timing:
                            with strict_timing_():
                                play_sequence(sequence_list, depth, qubit)
                        else:
                            play_sequence(sequence_list, depth, qubit)

                    align()

                    for i, qubit in enumerate(qubits):
                        readout_state(qubit, state[i])  # must output 0/1/2
                        save(state[i], state_st[i])

                assign(depth_target, depth_target + delta_clifford)

            assign(sequence_list[depth], saved_gate)

        save(m, m_st)

    with stream_processing():
        m_st.save("iteration")
        for i in range(num_qubits):
            state_st[i].buffer(n_avg).buffer(num_depths).buffer(num_of_sequences).save(f"state{i + 1}")


# %% {Simulate_or_execute}
if node.parameters.simulate:
    simulation_config = SimulationConfig(duration=100_000)
    job = qmm.simulate(config, randomized_benchmarking_individual, simulation_config)
    samples = job.get_simulated_samples()
    fig, ax = plt.subplots(nrows=len(samples.keys()), sharex=True)
    for i, con in enumerate(samples.keys()):
        plt.subplot(len(samples.keys()), 1, i + 1)
        samples[con].plot()
        plt.title(con)
    plt.tight_layout()
    node.results["figure"] = plt.gcf()
    node.machine = machine
    node.save()

elif node.parameters.load_data_id is None:
    node.results = {}
    with qm_session(qmm, config, timeout=node.parameters.timeout) as qm:
        if not node.parameters.multiplexed:
            job = qm.execute(randomized_benchmarking_individual)
        else:
            job = qm.execute(randomized_benchmarking_multiplexed)

        results = fetching_tool(job, ["iteration"], mode="live")
        while results.is_processing():
            m = results.fetch_all()[0]
            progress_counter(m, num_of_sequences, start_time=results.start_time)

    # %% {Data_fetching_and_dataset_creation}
    depths = np.arange(0, max_circuit_depth + 0.1, delta_clifford)
    depths[0] = 1

    ds = fetch_results_as_xarray(
        job.result_handles,
        qubits,
        {"depths": depths, "sequence": np.arange(num_of_sequences)},
    )

    # Store ds (Qualibrate/qualang_tools usually handles xarray dataset saving),
    # but DO NOT store DataArrays directly in node.results (JSON serialization issues).
    node.results = {"ds": ds}

    # %% {Leaky RB probabilities}
    probs = compute_probabilities_from_labels(ds)

    # --- Standard RB fit on p0 (but computed correctly from labels) ---
    da_p0 = probs["p0"]
    da_p0.attrs = {"long_name": "p(|0>)"}
    da_p0 = da_p0.assign_coords(depths=da_p0.depths - 1)
    da_p0 = da_p0.rename(depths="m")

    da_fit = fit_decay_exp(da_p0, "m")
    alpha = np.exp(da_fit.sel(fit_vals="decay"))

    average_gate_per_clifford = (1 * 3 + 9 * 2 + 1 * 4 + 2 * 3 + 4 * 2 + 2 * 3) / 24
    EPC = (1 - alpha) - (1 - alpha) / 2
    EPG = EPC / average_gate_per_clifford

    # --- Save JSON-friendly results only ---
    node.results["fit_results"] = {}
    for q in qubits:
        qq = q.name
        node.results["fit_results"][qq] = {
            "EPC": float(EPC.sel(qubit=qq).values),
            "EPG": float(EPG.sel(qubit=qq).values),
        }

    # Leakage fit on p2
    if node.parameters.fit_leakage_curve:
        m_vals = da_p0["m"].values.astype(float)
        for q in qubits:
            qq = q.name
            p2_vals = probs["p2"].sel(qubit=qq).values
            try:
                node.results["fit_results"][qq]["p2_fit"] = fit_leakage_vs_depth(m_vals, p2_vals)
            except Exception as e:
                node.results["fit_results"][qq]["p2_fit"] = {"fit_error": str(e)}

    # Save probabilities in JSON-safe form
    node.results["probs_json"] = probs_to_jsonable(probs, qubits)

    # Print summary
    for q in qubits:
        qq = q.name
        fr = node.results["fit_results"][qq]
        print(f"{qq}: EPC={fr['EPC']}, EPG={fr['EPG']}")
        if "p2_fit" in fr:
            print(f"{qq}: p2_fit={fr['p2_fit']}")

    # %% {Plotting}
    plt.rcParams.update({"font.size": 10})
    plt.rcParams.update({"figure.figsize": [8, 6], 'dpi': 300} )
    
    grid = QubitGrid(ds, [q.grid_location for q in qubits])
    for ax, qubit in grid_iter(grid):
        qq = qubit["qubit"]

        m_plot = da_p0.sel(qubit=qq)["m"].values
        p0_plot = probs["p0"].sel(qubit=qq).values
        p2_plot = probs["p2"].sel(qubit=qq).values
        pcomp_plot = probs["pcomp"].sel(qubit=qq).values

        ax.plot(m_plot, p0_plot, ".", label="p0")
        ax.plot(m_plot, p2_plot, ".", label="p2 (leakage)")
        ax.plot(m_plot, pcomp_plot, ".", label="p0+p1")

        ax.grid("all")
        ax.set_title(qq, pad=22)
        ax.set_xlabel("Circuit depth (Cliffords)")
        ax.set_ylabel("Probability")

        # RB fit overlay on p0
        fit_dict = {k: da_fit.sel(qubit=qq).sel(fit_vals=k).values for k in da_fit.fit_vals.values}
        ax.plot(m_plot, decay_exp(m_plot, **fit_dict), "r--", label="p0 fit")

        # annotate
        fr = node.results["fit_results"][qq]
        txt = f"RB fidelity = {1 - fr['EPG']:.5f}"
        p2fit = fr.get("p2_fit", {})
        if isinstance(p2fit, dict) and "gamma" in p2fit:
            txt += f"\nleak gamma = {p2fit['gamma']:.2e}"
        ax.text(0.02, 0.98, txt, transform=ax.transAxes, va="top")

        ax.legend(fontsize=8, loc="best")

    plt.tight_layout()
    plt.show()

    # Store figure if your Qualibrate setup supports it; if it breaks JSON, remove this line.
    node.results["figure"] = grid.fig

    # %% {Save_results}
    node.outcomes = {q.name: "successful" for q in qubits}
    node.results["initial_parameters"] = node.parameters.model_dump()
    node.machine = machine
    node.save()


# =============================================================================
# IMPORTANT NOTE ABOUT 3-STATE READOUT
# =============================================================================
# This node assumes quam_libs.macros.readout_state(qubit, state_var) writes 0/1/2 labels into `state_var`.
# If your current readout_state only outputs 0/1, you must either:
#   (1) update readout_state to use your matched_filter_W/C and return 0/1/2, OR
#   (2) save I/Q here and run your classify_iq() in Python post-processing.
#
# Your Python-side classifier:
#
# def classify_iq(I, Q, qubit_resonator, mode="auto") -> int:
#     ...
#
# is great for offline classification, but it cannot run inside QUA.
# =============================================================================
