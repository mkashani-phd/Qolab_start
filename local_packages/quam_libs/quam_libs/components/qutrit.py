from quam.core import quam_dataclass
import numpy as np

from .transmon import Transmon
from .readout_resonator import ReadoutResonatorMW

__all__ = ["Qutrit"]

@quam_dataclass
class Qutrit(Transmon):
    flux_vs_freq_curve: list = None # [quadratic term, linear term, offset] describing parabolic fit near HFQ. Predicts 0-1 drive frequency at different fluxes.
    T1_state2: float = None
    pass

@quam_dataclass
class ReadoutResonatorMW3state(ReadoutResonatorMW):
    matched_filter_W: list = None
    matched_filter_C: list = None
    confusion_matrix_3x3: list = None
    # test_param: float = 0.0
    pass

def classify_iq(x,calibration):
    """3-state discriminator
    x: shape (2,) array [I, Q]
    calibration: dict containing fields "W" (3x3 numpy array) and "C" (3x1 numpy array) corresponding to "matched_filter_W"  and "matched_filter_C" from state.json
    returns: 0, 1, or 2
    """
    W = calibration['W']
    c = calibration['C']
    # scores g_k(x) = w_k^T x + c_k
    g = W @ x + c
    return int(np.argmax(g))

def classify_batch(X,calibration):
    """3-state discriminator (multiple I,Q inputs)
    Depends on having run 07d_IQ_Blobs_3state.py and saving the parameters to state.json.
    X: shape (N, 2)
    calibration: dict containing fields "W" (3x3 numpy array) and "C" (3x1 numpy array) corresponding to "matched_filter_W"  and "matched_filter_C" from state.json
    """
    return np.array([classify_iq(x,calibration) for x in X])

