"""Time series of temperature and responses to temperature."""

import datetime
import math
import os
from copy import deepcopy
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from scipy.interpolate import interp1d
from sklearn.linear_model import LinearRegression

from bridge_sim.model import Config, Point, ResponseType
from bridge_sim.scenarios import ThermalScenario
from bridge_sim.sim.responses import load_fem_responses
from bridge_sim.sim.run.opensees import OSRunner
from bridge_sim.util import print_d, print_i, project_dir

# D: str = "classify.temperature"
D: bool = False

# https://www1.ncdc.noaa.gov/pub/data/uscrn/products/subhourly01/2019/


def remove_sampled(num_samples, signal):
    """Interpolate between num_samples and subtract.

    Data must be of shape n samples x f features.
    """
    # 'num_samples + 1' indices into given signal.
    indices = list(map(int, np.linspace(0, len(signal) - 1, num_samples + 1)))
    # Mean value of the signal between each pair of indices,
    # and new indices, at center between each pair of indices.
    y_samples, new_indices = [], []
    for i_lo, i_hi in zip(indices[:-1], indices[1:]):
        y_samples.append(np.mean(signal[i_lo:i_hi]))
        new_indices.append(int((i_lo + i_hi) / 2))
    rm = interp1d(new_indices, y_samples, fill_value="extrapolate")(
        np.arange(len(signal))
    )
    return rm, deepcopy(rm) - rm[0]


def parse_line(line):
    # 23803 20190101 0005 20181231 1805      3  -89.43   34.82    12.4
    # 0.0      0 0    10.9 C 0    88 0 -99.000 -9999.0  1115 0   0.79 0
    line = line.split()
    ds = line[1]  # Date string.
    ts = line[2]  # Time string.
    year, mon, day, hr, mn = (ds[0:4], ds[4:6], ds[6:8], ts[0:2], ts[2:4])
    # 2011-11-04T00:05
    dt = datetime.fromisoformat(f"{year}-{mon}-{day}T{hr}:{mn}")
    return [dt, float(line[-15]), float(line[-13])]


def load(
    name: str, temp_quantile: Tuple[float, float] = (0.001, 0.999)
) -> pd.DataFrame:
    # If the file is already parsed, return it..
    name_path = os.path.join(project_dir(), "data/temperature", name + ".txt")
    saved_path = name_path + ".parsed"
    if os.path.exists(saved_path):
        df = pd.read_csv(saved_path, index_col=0, parse_dates=["datetime"])
        lq = df["temp"].quantile(temp_quantile[0])
        hq = df["temp"].quantile(temp_quantile[1])
        print(f"Temperature {temp_quantile} quantiles = {lq}, {hq}")
        df = df[(df["temp"] >= lq) & (df["temp"] <= hq)]
        return df
    # ..otherwise read and parse the data.
    with open(name_path) as f:
        temps = list(map(parse_line, f.readlines()))
    # Remove NANs.
    for line_ind, [dt, temp, solar] in enumerate(temps):
        if np.isnan(temp):
            print_i(f"NAN in {name} temperature")
            temps[line_ind][1] = temps[line_ind - 1][1]
        if np.isnan(solar):
            print_i(f"NAN in {name} solar radiation")
            temps[line_ind][2] = temps[line_ind - 1][2]
    # Pack it into a DataFrame.
    df = pd.DataFrame(temps, columns=["datetime", "temp", "solar"])
    # Convert to celcius.
    # df["temp"] = (df["temp"] - 32) * (5 / 9)
    # Remove duplicate times.
    len_before = len(df)
    df = df.drop_duplicates(subset=["datetime"], keep="first")
    len_after = len(df)
    print_i(f"Removed {len_before - len_after} duplicates, now {len_after} rows")
    # Sort.
    df = df.sort_values(by=["datetime"])
    # Save.
    df.to_csv(saved_path)
    return load(name=name)


