from quam.core import quam_dataclass
from quam.components.pulses import DragCosinePulse
import numpy as np
# from typing import List, Literal, Optional, Required
# from .pulses import DragPulseCosine  # Qualibrate implements DragPulseCosine but it's not actually used!

# For definition of DragCosinePulse see .venv/lib/python3.12/site-packages/quam/components/pulses.py
# See also: local_packages/quam_libs/quam_libs/quam_builder/pulses.py
# Seemingly unused classes: local_packages/quam_libs/quam_libs/lib/pulses.py

@quam_dataclass
class FastDragPulse(DragCosinePulse):
    # axis_angle: Optional[float] = 0.0
    # amplitude: Optional[float] = 0.0
    # alpha: Optional[float] = 0.0
    # anharmonicity: Optional[float] = 0.0
    # detuning: Optional[float] = 0.0
    N: int = 4

    # Edit this function, maybe implement our own drag_cosine_pulse_waveforms
    # which is defined in .venv/lib/python3.12/site-packages/qualang_tools/config/waveform_tools.py
    def waveform_function(self):
        from qualang_tools.config.waveform_tools import drag_cosine_pulse_waveforms

        I, Q = drag_cosine_pulse_waveforms(
            amplitude=self.amplitude,
            length=self.length,
            alpha=self.alpha,
            anharmonicity=self.anharmonicity,
            detuning=self.detuning,
        )
        I, Q = np.array(I), np.array(Q)

        I_rot = I * np.cos(self.axis_angle) - Q * np.sin(self.axis_angle)
        Q_rot = I * np.sin(self.axis_angle) + Q * np.cos(self.axis_angle)

        return I_rot + 1.0j * Q_rot

    pass


@quam_dataclass
class HDDragPulse(DragCosinePulse):
    pass
