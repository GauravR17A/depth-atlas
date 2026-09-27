# Phase 2: historical Bay of Bengal case

Project/access-review date: **21 September 2026**. The user explicitly reminded us that the current year is 2026. Scientific acquisition dates, observation dates, source update dates and project dates are separate fields. No January 2024 data is described as current or live.

## Selected case

- Case ID: `bay-bengal-2024-01`.
- Model: HYCOM GOFS 3.1 + NCODA, `GLBy0.08/expt_93.0`, an assimilative **model analysis**, not an observation or a newly computed forecast.
- Seven instantaneous snapshots: 2024-01-07 00:00 UTC through 2024-01-10 00:00 UTC, every 12 hours. The archive has 3-hourly output; the intervening timestamps are deliberately not bundled.
- Requested box: 85–90° E, 12–15° N. Selected native coordinates: approximately 85.04–90° E, 12–15° N. The source's exact first longitude is **85.0400390625° E**, confirmed independently through its ASCII endpoint; retain that value for exact point requests rather than the rounded label.
- Native subset: 63 longitudes × 76 latitudes × 40 irregular output depths, from 0 to 5000 m. The source's 41 hybrid model layers are distinct from its 40 fixed output depths.
- Four scalar arrays: in-situ temperature, practical salinity, eastward velocity and northward velocity. The velocity components are geographic, not grid-relative. No chlorophyll or vertical velocity is supplied.
- Seven **delayed-mode Argo profiles** distributed through the INCOIS DAC at Ifremer GDAC, cycles 012 of floats 1902669, 2903891, 4903775, 4903776, 5907083, 7901125 and 7901126.

This box was chosen after inspecting the January 2024 Argo index and reading actual profile files. It is a small compatibility case, not a verified ocean event or basin-wide coverage claim. The geographic globe's larger navigation rectangle remains illustrative and is labelled separately.

## Source-access audit

| Candidate | Evidence on 21 September 2026 | Decision |
| --- | --- | --- |
| Copernicus GLORYS12 | Product catalogue read successfully; official download documentation describes account credentials. No authenticated subset download was established in this session. | Retain as a later adapter/source candidate; do not block this phase or imply acquisition succeeded. |
| INCOIS services | ESSDP homepage returned HTTP 200. An older `portal/datainfo.jsp` URL returned 404. This is not evidence of access to an INCOIS numerical model download. | Preserve the institutional integration requirement. The selected Argo originals do come from the public INCOIS DAC directory. |
| HYCOM GOFS 3.1 archive | DDS, DAS and coordinate metadata returned HTTP 200. NCSS metadata timed out. Native netCDF4 remote access failed locally with a curl IO error; the same OPeNDAP archive worked through pydap. One later field request timed out and was resumed from verified snapshots. | Use serial pydap OPeNDAP subset requests, at most one HYCOM connection at a time, with bounded retries. |
| Ifremer Argo GDAC | Indian Ocean daily file and global profile index retrieved. The initially inspected 15 January daily file had no profiles in the tested Bay box. Index filtering found 57 January profiles in the broader candidate region; seven matching INCOIS profiles were downloaded for the final box/time span. | Use original individual delayed-mode NetCDF records with QC and metadata. |

The raw audit is in `evidence/phase-02-access-audit.json`. Selected files, exact remote indices, source URLs, retrieval timestamp and SHA-256 fingerprints are recorded in the case manifest and source-metadata file. The profile index is a discovery aid, not a substitute for inspecting the selected original records.

## Reproduction and stored representations