def from_to_mins(df, from_, to, smooth: bool = False):
    # Create times and temperatures from given data.
    dates, temps, solar = df["datetime"], df["temp"], df["solar"]
    times = dates.apply(lambda d: datetime.timestamp(d))
    # Create times that are expected to return.
    result_dates, result_times = [], []
    curr = from_
    while curr <= to:
        result_dates.append(curr)
        result_times.append(datetime.timestamp(curr))
        curr += timedelta(minutes=1)
    # Interpolate to get results.
    result_temps = interp1d(times, temps, fill_value="extrapolate")(result_times)
    result_solar = interp1d(times, solar, fill_value="extrapolate")(result_times)
    # Pack it into a DataFrame.
    df = pd.DataFrame(
        np.array([result_dates, result_temps, result_solar]).T,
        columns=["datetime", "temp", "solar"],
    )
    # Sort.
    df = df.sort_values(by=["datetime"])
    df["temp"] = pd.to_numeric(df["temp"])
    df["solar"] = pd.to_numeric(df["solar"])
    # Smooth.
    if smooth:
        df["temp"] = savgol_filter(df["temp"], 20, 3)
    return df


def from_to_indices(df, from_, to):
    """Indices of temperatures that correspond to the given range."""
    start, end = None, None
    for i, date in enumerate(df["datetime"]):
        if start is None and date >= from_:
            start = i
        if date >= to:
            return start, i
    raise ValueError("End date not found")


def temps_bottom_top(c: Config, temps: List[float], solar: List[float], len_per_hour):
    """The top and bottom bridge temperatures for given air temperatures."""

    # temps_bottom = np.array(temps) - c.bridge.ref_temp_c
    # temps_top = temps_bottom + c.bridge.air_surface_temp_delta_c
    # return temps_bottom, temps_top

    bd = 0.001
    # bn = 0.008

    temps_b = [temps[0]]
    for i, temp_a in enumerate(temps[1:]):
        temps_b.append((1 - bd) * temps_b[i - 1] + bd * temp_a)

    recent_hours = 3
    sd = 0.008
    sn = 0.008
    ss = 0.0001
    temps_s = [temps[0]]

    for i, (temp_a, solar) in enumerate(zip(temps[1:], solar[1:])):
        recent_start = i - (len_per_hour * recent_hours)
        # if i > 1 and temps_b[i - 1] > temps_b[i - 2]:
        if False:
            recent_max = np.max(temps[max(0, recent_start) : i])
            temps_s.append((1 - sd) * temps_s[i - 1] + sd * recent_max)
        else:
            temps_s.append((1 - sn - ss) * temps_s[i - 1] + sn * temp_a + ss * solar)

    return np.array(temps_b), np.array(temps_s)


