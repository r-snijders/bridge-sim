import numpy as np

from classify.data.responses import responses_to_traffic_array
from classify.data.responses.convert import loads_to_traffic_array
from classify.scenario.bridge import HealthyDamage, pier_disp_damage, transverse_crack
from classify.scenarios import healthy_scenario
from classify.vehicle import wagen1
from classify import temperature, without
from config import Config
from model.bridge import Point
from model.load import PointLoad
from model.response import ResponseType
from fem.params import SimParams
from fem.responses import Responses, load_fem_responses
from fem.run.opensees import OSRunner
from plot import equal_lims, plt
from plot.geometry import top_view_bridge
from plot.responses import plot_contour_deck
from bridge_sim.util import clean_generated, flatten, print_i, print_s
from validate.campaign import displa_sensor_xz, strain_sensor_xz


def density_no_effect(c: Config):
    """Output maximum and minimum fem with different density values."""
    response_types = [ResponseType.YTranslation, ResponseType.Strain]
    pload = PointLoad(x_frac=0.5, z_frac=0.5, kn=100)
    c.bridge.type = "debugging"

    def set_density(density):
        for section in c.bridge.sections:
            print(section.density)
            section.density = density
        for pier in c.bridge.supports:
            if not callable(pier._sections):
                raise ValueError("Experiment requires callable pier sections")
            original_sections = pier._sections

            def new_sections(section_frac_len):
                section = original_sections(section_frac_len)
                section.density = density
                return section

            pier._sections = new_sections

    for density in [0.2, 100]:
        clean_generated(c)
        set_density(density)
        for response_type in response_types:
            sim_params = SimParams(response_types=[response_type], ploads=[pload],)
            sim_responses = load_fem_responses(
                c=c,
                sim_runner=OSRunner(c),
                response_type=response_type,
                sim_params=sim_params,
                run=True,
            )
            amax, amin = max(sim_responses.values()), min(sim_responses.values())
            print_s(f"Density's ratio = {density}")
            print_s(f"Max {response_type.name()} = {amax}")
            print_s(f"Min {response_type.name()} = {amin}")


