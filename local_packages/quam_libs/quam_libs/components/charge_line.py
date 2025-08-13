from quam.components import SingleChannel
from quam.components.ports import LFFEMAnalogOutputPort
from quam.core import quam_dataclass
from dataclasses import field
from typing import Dict, Any


__all__ = ["ChargeLine"]


@quam_dataclass
class ChargeLine(SingleChannel):
    """QuAM component for a charge line.

    Args:
        settle_time: the charge line settle time
    """

    settle_time: float = 16.
    max_offset: float = 0.0

    def settle(self):
        """Wait for the charge bias to settle"""
        if self.settle_time is not None:
            self.wait(int(self.settle_time) // 4 * 4)

    def to_zero(self):
        """Set the charge bias to 0.0 V"""
        self.set_dc_offset(0.0)
