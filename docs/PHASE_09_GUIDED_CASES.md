# Phase 9: guided Indian Ocean cases

Implementation date: 22 September 2026. Historical case dates: 7 to 10 January 2024.

## What changed

Bay of Bengal and eastern Arabian Sea now use the same acquisition, preparation, visualization, comparison, structure search and investigation replay tools. The Arabian Sea pack has seven snapshots, 40 native depths, 76 latitudes and 63 longitudes. Its actual bounds are 66 to 70.9599609375 degrees east and 16 to 19 degrees north. It contains temperature, practical salinity and horizontal velocity components. Missing values are retained. Neither rectangle represents complete basin coverage.

The acquisition uses the original HYCOM GLBy0.08/expt_93.0 archive. Requests run serially, with a source hash and resumable checkpoint for each bounded snapshot. The existing model and Argo parsers required no scientific correction. Pipeline configuration and storage were generalized to accept an explicit case ID. Case IDs remain allowlisted; user strings cannot become file paths.

Source references: [HYCOM GOFS 3.1 analysis](https://www.hycom.org/dataserver/gofs-3pt1/analysis), [archive catalogue](https://wcs-proxy.hycom.org/thredds/catalogs/GLBy0.08/expt_93.0.html), [known archive gaps](https://www.hycom.org/faqs/477-did-you-know-there-are-missing-days-in-the-gofs-31-global-analysis), [Argo attribution](https://argo.ucsd.edu/data/acknowledging-argo/).

Five original INCOIS DAC files produce six profiles. R2902273_172 contains two profile records, so file count and profile count differ. The new observation index is separate from the original Bay index. Bay continues to expose its original 13-profile library. Arabian Sea exposes that library plus six new profiles, including out-of-domain examples with explicit comparison exclusions. This preserves the source identities of existing saved investigations.

Calibration review found delayed-mode adjusted values for 1902671, 1902672 and 5907084, real-time raw values for 7901128, and adjusted real-time parameter modes for the two 2902273 records. Pressure-hysteresis comments are retained in the latter source families. The guide selects delayed-mode 1902671 for its Arabian Sea comparison. Source modes, QC, original values, adjusted values, error fields and calibration text remain inspectable. The original Bay 5907083 provenance hold remains in force. This review does not independently certify sensor calibration.

## The teaching example

At 7 January 2024, 12:00 UTC, the selected Bay column is at 12.359999656677246 N, 87.760009765625 E. The Arabian Sea column is at 16 N, 70.56005859375 E. Their native surface temperatures differ by 0.007000000332482159 degrees Celsius. At 100 m they differ by 4.239000201341696 degrees Celsius.

Selection is explicit: consider every cross-case column pair at that snapshot with finite temperatures at 0 and 100 m and a surface difference no greater than 0.05 degrees Celsius. Select the greatest absolute difference at 100 m. Break ties by the first flattened Bay index, then Arabian index. This example is selected to illustrate contrast. It is not a representative estimate of either basin and does not establish a causal explanation, density contrast or forecast.

The guide displays a common-axis depth plot, a selectable native-depth value table, exact dates, coordinates and the selection rule. The lines connect native samples for readability. Missing values break lines. API values are checked against case fingerprints and native columns before being returned. The source verification script independently repeats the selection with a separate vectorized algorithm using packed source NetCDF files.

## Guided journey

1. Select a study case and choose Start guided investigation.
2. Inspect the two-column example. Open this column selects the corresponding native point and opens the cutaway. Basic graphics remain available.
3. Compare a measurement loads a separate real Argo profile near a model column, at the declared snapshot. It does not imply that this float measured the teaching-example point. The initial Bay comparison has 103 eligible pairs; Arabian Sea has 101. These are sample counts, not accuracy scores.
4. Find warm water applies temperature at least 26 degrees Celsius over 0 to 300 m. It explains that connected cells are threshold regions, not automatically eddies or water trajectories.
5. Save the evidence points to the existing save/replay/export workflow. No step is marked scientifically successful merely because its button was pressed. Previous step, restart and exit allow navigation without a forced onboarding tour.

The study-case selector remains visible in comparison and structure views. Changing cases resets case-specific selections and result panels. Advanced colour and matching controls remain expandable. The new salinity colour default uses outward-rounded minima and maxima from all seven Arabian Sea snapshots. The original 30 to 36 range would saturate values above 36; the new case range includes those values without changing the science. Bay's original manifest and stored replay settings remain unchanged.

Pending calculations can be cancelled. Cancellation stops the client's request and keeps any previous result labelled with its original query. It does not promise to interrupt an already running server thread. Interrupted response-body downloads now remain retryable service errors. Malformed JSON remains a verification error. This fixes the classification, not every possible network or CDN failure.

## Standards and deployment limits

Both cases have native CF-1.10 NetCDF downloads and REST access. The separately tested THREDDS configuration remains scoped to Bay of Bengal. No persistent public THREDDS address is configured, and Arabian Sea WMS/WCS/DAP2 service availability is not claimed. The new access page and API distinguish these scopes.

The model assimilates observations, including Argo. Agreement is not independent forecast validation. Derived structures use the existing P07 numerical method and midpoint-bin volume estimates. The profile pair and guided structure query are educational analyses of historical data, not operational advisories.

## Verification status

- Independent source decoding: all 10,725,120 native scalar values across both cases, seven snapshots and four variables match their packed source files exactly. Display subsets match the declared float32 decimation, including masks. Both exchange files match their checked native temperature snapshot. The selected teaching pair passes an independent exhaustive selection check. Evidence: `evidence/p09-source-verification.json`.
- Original Argo audit: all six added profiles and 2,398 levels checked directly against the five original NetCDF files, including raw/adjusted/error values, flags, modes, source coordinates and depth conversion. Source JULD is preserved exactly; formatted timestamps are checked within their declared second-level presentation. This uses the declared GSW routine and is not an independent validation of GSW physics. Evidence: `evidence/p09-observation-source-check.json`.
- Backend regression: 317 passed. Includes two-case isolation, source checks, rejected mutations, capture/replay/export in all four Arabian modes and replay of original P08 records. Evidence: `evidence/p09-backend.xml`.
- Initial backend failures were a test double missing the new case argument and an incomplete new ocean-recipe test fixture. Both fixtures were corrected without weakening numerical assertions. Initial evidence is retained.
- The initial 198-case local browser run passed 190, failed seven and skipped one unavailable WebKit context-loss injection. Six failures were obsolete single-case copy assertions. One exposed WebKit response-parser classification, fixed by reading the body separately from local JSON parsing. The first guide run exposed an exact-label problem; the corrected guide suite passed all 18 cases. Corrected regression and deployment checks are recorded separately.
- Corrected local regression: all 78 browser cases passed across Chromium desktop, WebKit desktop and mobile Chromium emulation. New guide controls also pass narrow 320 px, enlarged text, reduced motion and keyboard-return checks. Evidence: `evidence/p09-local-corrected-regression.json`.
- Renderer/transport checks: all 26 passed, including numerical geometry and interrupted-body versus invalid-JSON recovery. Evidence: `evidence/p09-renderer-transport-final.txt`.
- Visual audit: 23 captured views across both cases, all five ocean modes, kinetic energy, comparison, search and 800/390/320 px guide widths, without detected horizontal page overflow, visible alerts or uncaught errors. Reviewed representative cutaway, guide, narrow-screen and structure screenshots. Mobile chart labels were enlarged after review. Evidence: `evidence/p09-visual-local-final/`. New explicit guide text/surface colour pairs exceed 4.5:1 contrast; this is not a full accessibility certification.
- Real unfamiliar-user pilot: pending. No participants or task outcomes have been invented. See `P09_USER_PILOT.md`.

## Checkpoint C: official requirement review

The archived official statement is `reference/official-2026/the project brief-statement.txt`. This is a review of that statement, not a claim that submission rules were reissued or rechecked today.

| Requirement | Current implementation and remaining limit |
| --- | --- |
| Browser 3D volume, slices, isosurfaces, time | Working with both bounded historical cases; adaptive Basic graphics. Physical judge devices and Firefox remain unverified. |
| Temperature, salinity, currents | Real checked HYCOM fields. Kinetic energy is a labelled derived product. |
| Instrument markers and profile inspection | Argo, glider, CTD and BGC examples supported. Case overlap and numerical comparability are explicitly gated. Not every instrument overlaps both rectangles. |
| NetCDF and delimited ingestion | Supported, documented schemas and modular adapters. Arbitrary grids, variables and calendars are not automatically supported. |
| Palette, ranges, scale, opacity, vertical exaggeration | Implemented with unit labels, validation and saved settings. |
| REST/OPeNDAP and scalable deployment | Public Vercel REST/viewer/downloads. Separate local Bay THREDDS tested. Persistent institutional hosting, Docker execution and INCOIS installation are unverified. |
| CF and OGC interoperability | Native CF exchange for both cases. Local Bay WMS/WCS/DAP2 evidence retained with coordinate limitations. |
| Extensible sensors and derived/ML products | Adapter/product contracts and tested derived example. No claimed ML prediction or unsupported sensor integration. |
| Outreach and intuitive investigation | Basic guide, definitions and two-region example implemented. Real unfamiliar-user evidence remains P09.5; expanded learning and assistant remain P16. |

P10 expedition and sampling experiments, P11 particle/pebbles simulation, P12 Heat & Depth, P13 El Nino/La Nina/IOD, P14 evolution/blackout, P15 wider coverage, P16 expanded learning/assistant and P17 final release remain planned. This checkpoint does not complete those features, guarantee the ten-day deadline or establish a competition rank.


### Investigation isolation correction

A direct API audit after the first 0.9.0 deployment found that observation-only capture could accept an Arabian-only profile under the Bay case. Numerical values were not fabricated, but the declared case-library identity did not include that record. Comparison already rejected this mismatch. The correction applies the same library membership gate before observation capture or replay. All 36 focused multi-case and investigation tests pass, including original P08 replay. This is a validation correction for an unsupported request, not a change to supported scientific calculations. The final patch is recorded in the release handoff.


### Initial public run and retained rechecks

The 0.9.0 public browser run passed 189 cases, failed eight during loading and skipped one unavailable WebKit context-loss injection. All eight failed cases passed unchanged rechecks against the same deployment, without longer assertion timeouts or application changes. The original report, traces and transfer review are retained. They show pending transfers and several eight-second request aborts; the exact network/CDN/browser/backend contribution remains unestablished. This is not evidence of guaranteed availability.

Trace review also identified a separate unnecessary startup request: an observation query started under an undefined cache key, then was cancelled and restarted for the same default Bay case when the catalogue arrived. The final patch uses the actual default case ID from the beginning. This removes that redundant request; it is not claimed to explain or solve every public timeout. The final patch also enforces observation-only save library membership.


### Final public release

Release 0.9.1 is deployed to the existing Vercel project as dpl_CzrjqNDW5VceE7s3Eo9p73eTEqqk. All 69 final public guide/instrument/investigation browser checks passed. The final case/source/isolation verifier passed 20 checks, the original-record replay/export verifier passed 19, and the release check verified eight public routes and their compiled assets. The scientific values and source fingerprints are unchanged by the final validation/startup patch. Evidence: p09-final-public-browser.json, p09-final-public-http.json, p09-final-original-replay.json and p09-release-check.json under evidence/.

P09.1-P09.4 are technically complete. P09.5 remains pending real participant evidence. This distinction is intentional.

Public screenshots cover 23 distinct views across the first capture run and the focused Arabian/mobile recheck. The first run stopped while waiting for Arabian current rendering after 30 seconds. Its precise cause was not captured by the original harness and remains unestablished. Both public current-component responses subsequently passed, and the unchanged focused screenshot run completed 13 captures with no uncaught errors, visible alerts or page overflow. The original partial run is retained separately. Representative deployed current, guide and narrow-screen images were visually reviewed. This is technical evidence, not a human usability study.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