def truck_1_time_series(c: Config):
    """Time series of 3 sensors to Truck 1's movement."""
    side_s = 7
    side = int(side_s * (1 / c.sensor_hz))
    assert wagen1.x_at(time=0, bridge=c.bridge) == 0
    # Get times and loads for Truck 1.
    end_time = wagen1.time_left_bridge(c.bridge)
    wagen1_times = np.linspace(
        -end_time, end_time * 2, int((end_time * 3) / c.sensor_hz)
    )
    print_i("Calculating Truck 1 loads")
    wagen1_loads = [
        flatten(wagen1.to_wheel_track_loads(c=c, time=time), PointLoad)
        # flatten(wagen1.to_point_load_pw(time=time, bridge=c.bridge), PointLoad)
        for time in wagen1_times
    ]
    print_i("Calculated Truck 1 loads")

    def set_labels(ylabel: str, xlabel: str):
        for i, y, x in [
            (1, True, False),
            (2, False, False),
            (3, True, False),
            (4, False, False),
            (5, True, True),
            (6, False, True),
        ]:
            plt.subplot(3, 2, i)
            ax = plt.gca()
            if y:
                plt.ylabel(ylabel)
            else:
                ax.axes.yaxis.set_ticklabels([])
            if x:
                plt.xlabel(xlabel)
            ax.axes.xaxis.set_ticklabels([])
        ymin, ymax = np.inf, -np.inf
        for i in range(1, 6 + 1):
            plt.subplot(3, 2, i)
            ymin = min(ymin, plt.ylim()[0])
            ymax = max(ymax, plt.ylim()[1])
        for i in range(1, 6 + 1):
            plt.subplot(3, 2, i)
            plt.ylim((ymin, ymax))

    ################
    # Vert. trans. #
    ################

    plt.portrait()
    # Find points of each sensor.
    displa_labels = ["U13", "U26", "U29"]
    displa_points = [
        Point(x=sensor_x, y=0, z=sensor_z)
        for sensor_x, sensor_z in [
            displa_sensor_xz(displa_label) for displa_label in displa_labels
        ]
    ]
    # Ensure points and truck are on the same lane.
    assert all(p.z < 0 for p in displa_points)
    # Results from simulation.
    responses_truck1 = responses_to_traffic_array(
        c=c,
        traffic_array=loads_to_traffic_array(c=c, loads=wagen1_loads),
        response_type=ResponseType.YTranslation,
        damage_scenario=healthy_scenario,
        points=displa_points,
    ).T
    for s_i, sensor_responses in enumerate(responses_truck1):
        plt.subplot(len(displa_points), 2, (s_i * 2) + 1)
        # Find the center of the plot, minimum point in the data.
        data_center = 0
        for i in range(len(sensor_responses)):
            if sensor_responses[i] < sensor_responses[data_center]:
                data_center = i
        # sensor_responses = add_displa_noise(sensor_responses) * 1000
        sensor_responses = sensor_responses * 1000
        plt.plot(sensor_responses[data_center - side : data_center + side])
        plt.title(f"{displa_labels[s_i]} in simulation")
    # Results from experiment.
    side = int(side / ((1 / c.sensor_hz) / 100))
    print_i(f"{side} points each side of center")
    for s_i, displa_label in enumerate(displa_labels):
        plt.subplot(len(displa_points), 2, (s_i * 2) + 2)
        with open(f"validation/experiment/D1a-{displa_label}.txt") as f:
            data = list(map(float, f.readlines()))
        side_expt = int(side_s * (len(data) / 240))
        # Find the center of the plot, minimum point in first 15000 points.
        data_center = 0
        for i in range(15000):
            if data[i] < data[data_center]:
                data_center = i
        plt.plot(data[data_center - side_expt : data_center + side_expt])
        plt.title(f"{displa_label} in dynamic test")
    set_labels("Y translation (mm)", "Time")
    plt.tight_layout()
    plt.savefig(c.get_image_path("validation/truck-1", "time-series-vert-trans.pdf"))
    plt.close()

    ##########
    # Strain #
    ##########

    plt.portrait()
    # Find points of each sensor.
    strain_labels = ["T1", "T10", "T11"]
    strain_points = [
        Point(x=sensor_x, y=0, z=sensor_z)
        for sensor_x, sensor_z in [
            strain_sensor_xz(strain_label) for strain_label in strain_labels
        ]
    ]
    # Results from simulation.
    responses_truck1 = responses_to_traffic_array(
        c=c,
        traffic_array=loads_to_traffic_array(c=c, loads=wagen1_loads),
        response_type=ResponseType.Strain,
        damage_scenario=healthy_scenario,
        points=strain_points,
    ).T
    for s_i, sensor_responses in enumerate(responses_truck1):
        plt.subplot(len(strain_points), 2, (s_i * 2) + 1)
        # Find the center of the plot, minimum point in the data.
        data_center = 0
        for i in range(len(sensor_responses)):
            if sensor_responses[i] > sensor_responses[data_center]:
                data_center = i
        # sensor_responses = add_strain_noise(sensor_responses)
        # plt.plot(sensor_responses)
        plt.plot(sensor_responses[data_center - side : data_center + side])
        # plt.plot(sensor_responses[data_center - side : data_center + side])
        plt.title(f"{strain_labels[s_i]} in simulation")
    # Results from experiment.
    print_i(f"{side} points each side of center")
    for s_i, strain_label in enumerate(strain_labels):
        plt.subplot(len(strain_points), 2, (s_i * 2) + 2)
        with open(f"validation/experiment/D1a-{strain_label}.txt") as f:
            data = list(map(float, f.readlines()))
        side_expt = int(side_s * (len(data) / 240))
        # Find the center of the plot, minimum point in first 15000 points.
        data_center = 0
        for i in range(15000):
            if data[i] < data[data_center]:
                data_center = i
        # plt.plot(data)
        plt.plot(data[data_center - side_expt : data_center + side_expt])
        # plt.plot(data[data_center - side_expt : data_center + side_expt])
        plt.title(f"{strain_label} in dynamic test")
    set_labels("Microstrain", "Time")
    plt.tight_layout()
    plt.savefig(c.get_image_path("validation/truck-1", "time-series-strain.pdf"))
    plt.close()


