# Phase 5: model comparisons and observation coverage

Build date: 22 September 2026. Completed release: 0.5.0. Acceptance is recorded below. The January 2024 model dates are historical source dates.

## Implemented scope

The Compare workspace connects the checked observation library to the existing Bay of Bengal model. It provides observed/model profiles, model-minus-observation residuals, a shared depth cursor, native model-column navigation, exclusion explanations, actual observation coverage, eligible-record discovery and a temporary sensitivity reference. Comparisons support in-situ temperature and practical salinity. Imports remain inspectable in Instruments and are not included in quantitative comparisons.

Only this bounded model case is available. Glider, CTD and BGC examples keep their actual regions and dates. Their presence in the observation library does not extend model coverage.

## Reproducible method

The versioned method is `p05-native-column-v1`. `science/evidence_contracts.py` defines settings, comparison rows and coverage records. `science/evidence.py` is the pure numerical matcher. `api/evidence_store.py` binds it to immutable, hash-checked arrays and library profiles with bounded process caches.

1. Choose one actual model timestamp. Each source sample retains its own timestamp. Signed offset is observation minus model time; the absolute value must be within the selected tolerance. The tolerance applies on either side of the selected snapshot, including collection endpoints. No model value is inferred at the observation time.
2. Require compatible physical definitions and units. Both temperature fields are in-situ Celsius, and salinity is practical salinity. Do not substitute potential or conservative temperature, or absolute salinity. CTD temperature needs a confirmed ITS-90 scale before quantitative use. The current cruise source does not supply that confirmation.
3. Preserve source variable and coordinate QC. Good-or-probably-good uses the existing P04 policy; good-only narrows Argo and declared flags to 1. QARTOD 1 and WOCE 2 retain their own meanings. A user setting cannot rescue a reading rejected by the source adapter.
4. Require a valid physical depth and coordinates inside the native rectangular subset. Search all native horizontal grid points by great-circle distance with Earth radius 6371.0088 km. Resolve an exact tie by the first native index. Require separation within the selected distance limit. Do not search for a replacement wet column.
5. Read the full-resolution analytical array, not the display grid. Interpolate linearly at the actual observation depth between the immediately adjacent finite native levels. An exact native level needs that cell only. Reject depth extrapolation, a masked endpoint or a bracket wider than the configured maximum. The existing GSW pressure-to-depth calculation remains unchanged.
6. Calculate residual as model minus observed. Bias is mean residual, RMSE is the square root of mean squared residual, and MAE is mean absolute residual. N counts accepted original samples, with equal sample weights. Source order is retained, including nonmonotonic casts and gaps.

Defaults are a 6-hour window on either side, 5 km separation, a 500 m maximum native bracket and good-or-probably-good QC. They are project choices, not universal scientific thresholds. Adjustable bounds are 0-72 hours, 0-50 km and 1-1,000 m. Each rejected sample receives one first-failed reason. The gate order in the matcher is authoritative, so reason counts add to the excluded count without double counting.

Coverage uses the same comparison results. Depth strokes are actual accepted sample depths. Time and distance ranges describe accepted samples when pairs exist; empty profiles retain source time offsets only to explain the mismatch. Dashed model bounds are separate context. There is no spatial confidence field, interpolation of observation coverage or inference about unsampled water.

Discovery ranks currently eligible profiles by absolute time separation followed by distance, or by their largest absolute residual. When the selected snapshot has no eligible pairs, it can suggest another bundled snapshot. Applying that suggestion is an explicit action. Ranking by residual is a navigation aid and must not be presented as an unbiased assessment of the model.

## Source review hold

The original `D5907083_012.nc` calibration comment contains verification-run wording. A fresh HTTPS download is byte-identical to the cached source, with SHA-256 `17f3e33d95003693c24b7fc5737b1dbe9369334b6ffce679964288b5f96483dd`. Its meaning has not been established with the provider. This file is held out of quantitative comparisons under `source_review`, while its readings and unchanged source QC remain inspectable. The decision is based on provenance text, not residual size. It is not a claim that the source is fabricated or a provider QC rejection.

P05 also preserves original scientific calibration comments, equations and coefficients in the instrument metadata. Regenerating the 13-profile observation library changes its derived files and index, but not the original source hashes or P02 model manifest. Model manifest SHA-256 remains `9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d`.

## Independent numerical references

`science/verify_p05_reference.py` reads original NetCDF files without importing the application matcher. It manually decodes source packing into float64, independently scans the native grid and evaluates scalar depth interpolation. `tests/fixtures/p05-source-reference.json` freezes seven profiles, 720 source rows, four snapshots, 576 count scenarios and 12 labelled synthetic edge probes. Synthetic probes are test data only and never appear as observations in the application.

The first Argo 1902669 sample is 0.3976914255 m deep. At the January 7 noon model snapshot, its interpolated model temperature is 28.0013865286 degrees Celsius, its observation is 28.1529998779 and its residual is -0.1516133493. Practical salinity is 33.7670006539 versus 32.8320007324, giving +0.9349999215. These values were also checked against a bounded live HYCOM ASCII response.

The default January 7 noon settings yield 206 pairs across Argo 1902669 and 4903775 after the provenance hold. A 2-hour window yields zero. A 100 m maximum native bracket yields 124 pairs; 25 m yields 50. January 8 noon yields 103 pairs and January 9 noon yields 307. These are acceptance references for this case, not a coverage or performance claim for the wider ocean.

See [P05_SCIENCE_REVIEW.md](P05_SCIENCE_REVIEW.md), [source audit](evidence/p05-source-audit.json) and the frozen fixture for original URLs, packing details and hashes.

## API and browser behavior

