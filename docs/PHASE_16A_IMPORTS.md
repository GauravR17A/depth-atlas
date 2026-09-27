# P16A: imported observations in a connected model view

Started 26 September 2026; accepted 27 September 2026, Asia/Calcutta. Release 0.16.5 is deployed on the existing Vercel project. Final deployment evidence is recorded in PROJECT_STATE.md.

## Delivered scope

P16A owns review items 1, 4, 5, 6, 11, 12 and 13. A supported observation file is reviewed before it enters the temporary workspace. Its eligible in-domain coordinates feed the shared instrument overlay. Opening a profile retains the model view and its selected timestamp. The observation sample has its own timestamp, position, source field, units and QC.

Desktop uses adjacent model and profile panels. Narrow screens stack them with a bounded, keyboard-accessible model panel. Location maps, tracks and detailed provenance expand on demand. Closing the profile restores the full model space. Basic graphics retains selectable instrument-location controls.

The preview lists detected variables and units, accepted, excluded and missing readings, coordinates, time/depth coverage, excluded-sample reasons and unsupported fields. Add commits to this tab; Discard or Cancel retains previously added profiles. Cancel aborts the browser request and ignores a late response; it does not guarantee interruption of parsing already running on the service.

CSV mapping supports explicit column selection for documented quantities. Kelvin converts to Celsius by subtracting 273.15; chlorophyll mg/L converts to mg/m3 by multiplying by 1000; ug/L has the same numerical value as mg/m3. Practical salinity accepts the declared psu/PSS-78 naming. Oxygen and nitrate require umol/kg. Coordinates, pressure, timezone-aware time and QC must already use the documented meanings. No density-dependent conversion, salinity redefinition, QC-scheme translation or arbitrary formula is offered. Canonical measurement columns cannot be relabelled as different quantities/units. Mapping changes require another review before Add becomes available.

Native NetCDF and CTD Exchange retain source metadata and processing rules. The original file hash survives CSV mapping; normalized-table and mapping hashes are recorded separately. Raw CSV inspection explicitly uses converted display units. Unknown source files do not inherit an official URL from their filename. Only an exact public-example byte hash receives the known original source URL.

## Real examples and scientific limits

The [machine-readable overlap report](evidence/p16a-example-overlap.json) evaluates every example against all five main model cases using coordinate-eligible samples and the actual model date range. Intersection is not a scientific comparison or independent validation.

| Example | Source date and location | Current model relationship |
| --- | --- | --- |
| Argo 2903891 cycle 12, native and derived CSV | 9 January 2024, 13.0667 N, 89.9833 E | Inside Bay rectangle/date range. Native file has 102 coordinate-eligible samples. The CSV contains 20 source levels from the same profile, not independent observations. |
| BGC 6903091 cycle 100 | 28 September 2023, 9.1326 N, 20.7304 W | Outside all five main model cases. Original oxygen adjustment and QC remain inspectable. |
| IOOS ru29 glider subset, four profiles | 19 April 2024, near 17.7794 N, 67.0579 W | Outside all five main cases. Moving sample coordinates/times are preserved. Contradictory salinity range metadata retains its inspect-only policy. |
| CCHDO CTD station | 21 February 1996, 33.1947 S, 28.0603 E | Outside all five main cases. Source WOCE flags and absent oxygen remain explicit. |
| New BGC 1902594 cycle 34 | 29 March 2024, 12.6794 N, 85.3031 E | Inside Bay rectangle, outside its January date range. Chlorophyll is an observed quantity, not a new model field. |

The remaining dependency for simultaneous glider/CTD co-display is a supported model covering the actual example coordinates and dates, or an openly available, QC-documented observation subset inside the existing model domains/dates. No such matched source pair is supplied by this checkpoint. New model input is P16B; imported numerical matching is P16C. Source types are supported by the shared location contract, but this phase does not claim a real simultaneous four-instrument/model comparison.

### Chlorophyll provenance

