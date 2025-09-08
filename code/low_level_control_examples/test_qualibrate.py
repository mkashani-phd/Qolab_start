"""
This program performs minimal QUA program (same as test_qua_execution.py) on qualibrate.

When it runs properly, the result will be saved on the location specified in qualibate config.
"""

# %% {Imports}
from qualibrate import QualibrationNode, NodeParameters
from quam_libs.components import QuAM
from qualang_tools.multi_user import qm_session
from qm import qua
from typing import Optional, List

# %% {Node_parameters}
class Parameters(NodeParameters):
    qubits: Optional[List[str]] = 'q1'

node = QualibrationNode(name="test_node", parameters=Parameters())

# %% {Initialize_QuAM_and_QOP}
machine = QuAM.load()
config = machine.generate_config()
qmm = machine.connect()

# %% {QUA_program}
with qua.program() as qua_program:
    a = qua.declare(qua.fixed)
    r1 = qua.declare_stream()
    with qua.for_(a, 0, a < 1.1, a + 0.5):
        qua.save(a, r1)
    with qua.stream_processing():
        r1.save_all("r1")


# %% {Execute}
# Open a quantum machine to execute the QUA program
with qm_session(qmm, config, timeout=10) as qm:
    job = qm.execute(qua_program)

# %% {Data_fetching_and_dataset_creation}
res_handles = job.result_handles # Creates a result handle to fetch data from the OPX
res_handles.wait_for_all_values() # Waits (blocks the Python console) until all results are acquired
r1_st = res_handles.get("r1").fetch_all()
node.results = {"r1": r1_st} # Add the dataset to the node

# %% {Save_results}
node.results["initial_parameters"] = node.parameters.model_dump()
node.machine = machine
node.save()
print("Results saved")