def effect(
    c: Config,
    response_type: ResponseType,
    points: List[Point],
    temps_bt: Optional[Tuple[List[float], List[float]]] = None,
    len_per_hour: Optional[int] = None,
    temps: Optional[List[float]] = None,
    solar: Optional[List[float]] = None,
    d: bool = False,
    ret_temps_bt: bool = False,
) -> List[List[float]]:
    """Temperature effect at given points for a number of given temperatures.

    The result is of shape (number of points, number of temperatures).

    NOTE: The 'ThermalDamage' method 'to_strain' multiplies the results by E-6,
        which is called by this function. So take note that the strain values
        are already multiplied by E-6 (from microstrain to strain), and do not
        need to be resized.

    Args:
        c: Config, global configuration object.
        response_type: ResponseType, type of sensor response to temp. effect.
        points: List[Point], points at which to calculate temperature effect.
        temps_bt: A 2-tuple of arrays, the first array is for the temperatures
            at the bottom of the bridge, and the second array is for the
            temperatures at the top of the bridge. If this argument is given
            then 'temps', 'solar', 'len_per_hour' must not be given.
        len_per_hour: Optional[int], if given then temps and solar must also be
            given. The temperature fem are interpolated such that there
            are 'len_per_hour' fem for every hour of temperature data. It
            is assumed the temperature data is one data point per minute.
        temps: Optional[List[float]], first see 'len_per_hour'. Air temperature
            data given at one data point per minute.
        solar: Optional[List[float]], first see 'len_per_hour'. Solar irradiance
            data given at one data point per minute, same as 'temps'.

    """
    if temps_bt is not None:
        if any(x is not None for x in [len_per_hour, temps, solar]):
            raise ValueError(
                "Must only pass 'temps_bt', or ('len_per_hour', 'temps' & 'solar')"
            )

    original_c = c
    # Unit effect from uniform temperature loading.
    unit_uniform = ThermalScenario(axial_delta_temp=c.unit_axial_delta_temp_c)
    c, sim_params = unit_uniform.use(original_c)
    uniform_responses = load_fem_responses(
        c=c, sim_runner=OSRunner, response_type=response_type, sim_params=sim_params,
    )
    # Unit effect from linear temperature loading.
    unit_linear = ThermalScenario(moment_delta_temp=c.unit_moment_delta_temp_c)
    c, sim_params = unit_linear.use(original_c)
    linear_responses = load_fem_responses(
        c=c, sim_runner=OSRunner, response_type=response_type, sim_params=sim_params,
    )
    print_i("Loaded unit uniform and linear temperature fem")

    # Convert uniform fem to correct type (thermal post-processing).
    if response_type in [
        ResponseType.Strain,
        ResponseType.StrainT,
        ResponseType.StrainZZB,
    ]:
        uniform_responses = unit_uniform.to_strain(c=c, sim_responses=uniform_responses)
    elif response_type == ResponseType.Stress:
        uniform_responses = unit_uniform.to_stress(c=c, sim_responses=uniform_responses)
    unit_uniforms = np.array(uniform_responses.at_decks(points))
    print(f"Unit uniform temperature per point, shape = {unit_uniforms.shape}")

    # Convert linear fem to correct type (thermal post-processing).
    if response_type in [
        ResponseType.Strain,
        ResponseType.StrainT,
        ResponseType.StrainZZB,
    ]:
        linear_responses = unit_linear.to_strain(c=c, sim_responses=linear_responses)
    elif response_type == ResponseType.Stress:
        linear_responses = unit_linear.to_stress(c=c, sim_responses=linear_responses)
    unit_linears = np.array(linear_responses.at_decks(points))

    # Determine temperature gradient throughout the bridge.
    if temps_bt is None:
        temps_bottom, temps_top = temps_bottom_top(
            c=c, temps=temps, solar=solar, len_per_hour=len_per_hour
        )
    else:
        temps_bottom, temps_top = temps_bt
        temps_bottom, temps_top = np.array(temps_bottom), np.array(temps_top)

    temps_half = (temps_bottom + temps_top) / 2
    temps_linear = temps_top - temps_bottom
    temps_uniform = temps_half - c.bridge.ref_temp_c

    # print(f"temps_bottom.shape = {temps_bottom.shape}")
    # print(f"temps_top.shape = {temps_top.shape}")
    # print(f"temps_half.shape = {temps_half.shape}")
    print_d(D, f"tb = {temps_bottom[:3]}")
    print_d(D, f"tt = {temps_top[:3]}")
    print_d(D, f"th = {temps_half[:3]}")
    print_d(D, f"temps linear = {temps_linear[:3]}")
    print_d(D, f"temps uniform = {temps_uniform[:3]}")

    # Combine uniform and linear fem.
    uniform_responses = np.array(
        [unit_uniform * temps_half for unit_uniform in unit_uniforms]
    )
    linear_responses = np.array(
        [unit_linear * temps_linear for unit_linear in unit_linears]
    )
    # print(f"uniform_responses.shape = {uniform_responses.shape}")
    # print(f"linear_responses.shape = {linear_responses.shape}")
    print_d(D, f"uniform fem = {uniform_responses[:3]}")
    print_d(D, f"linear fem = {linear_responses[:3]}")
    if d:
        return temps_uniform, temps_linear, uniform_responses + linear_responses
    if ret_temps_bt:
        return ((temps_bottom, temps_top), uniform_responses + linear_responses)
    return uniform_responses + linear_responses
    # return (np.array(temps) - c.bridge.ref_temp_c) * unit_response


def get_len_per_min(c: Config, speed_up: float):
    """Length of time series corresponding to 1 minute of temperature."""
    return int(np.around(((1 / c.sensor_hz) * 60) / speed_up, 0))