def stress_strength_plot(c: Config, top: bool):
    """Plot the difference of tensile strength and stress under load."""
    original_c = c
    plt.portrait()
    response_type = ResponseType.StrainT if top else ResponseType.Strain
    settlement = 3
    temp_bottom, temp_top = 21, 30
    deck_points = [
        Point(x=x, y=0, z=z)
        for x in np.linspace(
            # c.bridge.x_min, c.bridge.x_max, num=10
            c.bridge.x_min,
            c.bridge.x_max,
            num=int(c.bridge.length * 3),
        )
        for z in np.linspace(
            # c.bridge.z_min, c.bridge.z_max, num=10
            c.bridge.z_min,
            c.bridge.z_max,
            num=int(c.bridge.width * 3),
        )
    ]

    # Pier settlement.
    plt.subplot(3, 1, 1)
    c, sim_params = pier_disp_damage([(9, settlement / 1000)]).use(original_c)
    responses = (
        load_fem_responses(
            c=c,
            sim_runner=OSRunner(c),
            response_type=response_type,
            sim_params=sim_params,
        )
        .resize()
        .to_stress(c.bridge)
    )
    top_view_bridge(bridge=c.bridge, compass=False, abutments=True, piers=True)
    plot_contour_deck(c=c, responses=responses, decimals=2)
    plt.legend(loc="upper right", borderaxespad=0)
    plt.title(f"{settlement} mm pier settlement")
    print("Calculated stress from pier settlement")

    # Temperature effect.
    plt.subplot(3, 1, 2)
    c = original_c
    print(f"deck_points.shape = {np.array(deck_points).shape}")
    temp_effect = temperature.effect(
        c=c,
        response_type=response_type,
        points=deck_points,
        temps_bt=([temp_bottom], [temp_top]),
    ).T[0]
    print(f"temp_effect.shape = {np.array(temp_effect).shape}")
    responses = (
        Responses(
            response_type=response_type,
            responses=[
                (temp_effect[p_ind], deck_points[p_ind])
                for p_ind in range(len(deck_points))
                if not np.isnan(temp_effect[p_ind])
            ],
        )
        .without(remove=without.edges(c=c, radius=2))
        .to_stress(c.bridge)
    )
    top_view_bridge(c.bridge, compass=False, abutments=True, piers=True)
    plot_contour_deck(c=c, responses=responses, decimals=2)
    plt.legend(loc="upper right", borderaxespad=0)
    plt.title(f"T_bot, T_top = {temp_bottom}°C, {temp_top}°C")
    # plt.title(f"{top_str} stress\nbottom, top = {temp_bottom}, {temp_top}")
    print("Calculated stress from temperature")

    # Cracked concrete.
    plt.subplot(3, 1, 3)
    time = wagen1.time_at(x=52, bridge=c.bridge)
    print(f"wagen1.total_kn() = {wagen1.kn}")
    wagen1.kn = 400
    loads = wagen1.to_wheel_track_loads(c=c, time=time, flat=True)
    c, sim_params = transverse_crack().use(original_c)

    c, sim_params = HealthyDamage().use(original_c)
    sim_params.ploads = loads
    responses = (
        load_fem_responses(
            c=c,
            sim_runner=OSRunner(c),
            response_type=response_type,
            sim_params=sim_params,
        )
        .resize()
        .to_stress(c.bridge)
    )
    top_view_bridge(bridge=c.bridge, compass=False, abutments=True, piers=True)
    plot_contour_deck(c=c, responses=responses, decimals=2)
    plt.legend(loc="upper right", borderaxespad=0)
    # plt.title(f"Top stress: cracked concrete\nunder a {int(wagen1.kn)} kN vehicles")
    plt.title(f"{int(wagen1.total_kn())} kN vehicle")

    plt.suptitle(f"Stress {response_type.ss_direction()} for 3 scenarios")
    equal_lims("x", 3, 1)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(
        original_c.get_image_path(
            "validation", f"stress-strength-{response_type.name()}.pdf"
        )
    )
    plt.close()
