"""Provided instances of the Config class."""

import os
from typing import Callable, Optional

from bridge_sim.model import Config, Bridge
from bridge_sim.sim.run.opensees import os_runner
from bridge_sim.util import project_dir


def opensees_default(
    bridge: Callable[[], Bridge], os_exe: Optional[str] = None, **kwargs
) -> Config:
    """A Config using OpenSees for a given Bridge.

    Args:
        bridge: function to return a new Bridge.
        os_exe: absolute path to OpenSees binary. Optional, if not given this
            will look for OpenSees on the $PATH.
        kwargs: keyword arguments passed to the Config constructor.
    """
    return Config(
        bridge=bridge,
        sim_runner=os_runner(os_exe),
        vehicle_data_path=os.path.join(project_dir(), "data/traffic/traffic.csv"),
        vehicle_pdf=[
            (2.4, 5),
            (5.6, 45),
            (7.5, 30),
            (9, 15),
            (11.5, 4),
            (12.2, 0.5),
            (43, 0),
        ],
        vehicle_pdf_col="length",
        **kwargs,
    )