From the repository root:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-science.txt
.venv/Scripts/python.exe -m science.acquire_case
.venv/Scripts/python.exe -m science.prepare_case
.venv/Scripts/python.exe -m pytest tests -q
```

The pinned offline environment was tested with Python 3.10.11. The web service uses the much smaller `requirements.txt`; xarray, netCDF4, pydap and GSW do not run in evaluator requests.

`data/raw/` is ignored and not uploaded to Vercel. Acquisition stores:

1. Original Argo profile NetCDF files, unchanged.
2. HYCOM **packed source subsets reconstructed as NetCDF** from OPeNDAP, with source attributes, original coordinates and exact index selections. These are not the original whole global archive files. Packing metadata retains the source Float32 scale/offset and Int16 fill values.
3. An acquisition journal with hashes. Verified cached snapshots can be reused after interrupted network requests. A changed cached fingerprint is rejected rather than silently accepted.

`casepacks/bay-bengal-2024-01/` is included in source/deployment:

- `manifest.json`: versioned contracts, coverage, provenance, limitations and file fingerprints.
- `source-metadata.json`: original coordinate/variable metadata, acquisition records and value statistics.
- `analytical/*.bin.gz`: lossless gzip of little-endian float64 values on the native subset grid. Source packing is decoded once; no interpolation or hole filling.
- `display/*.bin.gz`: every second latitude/longitude, plus the final coordinate, retaining all 40 depths, converted to float32. The resulting shape is 40 × 39 × 32. The manifest records source indices and the measured maximum rounding error per variable.
- `profiles/*.json`: selected and original readings, adjusted errors, QC, calibration metadata, source indices and pressure-derived depths.

The analytical and display arrays share timestamps and variable definitions. Scientific calculations must use the analytical representation. Display decimation is not an analytical regridding operation. Missing values remain NaN in binary and JSON `null` over the API.

The committed case pack allows a fresh checkout and Vercel deployment to run without downloading external data or configuring a marine-data account. Upstream files may be revised; the current Argo file hashes and update metadata identify this acquisition. We do not claim the files belong to a frozen monthly DOI snapshot. A later source revision must produce a reviewed case version, not silently replace this pack.

## Observational eligibility

- `DATA_MODE=D` or `A` selects only `*_ADJUSTED`. `R` selects raw values. An absent adjusted value is never backfilled from raw data.
- A sample is eligible for this early compatibility check only if selected pressure, temperature and salinity are finite with QC 1 or 2, pressure is nonnegative, and position/time QC are 1 or 2.
- All original source levels are retained, including excluded levels and raw/adjusted fields. The source order is preserved; regular vertical spacing is not assumed.
- Pressure in dbar is converted to positive-down depth in metres with `-gsw.z_from_p(pressure, latitude)`. Dynamic height and sea-surface geopotential use the documented zero defaults. Pressure itself is retained.
- JULD is decoded from its CF epoch and rounded to the source's second resolution, avoiding floating-day truncation by one second. Original numeric JULD, units and decoded timestamp remain in metadata.
- Profile eligibility additionally requires actual spatial, temporal and vertical overlap. The manifest records the nearest bundled model timestamp and signed offset. This is **not** collocation/interpolation, a mismatch metric, a confidence score or an independent validation result.

Full model/profile comparison methods belong to P05. HYCOM assimilates observations, so future agreement cannot automatically be described as independent validation.

## API and caching

| Endpoint | Output |
| --- | --- |
| `/api/catalog` | Schema v2, one real historical case and two planned regions |
| `/api/cases/bay-bengal-2024-01` | Full scientific manifest |
| `/api/cases/bay-bengal-2024-01/subset?variable=temperature&time_index=0&depth_index=0` | Native analytical surface slice |
| `/api/cases/bay-bengal-2024-01/subset?variable=temperature&time_index=0&operation=volume&representation=display` | Bounded display volume |
| `/api/cases/bay-bengal-2024-01/profiles/argo-1902669-012-0` | Genuine Argo record, selected/raw/adjusted values and QC |

Subset requests accept one variable and timestamp, an optional geographic box, and either a depth slice or volume. All four box limits are required together. Coordinates must lie within the selected case; unsupported dates, depths, variables and oversized requests produce explicit errors. A maximum of 100,000 scalar values keeps responses bounded. The larger complete analytical volume needs smaller bounds or slices.

A process-local LRU holds at most three decompressed arrays plus one manifest. Files are immutable deployment assets; the filesystem is not used as durable user storage. Array/profile fingerprints are checked before serving. Browser/API responses retain `no-store`; no external data request is triggered by opening the workspace.

## Verification scope

Numerical tests use independently specified packed integers and coordinates, reversed axes, 0–360 longitudes, irregular depth, fill/range masks, invalid coordinates, incompatible temperature/current definitions and unsupported calendars. Argo fixtures verify adjusted-value selection, rejection of bad QC and missing-adjusted behavior. Pressure conversion is checked against the published TEOS-10 example, not against the same implementation recomputed as an expected result.

Case-pack tests check hashes, actual dates/coverage, source samples, display/analytical equality within declared float32 rounding, missing deep cells and bounded API failure paths. Additional verification reads raw packed source NetCDF values independently with netCDF4 and records direct source-service checks. Browser tests cover historical labels, sample selection, missing values, Argo QC records, keyboard focus, region switching and error recovery. Evidence files are listed in `PROJECT_STATE.md`.

Not implemented by this phase: volumetric rendering, map instrument overlays, profile comparison charts, arbitrary uploads, live feeds, chlorophyll, gliders, CTD/BGC adapters, WMS/WCS interoperability certification, simulations or operational advisories. These remain on their original phases.

## Primary references

- [HYCOM dataset and archive](https://www.hycom.org/dataserver/gofs-3pt1/analysis)
- [HYCOM public-release terms and service limits](https://www.hycom.org/dataserver/access-methods/ncss)
- [HYCOM source metadata and service links](https://tds.hycom.org/thredds/catalogs/GLBy0.08/expt_93.0.html?dataset=GLBy0.08-expt_93.0)
- [Argo raw/adjusted selection and quality guidance](https://argo.ucsd.edu/data/how-to-use-argo-files/)
- [Argo attribution and DOI guidance](https://argo.ucsd.edu/data/acknowledging-argo/)
- [TEOS-10 pressure-to-height example and definition](https://www.teos-10.org/pubs/gsw/html/gsw_z_from_p.html)
- [CF Conventions 1.12](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.12/cf-conventions.html), used for interpretation; source metadata declares CF-1.6/NAVO, not full CF-1.12 certification.
- [Copernicus GLORYS12 product](https://data.marine.copernicus.eu/product/GLOBAL_MULTIYEAR_PHY_001_030/description)
- [Copernicus credential documentation](https://help.marine.copernicus.eu/en/articles/8185007-copernicus-marine-toolbox-credentials-configuration)


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
