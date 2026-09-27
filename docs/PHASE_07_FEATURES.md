# Phase 7: connected structures and drawn sections

Implementation date: 22 September 2026. Dataset dates: 7 to 10 January 2024.

## Scope and scientific meaning

The Find structures workspace queries one actual model snapshot. It supports in-situ temperature, practical salinity, eastward velocity, northward velocity and derived horizontal kinetic energy. A query records its variable, exact units, timestamp index, inclusive threshold or closed range, and minimum/maximum depth. No natural-language interpretation or hidden threshold is involved.

Search uses every native float64 sample, never the decimated rendering grid. A sample qualifies only if it is finite, satisfies the numerical comparison, and its depth coordinate falls inside the closed requested interval. A qualifying sample must also have positive inferred cell thickness after clipping. Six-face neighbours connect through one native depth, latitude or longitude index. Diagonal contact, missing samples and excluded samples do not connect.

The source supplies point coordinates without cell boundaries. Consequently the implementation cannot honestly claim a measured or provider-supplied water volume. It infers boundaries halfway between coordinates, truncates outer boundaries at the first/last sampled coordinates, and clips depth boundaries to the query interval. Each point value is treated as constant within that inferred bin. The displayed quantity is **estimated volume**. Irregular depth spacing and changing latitude area are retained. Seabed position between sampled depths remains unknown.

Volume integrates a spherical shell with radius 6,371,008.8 m. For positive-down depths a and b, the radial factor is `(b-a) * (3R² - 3R(a+b) + a² + ab + b²) / 3`, multiplied by longitude width in radians and the sine difference of latitude boundaries. Division by 10^9 converts cubic metres to cubic kilometres. Both native centre extents and inferred cell extents are returned. Arithmetic sample mean and volume-weighted mean are separate fields.

The ID of a region uses its smallest global flat index in depth/latitude/longitude order. IDs are query-specific, not persistent identities of a water body. Ranking by estimated volume or eligible sample count does not change membership. The API returns the first 50 region summaries in that order and reports total regions/cells separately. The plan view shows the shallowest qualifying region per horizontal column, so deeper components can be selected through the list.

## Geometry and sections

Each selected surface follows the exposed faces of inferred native cells. Coplanar rectangles merge without decimating or moving the boundary. The mesh is a visualization of the query's inferred bins. Depth exaggeration affects presentation only. The bounded fallback for more than 40,000 merged faces retains the footprint, numerical result and section instead of substituting a misleading simplified surface.

A drawn section is a straight segment in longitude/latitude. Its default 81 equally spaced stations include both endpoints. Each station selects the closest native column by great-circle distance, with deterministic first-index ties. Every selected native depth is retained. The section returns requested coordinates, sampled column coordinates, offset, cumulative station distance, source value and component membership. There is no horizontal or vertical interpolation, and missing values remain null. The station count is bounded to 2 through 201. Line geometry and sampling offsets remain explicit.

## Observation context

Temperature and practical-salinity evidence reuse the tested P05 matcher and source holds. Defaults are a 6-hour absolute time window, 5-km native-column separation, maximum 500-m depth bracket and good/probably-good source quality. Eligible source samples are associated with the qualifying inferred depth bin in their matched native model column. Exact interior depth midpoints belong to the deeper bin; the final boundary is closed. Observation depth must also fall in the query interval. This is nearby model-column evidence, not proof that the observed value satisfies the threshold.

Section observations must pass the same P05 gates and lie within 5 km of a requested section station. This is a sampled proximity rule, not an exact continuous corridor. Changing station density can change those links. Velocity and kinetic energy have no comparable profiles in this library and do not receive invented observation matches. The provenance-held Argo source, incompatible definitions and out-of-time or out-of-domain examples stay excluded.

## Interfaces and limits

- `POST /api/cases/{case_id}/features/search`: `FeatureQuery`.
- `POST /api/cases/{case_id}/features/region`: query plus query-specific region ID.
- `POST /api/cases/{case_id}/features/section`: query, two `[longitude, latitude]` endpoints and optional station count.
- Exact units, finite values, increasing query bounds, source timestamps, domain bounds and supported operators are validated.
- Native analysis is bounded to 250,000 cells and 5,000 components. The pinned case has 191,520 native cells.
- A small process cache holds immutable source-derived results. Ordering does not trigger fresh analysis. No query account, database or durable investigation is created.
- Numerical JSON exports contain query/result/source identity and section values. Durable saved investigations, fresh-session replay and share links remain P08.

## Acceptance evidence

