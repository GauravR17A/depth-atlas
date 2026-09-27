# Phase 4: observations and supported imports

Completed: 22 September 2026. Release: 0.4.0, verified on Vercel. PROJECT_STATE.md records the deployment and next phase.

## Implemented contract

The new observation contract is version 2, defined in `science/instruments.py` and checked in the browser. The P02 model manifest and its legacy profile endpoints remain unchanged. P04 reads the original Argo files again into a separate observation library using `adapters/instruments.py`. Each variable has its own source field, units, processing mode, QC scheme and accepted count. Every original sample retains its index, pressure, derived depth, position, timestamp and selected/raw/adjusted values, flags and supplied adjusted error. Structured `coordinate_qc` records pressure, position and time flags, leaving unavailable source flags blank; `coordinate_eligible` states the adapter's rule without inventing good flags.

Pressure is converted with `-gsw.z_from_p(pressure, latitude)` using GSW 3.6.20 and its zero dynamic-height/surface-geopotential defaults. Pressure is sea pressure in dbar; it is never relabelled as metres. Source order and duplicate depths are retained. Negative pressure has no usable depth. See the [TEOS-10 function and independent example](https://www.teos-10.org/pubs/gsw/html/gsw_z_from_p.html).

Core Argo R selects the raw parameter; A/D selects its adjustment. BGC selects each parameter through `PARAMETER_DATA_MODE`. Missing adjusted data never backfill from raw data. The accepted curve requires Argo flags 1/2 for its variable, eligible pressure and position/time. Raw BGC R values remain inspect-only. These choices follow the [Argo data-use guide](https://argo.ucsd.edu/data/how-to-use-argo-files/); acceptance by this filter is not independent validation.

QARTOD 1 is accepted; QARTOD 2 is not evaluated and excluded. WOCE CTD flag 2 is accepted; WOCE 1 is not promoted to good. CSV 1/2 are uploader declarations, not verified provenance. The source schemes remain visible. References: [IOOS temperature/salinity QC manual](https://ioos.noaa.gov/ioos-in-action/temperature-salinity/), [WOCE hydrographic data formats](https://cchdo.github.io/hdo-assets/documentation/manuals/pdf/90_1/chap4.pdf).

## Genuine observation library

| Collection | Records | Source and limit |
| --- | --- | --- |
| Bay of Bengal, January 2024 | Seven Argo profiles already acquired for P02 | INCOIS DAC originals via Argo GDAC; inside the model's geographic domain, but no match is inferred |
| Tropical Atlantic, September 2023 | Argo 6903091 cycle 100, including adjusted oxygen | [Original GDAC S-profile](https://data-argo.ifremer.fr/dac/coriolis/6903091/profiles/SR6903091_100.nc); S-file sensor alignment belongs to the provider, not this app |
| Caribbean Sea, April 2024 | Four RU29 glider profiles, 3,787 source rows | [IOOS/Rutgers delayed deployment](https://gliders.ioos.us/erddap/info/ru29-20240419T1430-delayed/index.html); bounded two-hour profile-time selection, full original samples within those profiles |
| Southwest Indian Ocean, February 1996 | CIVA2 station 1, cast 1, 48 samples | [CCHDO cruise 35MF103_1](https://cchdo.ucsd.edu/cruise/35MF103_1); original CTD Exchange member `i06sb_00001_00001_ct1.csv` |

Glider per-sample `precise_time`, `precise_lat` and `precise_lon` are retained. Source positions can be interpolated between GPS fixes, which is disclosed. The source salinity declares valid_min 40 and valid_max 0. The adapter records both, preserves finite source readings for inspection and excludes salinity from the accepted curve. It does not silently swap the bounds or invent a valid range. Temperature remains eligible under its own QARTOD/pressure checks. A source-quality problem should not become a plausible green curve.

The CTD source has missing oxygen at this station. The variable remains inspectable with no accepted curve. The temperature scale must be confirmed from the cruise report before P05 quantitative comparison. Neither the ship cast nor the glider/BGC collections extend the Bay of Bengal model domain.

`science/acquire_instruments.py` records source URLs, sizes and hashes; `science/prepare_instruments.py` creates the versioned profile JSON and checksummed index in `casepacks/instruments`. Raw downloads remain under ignored `data/raw/instruments`. Five downloadable example files include original core/BGC/glider NetCDF, original CTD Exchange, and a documented CSV export of 20 genuine Argo levels. The CSV export retains selected readings and flags; its simpler schema does not preserve the full adjustment history.

## Import boundary

`POST /api/instruments/import?filename=...` accepts a raw file body. Application code processes bytes in memory, does not fetch source URLs and does not persist uploads. The file name is display metadata only, not a filesystem path. The API serializes netCDF C-library access. The endpoint and browser reject excessive sizes; malformed metadata, calendars, unsupported variables, incompatible units and unsupported schemas get explicit errors. File limits: 2 MB, 24 profiles, 5,000 source samples, bounded NetCDF fields/elements and a 3.5 MB decoded response. Browser imports are capped at 24 profiles or 12,000 samples per open session.

Supported layouts are Argo/BGC profiles, documented IOOS glider row-NetCDF subsets, CTD Exchange casts and Depth Atlas CSV v1. This is not arbitrary NetCDF/Excel support. The public [import guide](../web/public/observation-import-guide.txt) defines the exact columns and requirements. Existing model ingestion still uses the offline xarray adapter. Runtime observation ingestion adds netCDF4, NumPy and GSW, without pandas/xarray in the serverless runtime.

Profiles from uploads live in browser memory until cleared or reloaded. Application code does not log body content; filenames can appear in request URLs and hosting logs. The Privacy Policy and Terms now describe this behavior and retain the user's deferred operator/contact details.

## Interaction and scientific limits

Numbered locations on the 3D model open the corresponding historical Argo profile. These are geographic surface markers, not simultaneous instrument fixes at the selected model timestamp. Markers can be hidden. Instruments opens a connected workspace with a collection selector, location map, selectable tracks and a variable-versus-depth chart. The map and 3D markers use actual coordinates. Glider Track detail zooms into the retained source track; the ordinary basemap is Natural Earth geographic context.

Charts use source samples in source order, with a linear physical depth axis. Lines break at missing or excluded samples. Isolated eligible samples appear as dots. Optional excluded crosses never join the accepted curve. Pointer selection chooses an actual sample; keyboard users have previous/next and sample controls. Each selected sample displays its own timestamp, coordinates, units and quality reason. Raw/adjusted fields and source metadata are inspectable.

View nearest model depth selects the nearest native model grid location/depth only, keeps the existing model timestamp and states the observation time. The button is unavailable for locations outside the current model domain. This navigation is not collocation, residual analysis, validation or a forecast. Those scientific matching rules belong to P05.

The desktop shows map and chart together. Narrow layouts prioritize the profile chart and move geographic detail below it. Opening instruments preserves the 3D camera and pauses the hidden renderer. The model controls and model-only case card are hidden in the observation workspace to avoid confusing dates/coverage across collections.

## Verification

- Backend: 51 tests pass, comprising 30 observation/import cases and the 21 existing checks. Source-value tests read original NetCDF/Exchange examples independently. Report: `evidence/p04-science-api-final.xml`.
- Renderer: 17 numerical checks passed; P04 does not alter the checked model field values or geometry methods.
- Local browsers: 98 passed, one intentional WebKit context-loss skip. Report: `evidence/p04-local-browser-final.json`. Isolated eligible-sample dots were then added and passed all three focused engine checks in `evidence/p04-isolated-samples-recheck.json`.
- Public browsers: 94 passed, four page/data-loading timeouts, one intentional skip, across Chromium desktop/mobile emulation and Windows WebKit. Three failures passed the first unchanged recheck. The mobile fallback needed a second unchanged recheck, which passed. Reports: `evidence/p04-public-browser-final.json`, `evidence/p04-public-browser-recheck.json`, `evidence/p04-public-fallback-recheck.json`. The traces show several API requests aborted around the existing eight-second limit. The fallback trace includes 5.1 seconds for HTML and 7.9 seconds for the first volume response, leaving its dependent renderer too late for the assertion. The underlying service/network cause is not established. First-load latency remains a real limitation. Trace summaries: `evidence/p04-public-timeout-traces.json`, `evidence/p04-fallback-timeout-trace.json`.
- Public source/API checks: all 13 profiles agree with the checked local library. All five example files download with matching hashes and import successfully. Malformed and oversized uploads return 422/413, unknown IDs return 404, and the catalogue is unchanged after imports. The P02 manifest is unchanged and three independent model probes agree. Report: `evidence/p04-public-http.json`.
- Visual review: desktop, Windows WebKit, 390/320-pixel widths and 200% root text; screenshots cover the model, Argo/BGC/glider, excluded salinity, missing CTD oxygen and imports. No page errors or document overflow in the checked views. Reports: `evidence/p04-local-visual-review.json` and `evidence/p04-public-visual-review.json`. These are emulated layouts, not physical-device certification.
- Build/typecheck and `pip check` pass. The Three.js chunk remains about 581 kB minified, 146 kB gzip, exceeding Vite's advisory. Two existing Python test-client deprecation warnings remain. Firefox's Windows launch issue, Docker and actual institutional installation remain open.

### Issues found and retained evidence

The initial local suite passed 91 and failed seven, with one skip. Existing tests needed explicit scope after adding Argo markers; field-picking tests now hide the marker layer before selecting the field. The deep-section test clicked exactly on the 1,000 m boundary, where subpixel rounding can fall outside the valid face. It now aims at 975 m inside that cell while still checking the independently sourced native 1,000 m value. A focused run passed eight of nine before that final targeting correction. No scientific values or picking tolerance were changed. Reports: `p04-local-browser-initial.json` and `p04-picking-recheck.json`.

The initial public HTTP check exposed a missing static route for bundled license files; `/licenses/` is now mounted. The initial public browser run passed 94 with four failures and one skip, but was contaminated by a concurrent local run deleting shared Playwright trace artifacts and a test edit targeting the not-yet-deployed isolated-dot feature. Those failures are retained in `p04-public-browser-initial.json`. The final suite ran alone against the final deployment.

Two initial Vercel builds failed during dependency configuration: universal resolution hit the Windows ARM64 NumPy constraint, then uv rejected a project-only setting in `uv.toml`. The successful build uses `pyproject.toml` with identical runtime pins and explicit supported server targets. See D023 and `evidence/p04-release-check.json`.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
