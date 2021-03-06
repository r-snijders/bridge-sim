"""Plot fem on a bridge.

Functions characterized by receiving 'FEMResponses' and 'PointLoad'.

"""
from typing import Callable, List, Optional, Tuple

import numpy as np
from scipy.stats import chisquare

from bridge_sim.model import ResponseType, Point, Config, PointLoad
from bridge_sim.sim.build import get_bridge_nodes, det_nodes
from bridge_sim.sim.model import Responses
from lib.plot import default_cmap, legend_marker_size, plt
from bridge_sim.util import print_w


def plot_deck_sensors(c: Config, without: Callable[[Point], bool], label: bool = False):
    """Scatter plot of deck sensors."""
    deck_nodes, _ = get_bridge_nodes(c.bridge)
    deck_nodes = det_nodes(deck_nodes)
    unavail_nodes = []
    avail_nodes = []
    for node in deck_nodes:
        if without(Point(x=node.x, y=node.y, z=node.z)):
            unavail_nodes.append(node)
        else:
            avail_nodes.append(node)
    X, Z, H = [], [], []  # 2D arrays, x and z coordinates, and height.
    for node in deck_nodes:
        X.append(node.x)
        Z.append(node.z)
        if without(Point(x=node.x, y=node.y, z=node.z)):
            H.append(1)
        else:
            H.append(0)
    plt.scatter(
        [node.x for node in avail_nodes],
        [node.z for node in avail_nodes],
        s=5,
        color="#1f77b4",
    )
    plt.scatter(
        [node.x for node in unavail_nodes],
        [node.z for node in unavail_nodes],
        color="#ff7f0e",
        s=5,
    )
    if label:
        plt.scatter(
            [avail_nodes[0].x],
            [avail_nodes[0].z],
            color="#1f77b4",
            label="Available",
            s=5,
        )
        plt.scatter(
            [unavail_nodes[0].x],
            [unavail_nodes[0].z],
            color="#ff7f0e",
            label="Unavailable",
            s=5,
        )
        legend = plt.legend()
        legend_marker_size(legend, 50)


def plot_distributions(
    response_array: List[float],
    response_type: ResponseType,
    titles: List[str],
    save: str,
    cols: int = 5,
    expected: List[List[float]] = None,
    xlim: Optional[Tuple[float, float]] = None,
):
    # Transpose so points are indexed first.
    response_array = response_array.T
    # response_array, unit_str = resize_and_units(response_array, response_type)
    num_points = response_array.shape[0]
    amax, amin = np.amax(response_array), np.amin(response_array)

    # Determine the number of rows.
    rows = int(num_points / cols)
    if rows != num_points / cols:
        print_w(f"Cols don't divide number of points {num_points}, cols = {cols}")
        rows += 1

    # Plot fem.
    for i in range(num_points):
        plt.subplot(rows, cols, i + 1)
        plt.xlim((amin, amax))
        plt.title(titles[i])
        label = None
        if expected is not None:
            if response_array.shape != expected.shape:
                expected = expected.T
                expected, _ = resize_and_units(expected, response_type)
            assert response_array.shape == expected.shape
            label = chisquare(response_array[i], expected[i])
        plt.hist(response_array[i], label=label)
        if label is not None:
            plt.legend()
        if xlim is not None:
            plt.xlim(xlim)

    plt.savefig(save)
    plt.close()


