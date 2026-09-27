# P13 field sources and preparation

Prepared in September 2026. The displayed ocean periods are historical September, October and November in 2013, 2015 and 2022. Project dates do not change those source dates.

## Source choice

The field source is the NOAA NCEP Global Ocean Data Assimilation System, distributed by NOAA PSL. NOAA CPC links this NetCDF distribution from its [GODAS background page](https://www.cpc.ncep.noaa.gov/products/GODAS/background.shtml). The [PSL dataset page](https://psl.noaa.gov/data/gridded/data.godas.html) supplies attribution guidance, and its [THREDDS catalogue](https://psl.noaa.gov/thredds/catalog/Datasets/godas/catalog.html) lists the annual archives.

The actual source variable is `pottmp`, potential temperature in kelvin. It is a monthly mean, with the timestamp set to the first day of the averaging period. This differs from the instantaneous in-situ temperature used by the earlier HYCOM cases. The source declares COARDS metadata and does not supply a CF standard name for `pottmp`; preparation explicitly maps NOAA's potential-temperature definition to `sea_water_potential_temperature`. It does not claim that this attribute was present in the original file.

The [CF definition of sea-water potential temperature](https://cfconventions.org/Data/cf-standard-names/9/build/cf-standard-name-table.html) references the temperature after an adiabatic change to sea-level pressure. That quantity definition supports the explicit surface-reference explanation used in the lab. It does not make potential temperature interchangeable with the original Argo in-situ readings.

Public GODAS salinity and both current components were also inspected. Current coordinates are staggered by half a degree relative to the temperature grid. P13 therefore supplies temperature fields only. The system does not fabricate missing variables or silently put those currents on the temperature grid.

## Exact extraction

The common subset contains 3 months, 28 native depths, 30 native latitudes and 240 native longitudes:

- September, October and November, without a seasonal averaging step during acquisition.
- Native depths from 5 to 459 m. The original archive has 40 levels down to 4,478 m; the bounded P13 extraction stops at the last native level below 500 m.
- All native latitude centres inside 5 degrees south to 5 degrees north.
- Longitude centres from 40.5 to 279.5 degrees east, keeping the original increasing convention through the dateline.

The Pacific workspace cases retain 140.5 to 279.5 degrees east. The common climate pack also supports Indian Ocean context on the same source grid and dates. The nearest source row to the equator is 0.16612949967384338 degrees north, and must be labelled with that actual latitude. No exact-equator row is invented.

`science/acquire_climate_fields.py` fetches contiguous native Float32 OPeNDAP subsets and reconstructs bounded NetCDF archives. These are source subsets, not downloads of the entire original annual files. The acquisition journal retains the source URL, original source-index ranges, numeric time units, original variable metadata, checksums and any failed attempts. Each request has a 45 second timeout, with at most two attempts per year; successful years are checkpointed. Cached files must match their recorded hashes.

## Baseline and transformations

The fixed field baseline is 1991 through 2020, with one separate mean for each of the three calendar months. Preparation uses the 30 actual annual fields under the declared complete-year policy below. An initial guessed `godas/pottmp.mon.ltm.1991-2020.nc` URL returned 404. Later review found the real [official climatology in the Derived directory](https://psl.noaa.gov/thredds/dodsC/Datasets/godas/Derived/pottmp.mon.ltm.1991-2020.nc.html), so that initial response did not establish that a provider climatology was absent.

The official product declares the same 1991-2020 period, Float32 potential temperature and a `valid_yr_count` field. Its metadata permits a mean with at least 3% of input values present, and its history records generation on 27 January 2022. P13 retains its already pinned Float64 reconstruction requiring all 30 source years, rather than silently switching to a product with a different missing-data policy and storage precision. Only the official product's DDS/DAS metadata were acquired during this later review; no numerical comparison with its climatology values has been performed. The metadata and exact source URLs are recorded in [p13-official-climatology-metadata.json](evidence/p13-official-climatology-metadata.json). This correction changes the source explanation, not the prepared baseline or its fingerprints.

Preparation applies this declared sequence:

1. Preserve source Float32 values and coordinate centres in the acquired archive.
2. Mask source missing values and declared valid-range failures.
3. Promote valid kelvin values to Float64, then subtract 273.15 to produce Celsius potential temperature.
4. Sum each calendar month's cell in ascending year order from 1991 through 2020 in Float64.
5. Divide by 30 only when all 30 values are finite. Otherwise keep the baseline cell missing. Preserve the contributing-year count separately.

No baseline gap is filled, no missing value is treated as zero, and no field is shifted to fit an expected ENSO appearance. The index definitions and historical labels are documented separately. The displayed GODAS anomaly baseline is a different source quantity and calculation from the surface-index baselines, even when their named year ranges agree.

Analytical files retain Float64 values. Pacific display files choose every second latitude and every third longitude, including the final coordinate of each axis, and keep every depth. Their shape is 28 by 16 by 48. Each display file is Float32, with the largest rounding error recorded in its case manifest. This is spatial selection and numeric rounding, not a smoother or an interpolated reconstruction.

## Original observations

Original Argo profiles are selected from the existing checked GDAC index before looking at their temperatures or QC. For each selected year and calendar month, candidates lie within 5S-5N and 160W-120W. Selection minimizes `abs(latitude) + abs(longitude + 140)`, then distance of the calendar day from the 15th, then source path. This is a small reproducible observation example, not an optimal observing network.

The original GDAC NetCDF files are read through the existing core Argo and instrument contracts. Adjusted-mode records never fall back to raw measurements. Per-parameter QC, original coordinates, pressure, derived depth, calibration metadata and original file hashes remain inspectable. The general source citation is [Argo GDAC, SEANOE](https://doi.org/10.17882/42182); [Argo's acknowledgement guidance](https://argo.ucsd.edu/data/acknowledging-argo/) states that the data are freely available without restriction and requests attribution.

The observations are instantaneous in-situ temperatures. GODAS is a monthly mean of potential temperature. Co-display supplies evidence and context, but a direct temperature residual between those quantities is disabled. GODAS may have assimilated these observations, so agreement would not establish independent validation even after a justified quantity/time conversion.

## Reproduction and evidence

From the repository root:

```powershell
.venv/Scripts/python.exe -m science.acquire_climate_fields
.venv/Scripts/python.exe -m science.prepare_climate_fields
```

The source journal is `data/raw/climate/field-acquisition.json`, with raw archives under ignored `data/raw/climate/`. Prepared source fields are in `casepacks/climate/field-manifest.json`. The three shared workspace cases are `casepacks/pacific-godas-2013-son/`, `casepacks/pacific-godas-2015-son/` and `casepacks/pacific-godas-2022-son/`. Their additional instrument libraries are under matching subdirectories of `casepacks/instruments/`.

All 31 model years and all nine original Argo files were acquired and prepared. The raw source files total 37,669,671 bytes. All 31 model acquisition attempts succeeded on their first attempt. A cached acquisition was then repeated with network calls disabled, and its acquisition journal remained byte-for-byte unchanged. Evidence: [cache and resume check](evidence/p13-field-cache-resume.json).

The full baseline contains 535,279 complete month/cells and 69,521 missing month/cells. Counts range from 0 to 30, and only count 30 produces a finite baseline. This count describes source availability, not calibrated confidence. Preparation evidence is [p13-field-preparation.json](evidence/p13-field-preparation.json).

The original September 2022 Argo profile has 994 accepted temperature readings but no accepted salinity readings. The older joint core contract therefore reports zero jointly eligible samples, while the per-variable instrument contract correctly retains those accepted temperature samples. The profile remains in the case, with its source flags visible. It was not replaced after seeing its QC. The other eight source profiles contain between 932 and 1,002 jointly eligible samples.

A second complete preparation reproduced all 62 checked case, instrument and field-pack files without changing a single hash. Evidence: [deterministic rebuild](evidence/p13-field-rebuild.json). The frozen field manifest SHA-256 is `b5b015c3401f74e3ae9be4e92e11abf97410899be85b465a43447d3fa4b728b2`.

| Shared case | Manifest SHA-256 | Prepared bytes |
| --- | --- | ---: |
| `pacific-godas-2013-son` | `a939fb4f64828f3d73d1bfc6fb677fbae1b3903eb532a2aca7298edf0bbec33d` | 2,954,055 |
| `pacific-godas-2015-son` | `dc46f59743f242e4a8dc3b2e83256ab0bb420aac3285d94c0673a9c8803ded0c` | 2,848,797 |
| `pacific-godas-2022-son` | `5eb03d4d2f9bd7fbbbd97d19889083da6e31d9c014a6b027a1e98a950cf5656c` | 2,965,850 |

Independent reads through NOAA's NCSS NetCDF interface matched all 1,008 compared source values exactly. These checks span 1991, 2005, 2013, 2015, 2020 and 2022, all three SON months, all 28 retained depths and the adjacent 179.5/180.5 degrees east cells on either side of the dateline. No numerical tolerance was used for the field values. [Source request records](evidence/p13-ncss-source-reads.json) and [transport comparison results](evidence/p13-field-transport.json) retain the evidence.

NCSS represents the selected latitude as 0.16612979769706726 degrees north, whereas the original OPeNDAP coordinate is 0.16612949967384338 degrees north. The difference is 0.0000002980232238769531 degrees. The source service cause was not established. Checks used the uniquely nearest native latitude and required identical time, depth and longitude coordinates; prepared files retain the original OPeNDAP latitude. The discrepancy is recorded instead of rewriting the native grid.

These checks establish reproducibility, source transport and contract preservation. They are not independent physical validation of the GODAS analysis. Numerical climate calculations and deployed interaction checks are recorded separately by the phase acceptance work.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
