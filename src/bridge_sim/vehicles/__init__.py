"""Provided instances of the Vehicle class."""

from bridge_sim.model import Vehicle
from bridge_sim.util import kg_to_kn

truck1 = Vehicle(
    kn=[
        (5050 * kg_to_kn, 5300 * kg_to_kn),
        (4600 * kg_to_kn, 4000 * kg_to_kn),
        (4350 * kg_to_kn, 3700 * kg_to_kn),
        (4050 * kg_to_kn, 3900 * kg_to_kn),
    ],
    axle_distances=[3.6, 1.32, 1.45],
    axle_width=2.5,
    # In dynamic test 'D1a' the speed was 20 kmph.
    kmph=20,
)
"""Truck 1 from the experimental campaign."""

assert truck1.lane == 0
assert truck1.init_x_frac == 0


__all__ = ["truck1"]
