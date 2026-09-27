"""Source-record and temporal-boundary checks for P13 climate labels."""
from decimal import Decimal
import json
from pathlib import Path
import shutil

import pytest

from science.climate_indices import (
    RAW, ROOT, SEASONS, acquire, parse_cpc_dmi_ascii, parse_cpc_table,
    parse_psl_monthly, prepare, qualify_enso, qualifying_run, season_dates,
    seasonal_monthly_context, sha256,
)


def source(name):
    if not (RAW / name).is_file():
        pytest.skip("Original climate index snapshot is not bundled: " + name)
    return (RAW / name).read_text(encoding="utf-8")


def fixture_rows(values, start=2015 * 12):
    return [{"year": (start + i) // 12, "center_month": (start + i) % 12 + 1,
             "season": SEASONS[(start + i) % 12], "value_c": value}
            for i, value in enumerate(values)]


@pytest.mark.parametrize("name", ["cpc-oni-v5.html", "cpc-oni-v6.html", "cpc-roni-v6.html"])
def test_provider_labels_independently_match_all_chronological_runs(name):
    rows = qualify_enso(parse_cpc_table(source(name)))
    assert len(rows) == 77 * 12
    assert all(row["provider_phase"] == row["calculated_phase"] for row in rows)
    assert any(row["value_c"] is None for row in rows if row["year"] == 2026)


@pytest.mark.parametrize("name,expected", [
    ("cpc-oni-v5.html", [-0.1, 2.5, -0.9]),
    ("cpc-oni-v6.html", [-0.1, 2.3, -0.9]),
    ("cpc-roni-v6.html", [-0.2, 2.0, -1.1]),
])
def test_manual_provider_season_transcription(name, expected):
    rows = {(row["year"], row["season"]): row for row in parse_cpc_table(source(name))}
    assert [rows[(year, "SON")]["value_c"] for year in (2013, 2015, 2022)] == expected


def test_roni_separate_two_decimal_text_consistent_with_published_table_precision():
    table = {(row["year"], row["season"]): row for row in parse_cpc_table(source("cpc-roni-v6.html"))}
    count = 0
    for line in source("cpc-roni.txt").splitlines()[1:]:
        season, year, value = line.split()
        row = table[(int(year), season)]
        if row["value_c"] is not None:
            # Decimal arithmetic uses the actual displayed precision. We do
            # not round the two-decimal text to create a replacement label.
            assert abs(Decimal(str(row["value_c"])) - Decimal(value)) <= Decimal("0.05")
            count += 1
    assert count == 919


def test_separate_dmi_html_and_text_values_match_and_components_close_at_published_precision():
    table = {(row["year"], row["season"]): row for row in parse_cpc_table(source("cpc-dmi-v6.html"), "dmi")}
    values = parse_cpc_dmi_ascii(source("cpc-dmi-v6.txt"))
    # The source has two explicitly missing entries: its first DJF and its
    # latest JAS. Those remain rows rather than being dropped.
    assert len(values) == 920
    valid = 0
    for row in values:
        assert row["value_c"] == table[(row["year"], row["season"])]["value_c"]
        if row["value_c"] is not None:
            # Each of three published fields is rounded to 0.01 C; their
            # printed arithmetic can differ by 0.01 C. Preserve official DMI.
            a, b, c = [Decimal(str(row[key])) for key in ("wtio_c", "setio_c", "value_c")]
            assert abs(a - b - c) <= Decimal("0.01")
            valid += 1
    assert valid == 918
    assert {row["provider_phase"] for row in table.values()} <= {"positive", "negative", "within_threshold", "unavailable"}


@pytest.mark.parametrize("sign", [-1, 1])
def test_exact_threshold_needs_five_seasons(sign):
    assert all(row["calculated_phase"] == "neutral" for row in qualify_enso(fixture_rows([0.5 * sign] * 4)))
    result = qualify_enso(fixture_rows([0.5 * sign] * 5))
    assert {row["calculated_phase"] for row in result} == {"el_nino" if sign == 1 else "la_nina"}


@pytest.mark.parametrize("interrupt", [None, 0.49, -0.8])
def test_missing_neutral_and_opposite_season_break_the_run(interrupt):
    result = qualify_enso(fixture_rows([0.8] * 4 + [interrupt] + [0.8] * 4))
    assert not any(row["calculated_phase"] == "el_nino" for row in result)


def test_cross_year_qualification_is_continuous_and_missing_season_stops_it():
    rows = fixture_rows([0.7] * 5, start=2014 * 12 + 10)
    result = qualify_enso(rows)
    run = qualifying_run(result, 2015, "DJF")
    assert run["first"]["season"] == "OND" and run["first"]["year"] == 2014
    assert run["last"]["season"] == "FMA" and run["season_count"] == 5
    assert all(row["calculated_phase"] == "neutral" for row in qualify_enso(rows[:2] + rows[3:]))