def plot_contour_deck(
    c: Config,
    responses: Responses,
    point_loads: List[PointLoad] = [],
    units: Optional[str] = None,
    cmap=default_cmap,
    norm=None,
    scatter: bool = False,
    levels: int = 14,
    mm_legend: bool = True,
    mm_legend_without_f: Optional[Callable[[Point], bool]] = None,
    sci_format: bool = False,
    decimals: int = 4,
    y: float = 0,
):
    """Contour or scatter plot of simulation responses.

    Args:
        config: simulation configuration object.
        responses: the simulation responses to plot.
        units: optional units string for the colourbar.
        cmap: Matplotlib colormap to use for colouring responses.
        norm: Matplotlib norm to use for colouring responses.
        scatter: scatter plot instead of contour plot?
        levels: levels in the contour plot.
        mm_legend: plot a legend of min and max values?
        mm_legend_without_f: function to filter points considered in the legend.
        sci_format: force scientific formatting (E) in the legend.
        decimals: round legend values to this many decimals.

    """
    amax, amax_x, amax_z = -np.inf, None, None
    amin, amin_x, amin_z = np.inf, None, None
    X, Z, H = [], [], []  # 2D arrays, x and z coordinates, and height.
    # Begin structure data.
    def structure_data(responses):
        nonlocal amax
        nonlocal amax_x
        nonlocal amax_z
        nonlocal amin
        nonlocal amin_x
        nonlocal amin_z
        nonlocal X
        nonlocal Z
        nonlocal H
        # First reset the maximums and minimums.
        amax, amax_x, amax_z = -np.inf, None, None
        amin, amin_x, amin_z = np.inf, None, None
        X, Z, H = [], [], []
        for x in responses.xs:
            # There is a chance that no sensors exist at given y position for every
            # x position, thus we must check.
            if y in responses.zs[x]:
                for z in responses.zs[x][y]:
                    X.append(x)
                    Z.append(z)
                    H.append(responses.responses[0][x][y][z])
                    if H[-1] > amax:
                        amax = H[-1]
                        amax_x, amax_z = X[-1], Z[-1]
                    if H[-1] < amin:
                        amin = H[-1]
                        amin_x, amin_z = X[-1], Z[-1]
        print(f"amin, amax = {amin}, {amax}")

    structure_data(responses)
    if len(X) == 0:
        raise ValueError(f"No fem for contour plot")

    # Plot fem, contour or scatter plot.
    if scatter:
        cs = plt.scatter(
            x=np.array(X).flatten(),
            y=np.array(Z).flatten(),
            c=np.array(H).flatten(),
            cmap=cmap,
            norm=norm,
            s=1,
        )
    else:
        cs = plt.tricontourf(X, Z, H, levels=levels, cmap=cmap, norm=norm)

    # Colourbar, maybe using given norm.
    clb = plt.colorbar(cs, norm=norm)
    if units is not None:
        clb.ax.set_title(units)

    # Plot point loads.
    for pload in point_loads:
        x = pload.x
        z = pload.z
        plt.scatter(
            [x], [z], label=f"{pload.load} kN load", marker="o", color="black",
        )

    # Begin: min, max legend.
    if mm_legend or mm_legend_without_f is not None:
        if mm_legend_without_f is not None:
            structure_data(responses.without(mm_legend_without_f))
        # Plot min and max fem.
        amin_s = (
            f"{amin:.{decimals}g}" if sci_format else f"{np.around(amin, decimals)}"
        )
        amax_s = (
            f"{amax:.{decimals}g}" if sci_format else f"{np.around(amax, decimals)}"
        )
        aabs_s = (
            f"{amin - amax:.{decimals}g}"
            if sci_format
            else f"{np.around(abs(amin - amax), decimals)}"
        )
        units_str = "" if units is None else f" {units}"
        print(units_str)
        for point, label, color, alpha in [
            ((amin_x, amin_z), f"min = {amin_s} {units_str}", "orange", 0),
            ((amax_x, amax_z), f"max = {amax_s} {units_str}", "green", 0),
            ((amin_x, amin_z), f"|min-max| = {aabs_s} {units_str}", "red", 0),
        ]:
            plt.scatter(
                [point[0]],
                [point[1]],
                label=label,
                marker="o",
                color=color,
                alpha=alpha,
            )
    # End: min, max legend.

    plt.xlabel("X position")
    plt.ylabel("Z position")
