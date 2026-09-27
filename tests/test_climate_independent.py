"""Independent raw-source/scalar acceptance for the P13 climate calculations.

References read original acquired GODAS Float32 Kelvin subsets with netCDF4.
They do not import source preparation, production means, or packing helpers.
Source comparisons are not independent ocean validation.
"""
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from api.case_store import CaseStore
from api.climate_store import ClimateStore
from api.instrument_store import InstrumentStore
from science.climate import ordered_mean, section_result, signed_difference, profile_from_section
from science.climate_contracts import ClimateQuery
from science.contracts import UnsupportedData

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "casepacks/climate"
MONTHS = (9, 10, 11)
YEARS = (2013, 2015, 2022)


@lru_cache(maxsize=31)
def raw(year):
    if not (ROOT / "data/raw/climate/field-acquisition.json").is_file():
        pytest.skip("Original climate field archive is not bundled; acquire it for independent source checks.")
    journal = json.loads((ROOT / "data/raw/climate/field-acquisition.json").read_text())
    item = next(row for row in journal["files"] if row.get("year") == year and row["archive_kind"] == "source_float32_subset_reconstructed_as_netcdf")
    path = ROOT / item["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    with netCDF4.Dataset(path) as data:
        data.set_auto_maskandscale(False)
        variable = data["pottmp"]
        assert variable.dimensions == ("time", "level", "lat", "lon")
        assert variable.dtype == np.dtype("float32")
        assert variable.units == "K" and variable.var_desc == "potential temperature"
        assert variable.statistic == "Monthly Mean"
        assert list(variable.valid_range) == [260, 310]
        kelvin = np.array(variable[:])
        coordinates = {name: np.array(data[name][:]) for name in ("time", "level", "lat", "lon")}
        dates = [value.strftime("%Y-%m-%d") for value in netCDF4.num2date(coordinates["time"], data["time"].units)]
    assert dates == [f"{year}-{month:02d}-01" for month in MONTHS]
    assert kelvin.shape == (3, 28, 30, 240)
    return kelvin, coordinates


def raw_celsius(year, month_index, z, y, x):
    value = float(raw(year)[0][month_index, z, y, x])
    return value - 273.15 if math.isfinite(value) and 260 <= value <= 310 else None


def scalar_mean(values):
    if any(value is None for value in values):
        return None
    # This independent correctly rounded summation is a numerical reference,
    # not the production fixed-order replay implementation.
    return math.fsum(values) / len(values)


def scalar_baseline(month, z, y, x):
    return scalar_mean([raw_celsius(year, month, z, y, x) for year in range(1991, 2021)])


def assert_value(actual, expected):
    if expected is None:
        assert actual is None or not math.isfinite(actual)
    else:
        assert actual is not None and math.isfinite(actual)
        assert actual == pytest.approx(expected, rel=0, abs=1e-12)


@pytest.fixture(scope="module")
def climate():
    assert (PACK / "manifest.json").is_file(), "Prepare the actual complete P13 pack before running scientific acceptance."
    cases = CaseStore(ROOT / "casepacks")
    return ClimateStore(cases, InstrumentStore(ROOT / "casepacks/instruments"))


@pytest.mark.parametrize("year", YEARS)
def test_native_source_definition_dates_depths_and_dateline(year):
    kelvin, axes = raw(year)
    assert axes["level"].tolist()[0] == 5 and axes["level"].tolist()[-1] == 459
    assert len(set(np.diff(axes["level"]).tolist())) > 1
    assert axes["lat"][15] == np.float32(0.16612949967384338)
    assert axes["lon"][100] == 140.5 and axes["lon"][-1] == 279.5
    assert axes["lon"][139] == 179.5 and axes["lon"][140] == 180.5
    assert np.all(np.diff(axes["lon"]) == 1)
    manifest = json.loads((ROOT / f"casepacks/pacific-godas-{year}-son/manifest.json").read_text())
    assert manifest["coordinates"]["longitude"] == axes["lon"][100:].astype(float).tolist()
    assert manifest["coordinates"]["depth_m"] == axes["level"].astype(float).tolist()
    assert manifest["variables"][0]["standard_name"] == "sea_water_potential_temperature"
    intervals = manifest["representations"]["temporal_support"]["intervals"]
    assert intervals[0] == [f"{year}-09-01T00:00:00Z", f"{year}-10-01T00:00:00Z"]
    assert intervals[-1] == [f"{year}-11-01T00:00:00Z", f"{year}-12-01T00:00:00Z"]


@pytest.mark.parametrize("year,expected_kelvin", [
    (2013, [296.7069091796875, 296.7618408203125, 298.5486755371094]),
    (2015, [301.28924560546875, 301.53948974609375, 301.1748046875]),
    (2022, [295.08599853515625, 295.3730773925781, 297.010009765625]),
])
def test_manually_transcribed_original_105m_210point5e_cells(climate, year, expected_kelvin):
    # These constants were read from the original acquired source before
    # looking at API results, at latitude 0.16612949967384338 N.
    assert raw(year)[0][:, 10, 15, 170].astype(float).tolist() == expected_kelvin
    for index, month in enumerate(MONTHS):
        analytical = climate.array("event", year, month)
        assert analytical[10, 15, 170] == expected_kelvin[index] - 273.15


@pytest.mark.parametrize("month", MONTHS)
def test_30_year_baseline_against_independent_scalar_source_sums(climate, month):
    baseline = climate.array("baseline", None, month)
    counts = climate.array("baseline_count", None, month)
    for z, y, x in ((0, 0, 0), (0, 15, 30), (27, 15, 55), (10, 15, 99), (10, 15, 100), (10, 15, 139), (10, 15, 140), (10, 15, 170), (27, 15, 239)):
        values = [raw_celsius(year, month - 9, z, y, x) for year in range(1991, 2021)]
        count = sum(value is not None for value in values)
        assert counts[z, y, x] == count
        assert_value(baseline[z, y, x], scalar_mean(values))
    # Independently derive missing support from all raw cells, including land.
    raw_counts = np.zeros((28, 30, 240), dtype=np.int64)
    for year in range(1991, 2021):
        field = raw(year)[0][month - 9]
        raw_counts += (np.isfinite(field) & (field >= 260) & (field <= 310)).astype(np.int64)
    np.testing.assert_array_equal(counts, raw_counts)
    np.testing.assert_array_equal(np.isfinite(baseline), raw_counts == 30)
    assert np.any(raw_counts < 30), "Missing land support must remain represented."


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("period", ["09", "10", "11", "SON"])
def test_output_temperature_anomaly_and_selected_minus_reference_from_raw_sources(climate, year, period):
    months = (0, 1, 2) if period == "SON" else (int(period) - 9,)
    result = climate.analyse(ClimateQuery(event_id=f"son-{year}", reference_event_id="son-2013", period=period, longitude_index=70, depth_index=10))
    point = result["selected_point"]
    reference = scalar_mean([raw_celsius(2013, index, 10, 15, 170) for index in months])
    selected = scalar_mean([raw_celsius(year, index, 10, 15, 170) for index in months])
    baseline = scalar_mean([scalar_baseline(index, 10, 15, 170) for index in months])
    assert point["longitude"] == 210.5 and point["depth_m"] == 105
    assert point["latitude"] == 0.16612949967384338
    assert_value(point["selected"]["potential_temperature_c"], selected)
    assert_value(point["reference"]["potential_temperature_c"], reference)
    assert_value(point["selected"]["baseline_c"], baseline)
    assert_value(point["selected"]["anomaly_c"], selected - baseline)
    assert_value(point["difference_c"], selected - reference)
    assert result["period"]["aggregation"] == "equal_weight_complete_month_mean"
    for panel in result["panels"]:
        yr = panel["event"]["year"]
        assert panel["period_start"] == f"{yr}-{months[0]+9:02d}-01T00:00:00Z"
        assert panel["period_end_exclusive"] == f"{yr}-{months[-1]+10:02d}-01T00:00:00Z"
        assert panel["pacific"]["longitude"] == [140.5 + i for i in range(140)]
        assert panel["indian"]["longitude"] == [40.5 + i for i in range(70)]
        assert panel["pacific"]["shape"] == [28, 140]
        assert panel["indian"]["shape"] == [28, 70]
        for item in result["observations"]:
            if item["event_id"] != panel["event"]["event_id"]:
                continue
            for profile in item["profiles"]:
                assert panel["period_start"] <= profile["time"] < panel["period_end_exclusive"]


@pytest.mark.parametrize("year", YEARS)
def test_common_workspace_native_field_matches_original_source_without_reordering(climate, year):
    case_id = f"pacific-godas-{year}-son"
    for month in (0, 1, 2):
        original = raw(year)[0][month, :, :, 100:].astype(float)
        expected = np.where(np.isfinite(original) & (original >= 260) & (original <= 310), original - 273.15, np.nan)
        array = np.asarray(climate.cases._read_array(case_id, "analytical", "temperature", month)).reshape(28, 30, 140)
        np.testing.assert_array_equal(array, expected)


def test_land_holes_remain_missing_in_result_and_do_not_create_cold_ocean(climate):
    result = climate.analyse(ClimateQuery())
    for panel in result["panels"]:
        for basin in ("pacific", "indian"):
            section = panel[basin]
            offset = 100 if basin == "pacific" else 0
            for z, local_x in ((0, 0), (0, 35), (10, 40), (27, 65)):
                expected = scalar_mean([raw_celsius(panel["event"]["year"], index, z, 15, offset + local_x) for index in (0, 1, 2)])
                assert_value(section["potential_temperature_c"][z * section["shape"][1] + local_x], expected)
            for i, (value, baseline) in enumerate(zip(section["potential_temperature_c"], section["baseline_c"])):
                if value is None or baseline is None:
                    assert section["anomaly_c"][i] is None


def test_closed_form_equal_month_mean_is_not_day_weighted_or_missing_skipping():
    result = ordered_mean([np.array([0, 6, np.nan]), np.array([3, np.nan, 9]), np.array([6, 12, 15])])
    assert result[0] == 3
    assert math.isnan(result[1]) and math.isnan(result[2])
    assert ordered_mean([np.array([0]), np.array([31]), np.array([0])])[0] == 31 / 3
    assert ordered_mean([np.array([0]), np.array([31]), np.array([0])])[0] != 31 * 31 / 91


def test_signed_difference_has_defined_orientation_and_keeps_holes():
    result = signed_difference(np.array([8.0, np.nan, 3.0]), np.array([2.0, 7.0, np.nan]))
    assert result[0] == 6 and math.isnan(result[1]) and math.isnan(result[2])
    with pytest.raises(UnsupportedData):
        signed_difference(np.zeros(2), np.zeros(3))


def test_section_native_depth_and_dateline_geometry_no_synthetic_zero_row():
    # A closed-form hand-labeled geometry catches axis transposes and invented
    # interpolation. The nearest source latitude is +0.2, not exactly zero.
    values = np.array([[[1, 2, 3], [4, 5, 6]], [[11, 12, 13], [14, 15, 16]], [[21, 22, 23], [24, 25, 26]]], dtype=float)
    values[1, 1, 1] = np.nan
    section = section_result(values, np.ones_like(values), [-0.7, 0.2], [179.5, 180.5, 181.5], [5, 35, 105], 179, 182)
    assert section["latitude"] == 0.2 and section["depth_m"] == [5, 35, 105]
    assert section["longitude"] == [179.5, 180.5, 181.5]
    assert section["potential_temperature_c"] == [4, 5, 6, 14, None, 16, 24, 25, 26]
    assert profile_from_section(section, 1)["potential_temperature_c"] == [5, None, 25]
    assert section["anomaly_c"] == [3, 4, 5, 13, None, 15, 23, 24, 25]
    assert ((section["longitude"][1] + 180) % 360) - 180 == -179.5


def test_missing_shape_and_outside_section_are_rejected():
    with pytest.raises(UnsupportedData):
        ordered_mean([])
    with pytest.raises(UnsupportedData):
        ordered_mean([np.zeros(2), np.zeros(3)])
    with pytest.raises(UnsupportedData):
        section_result(np.zeros((1, 1, 1)), np.zeros((1, 1, 1)), [0], [180], [5], 10, 20)
    with pytest.raises(UnsupportedData):
        section_result(np.zeros((2, 1, 1)), np.zeros((1, 1, 1)), [0], [180], [5], 170, 190)