def resize(
    temps,
    tmin: Optional[int] = None,
    tmax: Optional[int] = None,
    year: Optional[int] = None,
):
    """Resize temperatures into a range."""
    if year is not None:
        if year == 2018:
            tmin, tmax = -2, 32
        elif year == 2019:
            tmin, tmax = -5, 35
        else:
            raise NotImplementedError(f"Uknown year {year}")
    # TODO: Remove, just a sanity check while I write my thesis.
    assert tmin < 0
    assert tmax > 30
    print(tmin, tmax)
    return interp1d(
        np.linspace(min(temps), max(temps), 1000), np.linspace(tmin, tmax, 1000)
    )(temps)


def apply(effect: List[float], responses: List[float]):
    """Given effect interpolated across given fem."""
    i = interp1d(
        np.linspace(0, len(responses) - 1, 10000),
        np.linspace(0, len(effect) - 1, 10000),
    )(np.arange(len(responses)))
    return interp1d(np.arange(len(effect)), effect)(i)


def apply_effect(
    c: Config,
    points: List[Point],
    responses: List[List[float]],
    effect: List[List[float]],
    speed_up: int = 1,
    repeat_responses: bool = False,
) -> List[float]:
    """Time series of effect due to temperature at given points.

    Returns: a NumPy array of shape the same as given fem. The effect due
        to temperature is interpolated across the date range of the given
        fem, this is calculated under the assumption that temperature
        effect is given at one data point per minute and that the sensor
        fem are given at a rate of 'c.sensor_hz'.

    """
    raise ValueError("Deprecated")
    assert len(responses) == len(points)
    # Convert the temperature data into temperature effect at each point.
    # effect_ = effect(c=c, response_type=response_type, points=points, temps=temps)
    assert len(effect) == len(points)
    # A temperature sample is available per minute. Here we calculate the
    # number of fem between each pair of recorded temperatures and the
    # number of temperature samples required for the given fem.
    len_per_min = get_len_per_min(c=c, speed_up=speed_up)
    print_i(f"Length per minute = {len_per_min}, speed_up = {speed_up}")
    num_temps_req = math.ceil(len(responses[0]) / len_per_min) + 1
    if num_temps_req > len(effect[0]):
        raise ValueError(
            f"Not enough temperatures ({len(effect[0])}) for data"
            f" (requires {num_temps_req})"
        )
    # If additional temperature data is available, then use it if requested and
    # repeat the given fem. Here we calculate length, in terms of the
    # sample frequency, recall that temperature is sampled every minute.
    avail_len = (len(effect[0]) - 1) * len_per_min
    if repeat_responses and (avail_len > len(responses[0])):
        print_i(f"Increasing length of fem from {len(responses[0])} to {avail_len}")
        num_temps_req = len(effect[0])
        new_responses = np.empty((len(responses), avail_len))
        for i in range(len(responses)):
            for j in range(math.ceil(avail_len / len(responses[0]))):
                start = j * len(responses[0])
                end = min(avail_len - 1, start + len(responses[0]))
                new_responses[i][start:end] = responses[i][: end - start]
        responses = new_responses
    # Fill in the fem array with the temperature effect.
    result = np.zeros((len(points), len(responses[0])))
    for i in range(len(points)):
        for j in range(num_temps_req - 1):
            start = j * len_per_min
            end = min(len(result[i]), start + len_per_min)
            print_d(D, f"start = {start}")
            print_d(D, f"end = {end}")
            print_d(D, f"end - start = {end - start}")
            # print_d(D, f"temp_start, temp_end = {temps[j]}, {temps[j + 1]}")
            print_d(D, f"effect_start, effect_end = {effect[i][j]}, {effect[i][j + 1]}")
            result[i][start:end] = np.linspace(
                effect[i][j], effect[i][j + 1], end - start
            )
    if repeat_responses:
        return responses, result
    return result


# Shorthand.
ij = lambda _t, _i, _j: from_to_indices(
    _t, datetime.fromisoformat(_i), datetime.fromisoformat(_j)
)


def regress_and_errors(x, y):
    """Linear regression predictor, and error from each given point."""
    lr = LinearRegression().fit(x.reshape(-1, 1), y)
    errors = []
    for x_, y_ in zip(x, y):
        errors.append(abs(y_ - lr.predict([[x_]])[0]))
    return lr, np.array(errors)