The local backend suite passed 281 tests, including 83 independent P07 tests and 22 request/geometry checks. The renderer suite passed 24 tests. The independent P07 verifier passed 99 local HTTP checks against original-source expectations. The existing standards verifier passed 143 checks again, and a separate audit matched all 56 native/display arrays across seven snapshots exactly, including missing masks.

The initial local 144-test browser run passed 140, failed three new pointer-test precision assertions and skipped one unavailable WebKit context-loss check. The pointer tests now use the browser's delivered event coordinates, rather than impossible subpixel placement assumptions. All 27 feature/scientific UI tests passed after correction. They passed again on the final 0.7.1 accessibility build. The standalone final visual audit passed 35 checks across Chromium, Windows WebKit, 390 px, 320 px and 768 px at 200% text. Actual screenshot inspection, rather than counters alone, identified and verified the small-screen fixes.

Release 0.7.0 was deployed and its full public suite passed 148 checks, with four loading timeouts and one deliberate skip. All four timeout checks passed unchanged on focused recheck. Traces show requests canceled around the existing eight-second client deadline; they do not establish the underlying network/server cause. Reports and traces are retained.

Release 0.7.1 adds bounded scrolling charts and readable enlarged-text controls. Its full public browser run passed 144 checks, failed eight during loading and skipped the same unavailable WebKit context-loss injection. All eight passed unchanged on focused recheck in 23.4 seconds. Independent review of every failed trace found 25 incomplete or failed transfers and no HTTP error response. Three tests stalled on the main static script before application code ran; API reads also hit the existing client deadline, and the WebKit feature POST reported a browser transport error. No returned numerical mismatch or application exception was demonstrated. The transport cause remains unresolved, so these passing rechecks do not establish uninterrupted availability.

Final public acceptance is complete for the declared scope. All 35 public visual checks passed across five configurations, with zero page errors and actual screenshot review. After that review, all 99 independent P07 HTTP checks passed against release 0.7.1, including original-source query memberships, sections, meshes, observation associations and errors. The existing HTTP verifier also passed all 49 checks over 50 requests, including the full native NetCDF checksum, source-derived kinetic energy, legal routes and static assets. Vercel inspection confirms the normal public alias points to production READY deployment `dpl_dfApBFR6zxN9wtK3Uo4ZXd74J3rR`.

Key records under `evidence/`: `p07-science-api.xml`, `p07-independent-science.xml`, `p07-local-source-api.json`, `p07-protocol-verification.json`, `p07-audit-existing-source-arrays.json`, `p07-local-browser.json`, `p07-local-accessibility-browser.json`, `p07-local-071-features-visual.json`, `p07-public-browser.json`, `p07-public-browser-recheck.json`, `p07-public-timeouts.json`, `p07-public-071-browser.json`, `p07-public-071-browser-recheck.json`, `p07-audit-public-071-failures.json`, `p07-public-071-features-visual.json`, `p07-public-source-api.json`, `p07-public-existing-http.json` and `p07-release-check.json`.

## Defects found and corrected

- Basic current directions now account for plot aspect ratio and longitude convergence. Source speed and values are unchanged.
- Equal longitude widths are subtracted before conversion to radians, avoiding spurious unequal-volume ordering.
- Observation depth bins use unclipped midpoint edges for lookup, preserving exact inclusive upper-query boundaries before the clipped membership check.
- SVG picking uses the actual screen transform, including letterboxing and horizontal scrolling. Outer map boundaries no longer wrap to the first cell.
- Missing sections have no invented numeric colour scale. Constant sections identify their constant value. Exact depth-midpoint clicks follow the declared deeper-bin rule.
- Query thresholds retain their exact entered values; small positive quantities do not display as zero. Narrow depth intervals retain distinct tick labels, and returned section endpoints remain separate from draft inputs.
- The initial region camera exposes the side boundary and labels both the inferred depth extent and the selected exaggeration.
- The 320-pixel toolbar wraps, WebKit dropdown text is no longer clipped, and the full exaggeration value remains visible at 200% text. On narrow screens, charts retain readable axis labels inside keyboard-accessible horizontal scroll areas; the page itself does not overflow.

No current result is promoted to an eddy, a material trajectory, confidence score or validated forecast. Unknown-device performance, actual unfamiliar-user comprehension, Firefox and institutional deployment remain explicitly unverified.

Independent review: [P07_SCIENCE_REVIEW.md](P07_SCIENCE_REVIEW.md). Existing-component audit: [P07_COMPONENT_AUDIT.md](P07_COMPONENT_AUDIT.md).


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
