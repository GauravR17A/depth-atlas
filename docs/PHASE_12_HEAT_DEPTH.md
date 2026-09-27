# Phase 12: Heat & Depth Lab

Project date: 23 September 2026. P12.1-P12.5 are complete. Release 0.12.0 is deployed on the existing Vercel project, with scientific method p12-heat-v1. Source preparation, numerical acceptance, public API/export checks, exact replay in both platform directions, browser checks and visual review have passed within the supported scope.

## Intended supported workflow

Choose one of three fixed SST locations in either the Bay of Bengal or Arabian Sea study rectangle. Inspect daily NOAA OISST analysed SST in 2023 or 2024 against the declared 1982-2011 seasonal baseline and 90th-percentile threshold. Select an actual detected event to inspect dates, duration and intensity. Original event boundaries remain visible even when they cross the displayed year.

For an event overlapping the available 7-10 January 2024 HYCOM case, choose an overlapping model snapshot and inspect the nearest native column. Temperature, practical salinity, density, actual-depth gradients and stratification remain separate quantities. Two mixed-layer criteria and a fully defined column potential-enthalpy integral expose their assumptions and missing-support states. Source profiles retain their own locations, dates, quality flags and provenance review status.

When an event has no supplied depth coverage, the app explains the gap. It does not relabel another January column as that event's subsurface conditions. Every surface point remains in the catalogue regardless of whether it has an event. These are historical source analyses and derived diagnostics, not forecasts or basin-wide heatwave maps.

## Sources and method

See [surface source acquisition](P12_SURFACE_SOURCES.md), [independent method review](P12_INDEPENDENT_METHOD_REVIEW.md) and [API and export contract](P12_API_CONTRACT.md). D040-D043 record the substantive choices. OISST is a blended/interpolated surface analysis; HYCOM and the original instrument profiles are distinct sources. Data years remain separate from the 2026 project date.

Each of the six fixed cells has 16,071 daily values covering 1982-2025, with no missing temperature. All 10,957 baseline days are present at every cell. NOAA AOML supplies 14,966 dates, and retained NOAA PSL records supply 1,105 dates absent from AOML. This is a source merge, without temporal interpolation. The pack is 7,386,504 bytes. Its manifest SHA-256 is `b2c1186439af2a66c982392961145300f0c015792327b6b96721216278d15fff`.

The two distributions retain a small checked packing difference. Across 6,282 overlapping point-days, 973 differ by no more than one Float32 step, with a final maximum of 3.814697265625e-6 degrees Celsius; all remain in the same original centidegree bin. Original NCEI packed integers explain the tested decoding alternatives. The served values are preserved. Both preparations reproduced the manifest and all six location hashes exactly, and all 96,426 point timestamps reconstructed from their original per-file units. See `evidence/p12-source-rebuild.json`, `evidence/p12-source-packing-diagnostic.json`, `evidence/p12-distributor-comparison.json` and `evidence/p12-time-provenance-resume.json`.

The baseline uses all daily data from 1982 to 2011. For each calendar day, pool the five actual days before and after every occurrence inside the baseline. Clip at baseline edges. Calculate the mean and linear 90th percentile, interpolate the February 29 climatology before smoothing, then apply a 31-day circular average. Events need at least five consecutive days strictly above the threshold. Already-qualified events can merge across at most two finite intervening days. Unknown days are never filled or bridged.

Detection uses the supplied 2022-2025 context before selecting a display year. Boundary flags show where available context does not establish a complete start or end. Intensity means SST minus the seasonal mean. Merged duration and intensity accounting include observed intervening cool days.

The depth method uses GSW 3.6.20 with the original in-situ temperature, practical salinity, coordinates and native levels. It computes pressure, Absolute Salinity, Conservative Temperature, potential temperature, sigma0 and in-situ density. Adjacent valid levels supply signed temperature gradients and N-squared, retaining negative stratification values. Model temperature is not silently treated as potential temperature.

Derived mixed-layer depth uses a 10 m reference and the first crossing of either sigma0 increase 0.03 kg/m3 or absolute potential-temperature change 0.2 degrees Celsius. Each estimate reports crossing, no crossing, missing support or unavailable reference. It is not a supplied HYCOM MLD field. The no-crossing bound applies to the selected depth window.

Column potential-enthalpy content relative to CT=0 is the trapezoidal integral of rho times cp0 times CT from 0 m to a supported native limit of 100, 300, 700 or 1000 m. Its value is in J/m2, displayed in GJ/m2. Missing input prevents a complete integral. No subsurface climatological anomaly, heatwave excess, cyclone-energy prediction or causal attribution is claimed.

## Integration and verification

The existing workspace, case selection and investigation system are reused. Saved records require the applied event selection and include surface-source identity, method, baseline curves, selected-year daily values, complete event boundaries, model diagnostics and source references. JSON, readable HTML and numerical CSV/ZIP exports retain these definitions. Existing recipe/source identities are preserved.