The source is [Argo GDAC/Coriolis SR1902594_034.nc](https://data-argo.ifremer.fr/dac/coriolis/1902594/profiles/SR1902594_034.nc), 518,900 bytes, SHA-256 `1368b43fca3d535e3d4745cfcc0c477706ce5e121137ae18e0bf4ac9a613bc2c`. It contains 1,475 original sample positions; 1,171 chlorophyll readings pass the implemented source/coordinate QC policy. CHLA_ADJUSTED is selected under the source's A mode. CHLA_FLUORESCENCE remains a distinct unsupported field. Source calibration metadata, raw values, adjusted values and flags remain available.

General source guidance: [Argo data FAQ](https://argo.ucsd.edu/data/data-faq/) and [BGC-Argo chlorophyll reprocessing](https://biogeochemical-argo.org/chla-reprocessing.php). These explain source processing; they do not independently validate this application. Future downloads can change after provider reprocessing. The preparation command rejects changed bytes instead of silently replacing the reviewed file.

The new example lives in `casepacks/instruments/import-examples.json`, separate from the frozen numerical library. An initial attempt to append it to the library changed the fingerprint required by saved investigations. The replay regression caught this. The original library bytes and fingerprints were restored; the new public example uses the normal preview/import workflow. Existing comparisons, source counts and older saved replay retain their original inputs.

## Demonstration path

1. Skip the tutorial, open Tools, then Instruments. The model remains visible beside the profile.
2. Open Import observations and Formats and genuine example files. Preview D2903891_012.nc, inspect counts, then Add profiles to workspace.
3. Close the profile and select its Imported marker. Choose a reading and View nearest model depth. The model date does not change to the observation date, and no comparison is claimed.
4. Preview SR1902594_034.nc and Add. Chlorophyll is selected by default. Inspect the accepted curve, original source field and separate observation/model dates.
5. Use a supported CSV with alternate names to show explicit mapping, review and unit conversion. Test fixtures are analytical test data and must never be presented as real ocean observations.
6. Clear imported profiles. The checked library remains available. Reloading also removes temporary imports.

## Verification

- `tests/test_import_preview.py`: native source comparisons, known chlorophyll count/hash, raw/adjusted values and missing samples; analytical Kelvin/chlorophyll conversion; malformed/ambiguous mappings; original identity; bounded request/response; no case-pack writes; all six examples; immutable library identity.
- Relevant existing parser, evidence, provenance, investigation and guided-case regression: 165 checks passed in `evidence/p16a-science-accepted.log`. This includes older saved investigation replay. Five API/release checks pass in `p16a-release-api.log`.
- `import-review.spec.ts`, `instruments.spec.ts` and `instrument-context.spec.ts`: review/Add/Discard/Cancel, mapping/QC, imported marker selection/clear, Basic fallback, original instrument types, chlorophyll values/dates, moving-position timestamps and dateline fixtures. The first settled set passed 45/45 across Chromium desktop/mobile and WebKit. Final-release and broader regression evidence is listed in the handoff.
- `science.verify_p16a` verifies every genuine example and its model overlap. With `--url`, it also checks that served example bytes and parsed JSON equal the local references.
- `web/benchmarks/p16a-visual.mjs` captures connected and chlorophyll views; manual findings and final public results are recorded separately.

Retained intermediate failures: the initial review-size check counted JSON spacing and wrongly rejected the glider response; compact wire-size accounting fixed it. The initial parser used an exception attribute that did not exist and accepted a malformed units type too late; both are corrected and covered. Adding chlorophyll to the frozen library broke replay and was replaced by the supplementary import catalogue. A first browser run accidentally included Firefox, whose launcher returned `spawn UNKNOWN`; no Firefox success is claimed. A mistyped Python test filename produced no tests; that failed command is retained separately from the accepted run. Existing build chunk-size and dependency deprecation warnings remain.

The first Vercel attempt rejected a 225.18 MB optimized function bundle against its 225 MB cap. The prior public release remained available. The packaging correction excludes developer browser benchmarks, client science-test files and offline `science/verify_*.py` commands from the server function. These files remain in the local source project. Runtime modules and all existing source-pack bytes are retained. Future dataset expansion must budget deployment size; this is not unlimited hosting capacity. The public verifier also initially compared Python coordinate tuples with JSON arrays; normalizing the local reference to its JSON wire form corrected that harness mismatch without changing numerical tolerances or product output.

The first public Python example check timed out while reading an uncompressed response. The verifier now requests and decodes the existing gzip response, as normal browsers do, and records per-example progress/failures. The final run verified all six served files and exact parsed JSON against the local references. The original timeout log is retained; this does not establish universal network reliability. No runtime API change or numerical tolerance change was made to get that result.

## Remaining boundaries

Limits remain 2 MB input, 24 profiles and 5,000 samples per file, 3.5 MB decoded review and 24 profiles/12,000 samples per browser session. The application does not save uploads. The Privacy page still matches request-only processing, filenames in URLs and temporary in-tab profiles. No new account, persistent upload store, external AI provider or secret is added.

Imported numerical comparison/save/replay is P16C. Broader synchronization is P16D. Larger/batch imports and refresh are P16E. P17 security work remains deferred. Automated checks do not replace actual oceanography-user testing, independent scientific review or testing on every evaluator device. P09.5 and the optional external LLM provider remain open. P16B is next only on a separate start instruction; Ultra is recommended for its new-data/standards/portable-installation work.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