def test_run_summary_does_not_join_qualified_runs_across_a_gap():
    rows = fixture_rows([0.7] * 5) + fixture_rows([0.7] * 5, start=2015 * 12 + 6)
    qualified = qualify_enso(rows)
    assert qualifying_run(qualified, 2015, "MAM")["season_count"] == 5


def test_out_of_order_and_duplicate_seasons_are_rejected():
    rows = fixture_rows([0.8] * 5)
    with pytest.raises(ValueError, match="chronological"):
        qualify_enso(list(reversed(rows)))
    with pytest.raises(ValueError, match="chronological"):
        qualify_enso(rows + rows[-1:])


@pytest.mark.parametrize("year,season,expected", [
    (2015, "SON", ["2015-09", "2015-10", "2015-11"]),
    (2015, "DJF", ["2014-12", "2015-01", "2015-02"]),
    (2015, "NDJ", ["2015-11", "2015-12", "2016-01"]),
])
def test_calendar_alignment(year, season, expected):
    assert season_dates(year, season)["months"] == expected


def test_missing_month_prevents_seasonal_context_mean():
    rows = [{"year": 2015, "month": 9, "value_c": 1.0}, {"year": 2015, "month": 11, "value_c": 3.0}]
    assert seasonal_monthly_context(rows, 2015, "SON")["mean_c"] is None
    rows.append({"year": 2015, "month": 10, "value_c": 2.0})
    assert seasonal_monthly_context(rows, 2015, "SON")["mean_c"] == 2.0


def test_psl_source_preserves_missing_sentinel_and_rejects_truncation():
    fixture = "2000 2000\n2000 1 2 3 4 5 6 7 8 9 10 -999 12\n-999\nDescription\n"
    assert parse_psl_monthly(fixture)[10]["value_c"] is None
    with pytest.raises(ValueError):
        parse_psl_monthly("2000 2001\n2000 1 2\n")


def test_cpc_omitted_tr_closing_tags_and_last_partial_year_are_preserved():
    first = "<tr><td>2020</td>" + "<td>0.0</td>" * 12
    second = "<tr><td>2021</td><td>0.1</td></tr>"
    rows = parse_cpc_table(first + second)
    assert len(rows) == 24 and rows[12]["value_c"] == 0.1 and rows[13]["value_c"] is None
    with pytest.raises(ValueError, match="historical"):
        parse_cpc_table(second.replace("2021", "2019") + first + "</tr>")


def test_cpc_duplicate_and_year_gap_rejected():
    row = "<tr><td>2020</td>" + "<td>0.0</td>" * 12 + "</tr>"
    with pytest.raises(ValueError, match="Duplicate"):
        parse_cpc_table(row + row)
    with pytest.raises(ValueError, match="gap"):
        parse_cpc_table(row + row.replace("2020", "2022"))


def test_iod_labels_are_separate_from_the_seasonal_numeric_threshold():
    pack = json.loads((ROOT / "casepacks/climate/indices.json").read_text())
    events = {event["year"]: event for event in pack["events"]}
    assert events[2015]["iod"]["classification"] == "positive"
    assert events[2015]["iod"]["seasonal_dmi_c"] == 0.39
    assert events[2015]["iod"]["event_label_source_id"] == "bom-2015.html"
    assert events[2022]["iod"]["classification"] == "negative"
    assert events[2013]["iod"]["classification"] == "unassigned"
    assert "Between late August and mid-November a positive Indian Ocean Dipole" in source("bom-2015.html")
    assert "very strong from July through to September" in source("bom-2022.html")
    assert "dissipating by late November" in source("bom-2022.html")


def test_pack_rebuild_is_deterministic_and_preserves_source_hashes(tmp_path):
    if not (RAW / 'cpc-oni-v5.html').is_file():
        pytest.skip("Acquire the original climate index snapshots before rebuilding the pack.")
    prepare(output=tmp_path)
    first = {name: (tmp_path / name).read_bytes() for name in ("indices.json", "index-manifest.json")}
    prepare(output=tmp_path)
    for name, content in first.items():
        assert content == (tmp_path / name).read_bytes()
        assert content == (ROOT / "casepacks/climate" / name).read_bytes()
    manifest = json.loads(first["index-manifest.json"])
    assert manifest["sha256"] == sha256(first["indices.json"])


def test_acquisition_cache_does_not_fetch_and_refuses_altered_snapshot(monkeypatch, tmp_path):
    if not (RAW / 'cpc-oni-v5.html').is_file():
        pytest.skip("The source-cache test needs the original climate index snapshots.")
    def no_network(*args, **kwargs):
        raise AssertionError("Verified cache must not refetch")
    monkeypatch.setattr("science.climate_indices.urlopen", no_network)
    assert len(acquire()["files"]) == 17
    shutil.copytree(RAW, tmp_path / "indices")
    (tmp_path / "indices/cpc-roni-v6.html").write_text("altered")
    with pytest.raises(ValueError, match="checksum"):
        acquire(tmp_path / "indices")
    with pytest.raises(ValueError, match="checksum"):
        prepare(tmp_path / "indices", tmp_path / "out")