All 590 backend tests pass with zero skips in `evidence/p12-final-backend.xml`. This includes 76 independent scientific tests, separately recorded in `evidence/p12-independent-final.xml`, and 33 new heat API/integrity/export tests. The scientific checks cover six complete OISST series against the pinned Oliver implementation, exact event dates and durations, 18 exact primary NCEI comparisons, calendar/missing-data rules, eight original HYCOM columns, version-matched GSW check casts, separate quadrature and a closed-form integral. Initial checks remain in `evidence/p12-independent-initial.xml` and `evidence/p12-early-backend.xml`.

The older GSW 3.05 published Absolute Salinity example differs slightly from the pinned 3.6.20 implementation. The actual matching-version upstream check cast was used, and all 98 finite reference values matched exactly. Original discrepancy evidence is retained rather than hidden by widening a tolerance. See `evidence/p12-gsw-reference-selection.json`.

The 26 existing renderer tests pass. The existing browser suite passes 248 checks with one inherited WebKit context-loss injection skip. The first P12 browser run passed 23 and failed four: three tests incorrectly assumed that selecting display year 2023 precluded an event extending into January 2024, and one exposed a real 320 px WebKit select-overflow defect. The tests now choose an actual non-overlapping event, and the select contains long labels. The subsequent local P12 suite passes all 27 checks. Initial reports and failure artifacts remain in `evidence/p12-browser-local-initial.json` and its companion artifact directory. The final suite is `evidence/p12-browser-local-final.json`.

Final public browser acceptance passes all 54 Heat and saved-investigation scenarios across Chromium desktop, WebKit desktop and Chromium mobile emulation, with no failures, skips or flaky tests. The report is `evidence/p12-public-browser.json`. The final public visual run captures 20 views with no page errors, document overflow or unexpected alerts, recorded in `evidence/p12-visual-public/checks.json`. The frontend reviewer manually inspected the public Bay surface graph, temperature gradient, Arabian unavailable-depth panel and 320 px surface chart. A second review also inspected the public Bay surface and depth panels and the 320 px view. The source curves remain distinct, gradient labels retain meaningful precision, and narrow charts use clearly indicated horizontal scrolling. No public correction or retry was needed. Local refinement results and the 20-view final local capture set remain retained separately.

The local HTTP verifier passes 88 checks across 85 requests with no retries, in `evidence/p12-local-http-initial.json`. It checks all six points and both years, actual Bay depth diagnostics at four limits, eight new captures/replays, numerical CSV/ZIP output, rejection paths and all 20 retained P08/P10/P11 records. The eight new records are retained in `evidence/p12-local-records.json`.

The public release passes 105 checks across 101 HTTP requests, with zero failures and no retries, in `evidence/p12-public-http-initial.json`. The same source, diagnostic, export and compatibility checks pass on Vercel. All eight Windows-produced heat investigations reproduce their complete scientific results and numerical ZIP contents exactly on the deployed service. The eight new Vercel records are retained in `evidence/p12-public-records.json`.

All eight Vercel-produced records also replay and export exactly on the Windows server. This reverse check passes 19 checks across 17 requests in `evidence/p12-public-to-local-replay.json`. No numerical tolerance was weakened, and no new platform-specific arithmetic correction was needed. The 76 independent tests are included in the 590 backend total; exact replay checks are included in the corresponding HTTP totals rather than additional unique tests.

## Demonstration and remaining limits

Open the [public workspace](https://depth-atlas-seifuku.vercel.app/), choose the Bay of Bengal study case, and open Heat & Depth through the toolbar or Heat on the navigation rail. Use the centre point and event year 2024, then select Analyse surface record if the controls contain unapplied changes. Identify the analysed SST, seasonal mean and threshold. The selected full event spans 11 October 2023 to 10 February 2024; its peak is in December, outside the displayed 2024 graph. Inspect a dated visible daily sample. Displayed values are rounded for reading; exports retain the numerical values.

The 7 January model snapshot supplies a separate native depth column. Change Depth variable, compare the two mixed-layer criteria, and change Column and integration limit. Select an event without January overlap to show the absence of depth evidence. Use Save heat investigation, give it a title and save it on the browser. Recalculate the saved record and download its evidence ZIP. Inspect the daily source series, seasonal curves, full event table and any supported depth tables.

Switch to the Arabian Sea case to inspect its genuine surface events and explicit absence of overlapping depth evidence. None of its detected events at the three selected cells overlaps the supplied model period. Changing display year alone does not guarantee unavailable depth: a full event can begin in one year and extend into the next. The app retains the actual event boundaries and source dates.

Surface events do not establish a subsurface marine heatwave. Source and numerical agreement do not establish independent ocean validation. The real unfamiliar-user pilot, physical-device coverage, Firefox runtime, Docker execution and persistent public standards hosting remain separate project limitations.

Next planned phase is P13 Climate Event Lab, only after P12 acceptance and a separate user instruction. Ultra remains recommended for its event/index definitions, seasonal alignment and new Pacific source coverage.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
