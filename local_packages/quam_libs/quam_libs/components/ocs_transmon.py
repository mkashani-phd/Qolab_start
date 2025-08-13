from quam.core import quam_dataclass
from quam.components.channels import IQChannel, Pulse
from quam import QuamComponent

from .transmon import Transmon
from .flux_line import FluxLine
from .charge_line import ChargeLine
from .readout_resonator import ReadoutResonator
from qualang_tools.octave_tools import octave_calibration_tool
from qm import QuantumMachine, logger
from typing import Dict, Any, Optional, Union, List, Tuple
from qm.qua import align, wait
import numpy as np
from dataclasses import field

__all__ = ["OCSTransmon"]


@quam_dataclass
class OCSTransmon(Transmon):
    """
    Example QuAM component for an OCS transmon qubit.

    Args:
        id (str, int): The id of the Transmon, used to generate the name.
            Can be a string, or an integer in which case it will add`Channel._default_label`.
        xy (IQChannel): The xy drive component.
        z (FluxLine): The z drive component.
        c (ChargeLine): The z drive component using offset charge instead of flux
        resonator (ReadoutResonator): The readout resonator component.
        T1 (float): The transmon T1 in s.
        T2ramsey (float): The transmon T2* in s.
        T2echo (float): The transmon T2 in s.
        thermalization_time_factor (int): thermalization time in units of T1.
        anharmonicity (int, float): the transmon anharmonicity in Hz.
        freq_vs_flux_01_quad_term (float):
        arbitrary_intermediate_frequency (float):
        sigma_time_factor:
        phi0_current (float):
        phi0_voltage (float):
        GEF_frequency_shift (int):
        chi (float):
        grid_location (str): qubit location in the plot grid as "(column, row)"
    """

    c: ChargeLine = None
    e_voltage: float = 1.5
    max_charge_dispersion_MHz: float = 8.0#0.75

    def align(self):
        align(self.xy.name, self.z.name, self.c.name, self.resonator.name)

    def wait(self, duration):
        wait(duration, self.xy.name, self.z.name, self.c.name, self.resonator.name)
