# P13 historical climate-index sources

Prepared on 23 September 2026. This document concerns the index catalogue, not acceptance of the ocean-field, browser or deployment work.

## The selected seasons

The application compares September to November in three years. Each ENSO label comes from one pinned NOAA CPC RONI ERSSTv6 release. Legacy ONI values remain separately named context.

| Season | RONI ERSSTv6, C | ENSO label | ONI ERSSTv5, C | ONI ERSSTv6, C | CPC DMI ERSSTv6, C | IOD episode context |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| SON 2013 | -0.2 | Neutral | -0.1 | -0.1 | -0.17 | No episode label assigned |
| SON 2015 | +2.0 | El Nino | +2.5 | +2.3 | +0.39 | BOM documents a positive episode from late August to mid-November |
| SON 2022 | -1.1 | La Nina | -0.9 | -0.9 | -0.48 | BOM documents a negative episode, strong in July to September and ending by late November |

These three seasonal ENSO labels agree across the separately checked definitions. Their values do not agree and are never substituted for one another. The application does not assert that every month of a year has the same ENSO or IOD phase.

## RONI, ONI and the 2026 change

[NOAA's January 2026 notice](https://www.weather.gov/media/notification/pdf_2026/pns26-05_Relative_ONI.pdf) makes RONI the official ENSO monitoring and prediction index from 1 February 2026. The [current historical RONI page](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/) identifies ERSSTv6 and a 1991-2020 baseline. It compares the Nino 3.4 anomaly with the tropical mean anomaly and rescales the difference. The application imports the provider values; it does not recalculate RONI from the bounded GODAS field.

Historical labels require five consecutive overlapping three-month windows at the threshold. The published table's classification is the label authority. A separate implementation checks inclusive +0.5/-0.5 C runs against those classifications. This matters because descriptive sentences on the source page alternate between threshold wording and strict greater-than/less-than wording. The actual published classifications include boundary values. All 924 seasons in each of the three pinned ENSO tables agree with the independent run check, including missing future cells.

SON 2015 falls in an 18-season RONI run from OND 2014 through MAM 2016. SON 2022 falls in a 35-season RONI run from AMJ 2020 through FMA 2023. The pack retains every value in those runs. SON 2013 has no qualifying warm or cold run.

The [ONI ERSSTv5 table](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v5/) and [ONI ERSSTv6 table](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v6/) are separately pinned. Their policy uses centered 30-year baselines with five-year updates. The catalogue does not invent a fixed ONI baseline or substitute RONI's fixed baseline. The earlier `ONI_v5.php` address now presents a moved-page notice, which is why actual destination tables were acquired explicitly.

Provider pages warn that recent estimates can change for two months. The selected 2013, 2015 and 2022 seasons are outside that recent provisional interval. They are described as a pinned historical snapshot, not as data guaranteed never to be revised.

## IOD has separate evidence

The numerical series is the [CPC seasonal DMI text file](https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/IODMI/mnth.ersstv6.clim19912020.dmi_season.txt). It explicitly identifies ERSSTv6 and the 1991-2020 climatology. DMI is the western tropical Indian Ocean anomaly, 50-70 E and 10 S-10 N, minus the southeastern anomaly, 90-110 E and 10 S-0 N. The [HTML table](https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/IODMI/DMI_season.html) matches all 920 text rows, including two missing entries. Its generic header also describes centered periods and ten-year updates; the pack preserves that inconsistency and uses the specific downloadable series definition.

The official DMI is retained as published. Subtracting the two displayed component values can differ by 0.01 C because the three text columns are separately rounded. The application does not replace DMI with that rounded subtraction.

The [Bureau of Meteorology 2015 statement](https://www.bom.gov.au/climate/current/annual/aus/2015/) supports the historical positive IOD label and its approximate timing. The [2022 statement](https://www.bom.gov.au/climate/current/annual/aus/2022/) supports the negative episode and its weakening through austral spring. These statements describe agency event assessments. They are not an application classification produced by thresholding a three-month CPC number. In particular, the 2015 SON DMI is +0.39 C, below +0.4 C, while the documented positive episode occupies a different interval. Both facts stay visible.

No IOD label is assigned to 2013 merely because its DMI is near zero. Exact IOD start/end dates, weekly persistence and local weather effects are not invented from annual statements. September, October and November controls expose ASO, SON and OND index windows respectively, explicitly named as centered three-month context. They do not pretend that a seasonal index is a single monthly measurement.

## Other sources reviewed

The [PSL HadISST DMI description](https://psl.noaa.gov/data/timeseries/month/DMI/), raw monthly series and original NCL method were archived. Its monthly values differ from CPC ERSSTv6. The acquired method reads a separate monthly climatology but does not state its years directly. It is research evidence, not a second numerical IOD source silently blended into the application.

The [BOM IOD year list](https://www.bom.gov.au/climate/iod/content/years-iod-enso.html), 2016/2019 annual statements and [JAMSTEC's study of the 2019 event](https://www.jamstec.go.jp/e/about/press_release/20200406/) were checked as contextual alternatives. They do not create additional deployed cases or demonstrate causal attribution for our three selected years.

## Reproduction and checks

Original unmodified bytes and HTTP metadata are under ignored `data/raw/climate/indices/`. Seventeen source files retain URL, resolved URL, retrieval timestamp, byte count, SHA256 and available Last-Modified/ETag headers. Acquisition reuses verified cached bytes. A changed cached file stops preparation. There is no live index request in the browser or public analysis request.

Run from the project root:

```powershell
.venv/Scripts/python.exe -m science.climate_indices --acquire --prepare
.venv/Scripts/python.exe -m pytest tests/test_climate_indices.py -q --junitxml=docs/evidence/p13-index-tests.xml
```

The prepared files are `casepacks/climate/indices.json` and `casepacks/climate/index-manifest.json`, with schema `p13-indices-v1`. Two preparations reproduce identical bytes. The source snapshot identity is `a5d0378b1d738aca26556db1d3383470b2def495f0983297c921423a0f5fc26d`.

All 26 index tests pass. They cover provider classification checks, an independently downloaded two-decimal RONI series, DMI text/HTML comparison, explicit source transcriptions, five-season boundaries, cross-year windows, missing support, ordered seasons, independently sourced IOD labels, deterministic packing and altered-source rejection. The first run had 25 passes and one mistaken expected source-row count; that report remains in `evidence/p13-index-tests-initial.xml`. The corrected expectation retains both explicit missing DMI rows. No source value or tolerance was changed.

Machine-readable evidence is [p13-index-audit.json](evidence/p13-index-audit.json), with final test evidence in [p13-index-tests.xml](evidence/p13-index-tests.xml). Index consistency does not validate GODAS subsurface fields, prove climate causality or establish operational forecast skill. Those claims are outside these checks.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
