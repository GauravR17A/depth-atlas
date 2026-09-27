# Phase 12 surface-temperature sources

The Heat & Depth Lab uses daily NOAA Optimum Interpolation Sea Surface Temperature (OISST), distributed by NOAA AOML and NOAA Physical Sciences Laboratory (PSL), for six fixed ocean grid cells. Data acquisition is separate from event detection. The pack contains source temperatures, coordinates, dates and provenance. It does not contain a hand-picked catalogue of warm events.

## Source and meaning

- Product: NOAA OISST v2.1, daily, 0.25-degree grid, degrees Celsius.
- Primary product description: <https://www.ncei.noaa.gov/products/optimum-interpolation-sst>.
- Dataset DOI: <https://doi.org/10.25921/RE9P-PT57>.
- Main distributor: NOAA AOML ERDDAP, with [the original archive](https://erddap.aoml.noaa.gov/hdb/erddap/griddap/SST_OI_DAILY_1981_PRESENT_T.html) through 2021 and [the separate modern archive](https://erddap.aoml.noaa.gov/hdb/erddap/griddap/SST_OI_DAILY_1981_PRESENT_T_V1.html) from 2022. The original archive lacks 1994-1996. The selected original and modern axes also lack nine isolated days.
- Gap recovery and cross-checks: [NOAA PSL](https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html), using `https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.day.mean.YEAR.nc`.

OISST blends bias-adjusted satellite and in-situ measurements and fills spatial gaps by interpolation. It is an observation-based gridded analysis. It is not an individual measured profile, the HYCOM model used elsewhere in the app, or independent proof that every ocean layer is anomalously warm. Complete gridded coverage does not mean complete direct observation coverage.

NOAA states that September 1981 to December 2015 SST and anomaly values in v2.1 are unchanged from v2. Some older annual PSL files retain legacy v2 titles and history. Those original attributes are preserved. The modern files identify Version 2.1. The source pack must document this compatible lineage rather than modifying the old source metadata.

The source product's separate published anomaly field uses a different climatology. We acquire SST only. The application calculates its declared baseline and threshold from these daily temperatures.

## Fixed sample selection

Before running a heatwave detector, choose west quartile, center and east quartile longitude in each existing case rectangle, all at its center latitude. Choose the nearest OISST native cell in each coordinate independently; select the lower coordinate on an exact tie. All six locations are kept, whether or not their selected year has an event. They represent points, not regional averages or heatwave area.

| Location ID | Case | Native longitude | Native latitude |
| --- | --- | ---: | ---: |
| bay-west | Bay of Bengal | 86.375 E | 13.375 N |
| bay-center | Bay of Bengal | 87.625 E | 13.375 N |
| bay-east | Bay of Bengal | 88.875 E | 13.375 N |
| arabian-west | Arabian Sea | 67.125 E | 17.375 N |
| arabian-center | Arabian Sea | 68.375 E | 17.375 N |
| arabian-east | Arabian Sea | 69.625 E | 17.375 N |

The completed pack covers every day from 1 January 1982 through 31 December 2025. The fixed baseline is 1982-2011, with 2023 and 2024 analysis years. Adjacent years provide context for events crossing a year boundary. AOML is the preferred distributor on every available day. A real PSL source sample fills each absent AOML date. No date is interpolated. The detector owns the duration, threshold, leap-day, joining and missing-value rules. These source scripts do not silently invent those rules.

## Time and units

The annual PSL files encode daily means at midnight UTC as days since 1800-01-01. AOML uses seconds since 1970-01-01 and noon-centered timestamps, as in the original NCEI daily product. Both original numeric times and encoded timestamps are retained. Per-day `source_file_indices` reference the units and calendar in each manifest source file. The location file has no single `time_units` value, because the source origins differ. A daily SST value is compared by its calendar day; it is not presented as an instantaneous midnight or noon instrument measurement.

Both distributors serve SST as Float32 in Celsius, with a valid range of -3 to 45 and declared missing markers. Preparation promotes those numbers exactly to JSON numbers. No temporal interpolation, smoothing, regridding or display rounding changes the analytical source pack. Missing markers become `null`. An otherwise finite out-of-range value raises an error.

The old AOML distribution can differ from PSL by one Float32 representable step. Every overlapping acquired point-day is compared. Accepted differences must remain within one Float32 ULP and the same original 0.01-degree quantization bin. Each served value is retained without a corrective rounding operation. Primary NCEI packed integers are checked with both Float32 scale multiplication and decimal hundredth-degree conversion; these are explicit numerical explanations, not a claim to have audited the distributor's internal processing code. AOML's modern distribution and the old distribution are checked separately. Exact saved-result replay remains exact; this source comparison does not loosen replay checks.

There are no per-sample instrument QC flags in the acquired SST subsets. We do not acquire the optional source error field as part of the heatwave calculation. The app must not imply that a finite interpolated SST has passed a direct instrument-quality test. Three original NCEI daily files, 1 January 1982, 1 July 1996 and 7 January 2024, support checks at all six cells. Agreement between two distributions of OISST is not independent ocean validation.

## Reproduction and pack contract

From the repository root:

```powershell
.venv/Scripts/python.exe -m science.acquire_heat --aoml
.venv/Scripts/python.exe -m science.acquire_heat --recover-gaps
.venv/Scripts/python.exe -m science.acquire_heat --primary-spots
.venv/Scripts/python.exe -m science.prepare_heat
```

`data/raw/heat/` holds ignored original DAP2 and ERDDAP NetCDF responses, source metadata and checkpoint journals. Every saved response has its URL, retrieval time, size and SHA-256 fingerprint. Retries are bounded; cached checksums must match before resuming. A circuit breaker stops queued PSL work after repeated service failure. The `--recover-gaps` command compares the AOML missing-date list with verified PSL coverage and acquires only uncovered dates, in serial blocks of at most ten days. Six isolated recovery files from this build also retain a separate journal under `recovery-gaps/`. An incomplete or changed source must fail preparation rather than becoming a plausible-looking series.

`casepacks/heat/manifest.json` declares source, baseline period, analysis years, context years and six locations. Each location includes its requested and actual coordinates, source selection rule and prepared-file fingerprint. Each location JSON contains aligned `dates`, `sst_c`, `source_timestamps`, `source_numeric_time` and `source_file_indices` arrays. Original metadata and time-axis responses are copied into `source-metadata/`.

## Access observations

CoastWatch ERDDAP access timed out in this session. The original NOAA AOML daily archive was reachable but incomplete. It was initially rejected as a sole source; later checks established a practical merge with the separate modern AOML archive and genuine PSL recovery data. The NCEI THREDDS aggregate was reachable but started in 2020. These observations do not imply that any service is permanently unavailable.

PSL annual metadata and short binary subsets were reachable. The first 2024 annual response exceeded each of three 55-second read deadlines. An annual three-cell alternative ended prematurely at about 61 seconds. Ninety-day subsets sometimes succeeded and sometimes exceeded the deadline. Thirty-day requests worked but later encountered transient 502 responses. Acquisition stopped, retained its cache, and resumed after the service recovered. Recovery work used one PSL request while AOML acquisition used one request. The final 1996 recovery used two concurrent ten-day requests with one journal writer; every ten-day request succeeded. Existing checked chunks remain available for overlap checks. No source data were fabricated to fill an access failure.

A static annual PSL download was also probed. Its 1996 file was 477,794,497 bytes. A corrected two-MiB range probe took 11.41 seconds to receive headers and 1.88 seconds to read the body, about 1.06 MiB/s. The earlier ten-second read deadline was shorter than the observed header delay, so that initial timeout did not establish slow body transfer. No full annual download was started; the existing subset recovery finished. Separate evidence preserves both probe outcomes.

## Completed source checks

Preparation passed on 23 September 2026. Each of the six locations contains 16,071 daily values with no missing values, including 10,957 finite baseline days. Across the shared daily axis, 14,966 days use AOML and 1,105 use PSL. The prepared pack is 7,386,504 bytes. These counts describe source coverage at six selected points, not regional coverage or forecast skill.

All 18 comparisons against original NCEI files passed the declared source representation checks. Across acquired overlapping subsets, 973 of 6,282 point-day comparisons differed numerically. The maximum difference was 0.000003814697265625 degrees Celsius. Every difference was within one Float32 representable step and retained the same original centidegree value. The pack preserves each preferred served value; it does not round the values to make distributors agree.

Two complete preparations from the checked raw journals produced exactly the same manifest and all six location-file hashes, including source indices and metadata ordering. The accepted manifest SHA-256 is `b2c1186439af2a66c982392961145300f0c015792327b6b96721216278d15fff`.

Evidence is retained in `docs/evidence/p12-surface-preparation.json`, `p12-primary-source-comparison.json`, `p12-distributor-comparison.json` and `p12-source-rebuild.json`. Individual requests, failures, successful recoveries and their elapsed times remain in the raw acquisition journals. Scientific event detection and depth diagnostics have separate acceptance checks; these source checks alone do not validate those calculations.

A further check reconstructed all 96,426 original numeric timestamps across the six locations using each referenced source file's time units and calendar. Every timestamp and calendar date matched exactly. Running gap recovery with network access deliberately blocked found the completed cache and left the acquisition journal unchanged. These checks are recorded in `docs/evidence/p12-time-provenance-resume.json`.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
