"""Test classify.data.fem."""
import numpy as np

from bridge_sim.bridges.bridge_705 import bridge_705
from bridge_sim.configs import opensees_default
from bridge_sim.model import PointLoad
from bridge_sim.vehicles import truck1
from bridge_sim.traffic import x_to_wheel_track_index, loads_to_traffic_array
from bridge_sim.util import flatten

# Comment/uncomment to print debug statements for this file.
D: str = "classify.data.test_responses"
D: bool = False

c = opensees_default(bridge_705(0.5))
c.il_num_loads = 10
entering_time = truck1.time_entering_bridge(bridge=c.bridge)
entered_time = truck1.time_entered_bridge(bridge=c.bridge)
leaving_time = truck1.time_leaving_bridge(bridge=c.bridge)
left_time = truck1.time_left_bridge(bridge=c.bridge)


def test_x_to_wheel_track_index():
    wheel_track_index_f = x_to_wheel_track_index(c)
    bin_width = c.bridge.length / (c.il_num_loads - 1)
    assert wheel_track_index_f(c.bridge.x_min) == 0
    assert wheel_track_index_f(c.bridge.x_max) == c.il_num_loads - 1
    for x in np.linspace(c.bridge.x_min, c.bridge.x_max, 1000):
        wti = wheel_track_index_f(x)
        if x < c.bridge.x_min + (bin_width * 0.5):
            assert wti == 0
        elif x < c.bridge.x_min + (bin_width * 1.5):
            assert wti == 1
        elif x > c.bridge.x_max - (bin_width * 0.5):
            assert wti == c.il_num_loads - 1
        elif x > c.bridge.x_max - (bin_width * 1.5):
            assert wti == c.il_num_loads - 2
        else:
            assert wti not in [0, 1, c.il_num_loads - 2, c.il_num_loads - 1]
    assert wheel_track_index_f(c.bridge.x_min + bin_width + 0.001) == 1
    assert wheel_track_index_f(c.bridge.x_max - bin_width - 0.001) == c.il_num_loads - 2


def test_loads_to_traffic_array():
    # First with one point load per wheel.
    wagen1_loads = [
        flatten(truck1.to_point_load_pw(time=time, bridge=c.bridge), PointLoad)
        for time in np.linspace(entered_time, leaving_time, 1000)
    ]
    for row in loads_to_traffic_array(c=c, loads=wagen1_loads):
        assert sum(row) == truck1.total_kn()
    # Then with point loads based on wheel tracks.
    wagen1_loads = [
        flatten(truck1.to_wheel_track_loads(c=c, time=time), PointLoad)
        for time in np.linspace(entered_time, leaving_time, 1000)
    ]
    for row in loads_to_traffic_array(c=c, loads=wagen1_loads):
        assert np.isclose(sum(row), truck1.total_kn())


# def test_response_to_mv_vehicles():

#     # All lanes are the same, so no error should be raised.
#     mv_vehicles_gen = normal_traffic(c).mv_vehicles(lane=0)
#     mv_vehicles = [next(mv_vehicles_gen) for _ in range(2)]
#     response_to_mv_vehicles(
#         c=c,
#         mv_vehicles=mv_vehicles,
#         bridge_scenario=None,
#         time=1,
#         at=Point(x=1),
#         response_type=ResponseType.XTranslation,
#         fem_runner=OSRunner(c),
#     )

#     # Different lanes, so an error should be raised.
#     for i, mv_vehicle in enumerate(mv_vehicles):
#         mv_vehicle.lane = i
#     with pytest.raises(ValueError) as e:
#         response_to_mv_vehicles(
#             c=c,
#             mv_vehicles=mv_vehicles,
#             bridge_scenario=BridgeScenarioNormal(),
#             time=1,
#             at=Point(x=1),
#             response_type=ResponseType.XTranslation,
#             fem_runner=OSRunner(c),
#         )
#     assert "single lane" in str(e.value)