- `GET /api/cases/{case_id}/evidence/profiles/{profile_id}` returns every original source row, its eligibility, original/paired values, source QC, time and distance, bracket/weight, residual, metrics, methods and caveats.
- `GET /api/cases/{case_id}/evidence/coverage` returns counts, actual accepted depths, accepted time/distance ranges, exclusions and optional snapshot suggestions for all checked profiles.
- Both use the same bounded `variable`, `time_index`, `time_window_hours`, `distance_km`, `max_vertical_gap_m` and `qc` settings.
- Responses include method, model-manifest and observation-library identities. The library identity hashes a canonical sorted compact JSON serialization of the index. It is not the byte hash of the pretty-printed index file.
- The browser validates contracts, counts, residual arithmetic, summary metrics and requested settings before showing results. Cache keys include release, case, profile and all settings. A pending selection does not relabel an earlier result as the new one.
- The model and comparison share one timestamp control state. Instruments' older nearest-depth action remains navigation only. The matched-column action explains that the 3D probe uses the nearest native depth while the numerical comparison uses physical-depth interpolation.
- The sensitivity reference stays in browser memory, including its original profile, variable, snapshot and filters. It is cleared on reload. Durable replay/export is P08 and is not claimed here.

## Acceptance and deployment

Completed P05.1-P05.5 and feature rows R05, X04 and X05. X06 remains partial because its durable replay requirement belongs to P08.

- Build/typecheck passed. The frozen reference regenerated byte-identically with `--check`; its SHA-256 is `4773abc59e39596bc2d4cff951a40a805d6d3463f7dc173992b20ea1a7d574c9`.
- `.venv/Scripts/python.exe -m pytest tests -q --junitxml=docs/evidence/p05-science-api-final.xml`: 137 passed, including 85 matching checks and a calibration-text fidelity regression. Two existing Starlette/AnyIO deprecations remain.
- `npm --prefix web run test:science`: 17 renderer numerical checks passed.
- Full local browser run: 116 passed and one deliberate WebKit context-loss skip in `evidence/p05-local-browser-final.json`.
- Full public browser run: 113 passed, three failed, one deliberate skip in `evidence/p05-public-browser-final.json`. All 18 new comparison checks passed. The failures were one native-value loading timeout, one page-load timeout and a test locator matching two alert panels. The service-update assertion was scoped to its own alert; the two loading cases were unchanged. All three passed in `evidence/p05-public-browser-recheck.json`. Original failure traces/screenshots are retained in `evidence/p05-public-initial-failures/`. No claim is made that intermittent network delays are eliminated.
- The initial new-feature browser run had 15 passes and three failures from an outdated expected message after the explicit snapshot action was added. The test wording was corrected; the full local and public comparison checks passed. Keep `evidence/p05-browser-new-initial.json`.
- Public HTTP audit: 66 checks across 70 GET requests passed in `evidence/p05-public-http-release.json`. It verifies every library profile in both variables, 12 coverage scenarios, independently frozen values/metrics, source identities, exclusions, release/API errors and assets. No audit request failed and the script does not automatically retry.
- Desktop Chromium, Windows WebKit, 390/320-pixel widths and 200% root text passed the final comparison/coverage/rules layout audit: `evidence/p05-public-final-visual-review.json`. There is no page overflow or captured page error. A Go to results link is checked, and a footnote-width assertion prevents an inherited sidebar width from returning. The earlier public screenshots exposed that width defect at enlarged text; it was corrected by giving the comparison footnote its own CSS class. These checks emulate device sizes and do not certify physical phones or Safari on Apple hardware.

Final Vercel deployment: `dpl_DDofskrZKtLVQkJmBVupBpnUybZZ`, READY. Public URL: https://depth-atlas-seifuku.vercel.app. Unique URL: https://depth-atlas-seifuku.vercel.app. The first 0.5.0 deployment was `dpl_4wGDN2zpQttV8KJH5b4B5XJRTv16`; the second changes only the conflicting footnote CSS class and associated build assets. Scientific code and case data are unchanged between these deployments.

The first public HTTP run passed 63 checks and failed three overly strict Windows/Linux static-byte comparisons. Investigation found generated asset-name references, HTML newline differences and exactly one 21-byte CSS rule, `.table{display:table}`, emitted locally from a test-file token excluded from deployment. JavaScript matches after normalizing generated filenames. Final checks allow only these demonstrated differences while keeping all other code, CSS and scientific data comparisons strict. Preserve `evidence/p05-public-http-initial.json`, `evidence/p05-public-asset-differences-final.json` and the earlier follow-up audit.

The final workspace bundle is about 514.74 kB minified, 166.01 kB gzip; the renderer is about 581.03 kB minified, 145.65 kB gzip. Both trigger Vite's 500 kB advisory. No performance guarantee is inferred. Broader loading/device improvements remain measurable work. Firefox cannot launch in the current Windows setup, Docker is unavailable and actual INCOIS installation remains unverified.

The roadmap audit preserves all 17 phases, 82 steps and 45 feature rows; authored P05 UI/method text contains no em dashes. See `evidence/p05-continuity-audit.json`.

## Limits and next phase

The HYCOM analysis assimilates observations including Argo. Agreement is not independent validation, forecast skill or operational improvement. Profiles contain correlated samples, unequal depth spacing and no area weighting. This implementation does not interpolate in time or horizontally, compare currents/BGC variables, accept arbitrary uploads into matching, provide live feeds or establish observing-system impact.

P06 adds standards services and an extension contract. Extra High is recommended. WMS/WCS and OPeNDAP require actual tested protocol responses; a REST endpoint with similar naming is not sufficient. The Vercel app remains the public host, while service placement and available infrastructure must be verified in that phase.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
