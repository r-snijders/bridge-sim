"""Plots for individual vehicles."""
import matplotlib.image as mpimg

from bridge_sim.model import Config
from bridge_sim.vehicles import truck1
from lib.plot.vehicle import topview_vehicle
from lib.plot import plt


def wagen1_plot(c: Config):
    """Plot of wagen1 compared to given specification."""
    plt.landscape()

    wheel_print = (0.31, 0.25)
    wheel_prints = []
    for w_i in range(len(truck1.axle_distances) + 1):
        if w_i in [1, 2]:
            wheel_prints.append([wheel_print, wheel_print])
        else:
            wheel_prints.append([wheel_print])

    plt.subplot(1, 2, 1)
    xlim, ylim = topview_vehicle(truck1, wheel_prints=wheel_prints)
    plt.title("Truck 1 specification")
    plt.xlabel("Width (m)")
    plt.ylabel("Length (m)")

    plt.subplot(1, 2, 2)
    topview_vehicle(truck1, xlim=xlim, ylim=ylim)
    plt.title("Truck 1 in simulation")
    plt.xlabel("Width (m)")
    plt.ylabel("Length (m)")

    plt.savefig(c.get_image_path("vehicles", "wagen-1", bridge=False) + ".pdf")
    plt.close()
