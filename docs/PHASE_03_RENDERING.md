# Phase 3: scientific ocean rendering

Implementation date: 22 September 2026, Asia/Calcutta. Release: 0.3.2 (continuity and motion revision). This phase uses the unchanged historical Bay of Bengal package from P02. It does not add a new region, observation source or simulated result.

## Rendering method

Three.js 0.186.0 manages the WebGL2 scene. A custom ray marcher samples a real three-dimensional texture, with front-to-back opacity accumulation. This is volume rendering of model values, not a decorative ocean surface or a stack of screenshots. The independent geographic overview remains available through Geographic context.

The full display grid has 32 longitudes, 39 latitudes and all 40 physical depth levels, for 49,920 samples per scalar snapshot. The initial view selects the original 33 levels from 0 to 1,000 metres. The Full column option restores all 40 levels to 5,000 metres. Neither window invents or redistributes depths. It selects every second horizontal source coordinate plus the final edge. It does not add depth levels or change analytical data. Float32 display values and float64 analytical values remain separate. The case manifest remains SHA-256 `9598b33dc9eef89cb909f2811e1590ca580a143c1dbcc25d97e51a84faf7d28d`.

| View | Method and limits |
| --- | --- |
| Volume | The initial view is a whole volume. Open cutaway beside the scene removes the southeast quarter for viewing and reveals two source-aligned coloured cross-sections. The button closes it again. 160 samples per settled viewing ray (64 during the short cut transition), physical-axis lookup and trilinear interpolation over the irregular rectilinear grid. Finite sampling can miss thin features; use a depth slice and native inspection for numerical examination. |
| Depth slice | Triangles through an actual supplied depth level; scalar colour interpolation is a display operation. A quad with a missing corner is excluded from scientific colour. |
| Section | East-west plane at one of the supplied display latitudes, using actual unequal depth intervals. Missing cells are shown with gray hatching. Arbitrary drawn transects belong to later work. |
| Isosurface | Each complete cell is split into six consistently ordered tetrahedra. Edge crossings are linearly interpolated. A cell with any missing corner is excluded. This is an approximation, not a new analytical feature-volume calculation. |
| Currents | Horizontal speed is derived from the supplied eastward and northward components. Arrows point east and north correctly; no vertical velocity or particle integration is inferred. Direction arrows have equal lengths: 0.35 scene units in 3D and 14 CSS pixels in Basic. Colour and native numeric values encode speed, rather than arrow length. Zero vectors have no direction arrow. |
| Basic 2D | Canvas depth slice or east-west section on physical coordinate axes. Cell colour is the average of four valid corners. Current vectors remain available. Volume and isosurface modes explicitly show a vertical-section fallback. Missing cells are hatched; Basic never claims to extract a 3D isosurface. |

Coordinates use a local equirectangular projection around this small domain's centre latitude, with radius 6,371,008.8 metres. East is positive scene x, north is negative scene z and depth is negative scene y. This local display projection is not the method for future geodesic distance, area or volume calculations. It is not yet suitable for arbitrary global, polar or antimeridian cases.

Vertical exaggeration ranges from 1 to 250 and is labelled. Initial upper-ocean exaggeration is 200; selecting the full column uses 50. Both are display settings, not physical aspect ratios. Depth remains in metres. Changing exaggeration changes geometry only. The default camera and reset fit the domain and depth labels to the viewport. Users can orbit, zoom or use keyboard-accessible camera buttons.

## Colour, masks and inspection

Temperature, practical salinity and horizontal current speed have labelled units. Palettes, minimum/maximum, linear/log mapping and opacity are editable. Invalid ranges show an explanation and use a stated default linear range until corrected. Log mapping requires a positive minimum and hides non-positive values. Scientific false-colour gradients are used only for the data legend and rendering.

The volume opacity transfer function is `1 - exp(-opacity * rayStep * 0.8)`. Opacity is independent of the scalar value, so colder water no longer receives systematically weaker opacity. This replaces the higher-value weighting used in v0.3.0. Brighter lower-range colours and opaque cut faces make the vertical structure easier to see. Opacity and simple depth/surface shading aid inspection; neither is underwater illumination, confidence, probability or a physical water property. Colours in a translucent volume are composited along the view, so they should not be read as an exact point measurement.

Missing source values stay masked. Volume interpolation rejects a location if a contributing corner is missing, allowing only a small floating-point weight tolerance. This can conservatively omit some valid water near a masked boundary. Hatching is the conservative missing-cell boundary, not measured bathymetry. There is no invented seafloor surface or gap filling. The source grid extends to 5,000 metres, but deep cells are missing; the empty 5,000-metre slice is a deliberate verification case.

Clicking a slice, section or isosurface maps back to the nearest native grid point. A cutaway-face click uses that face's physical longitude, latitude and depth. Other volume clicks use the explicitly selected horizontal probe depth. Clicking also updates the inspection-depth control. At overview scale, some native rows project to less than one pointer pixel; zoom or use coordinate selectors when a specific source row is required. The analytical endpoint supplies all 40 native depth values at the selected exact longitude and latitude. The selected original depth index reads directly from this checked column, so changing depth alone does not require another request. Columns must match the displayed field's dataset fingerprint, variable, units, time and coordinates. It is not a colour readback, interpolated display value or estimate at an arbitrary continuous position. Longitude and latitude selectors provide an accessible alternative. Current speed is calculated from the two native component values and both components are shown.

Seven real timestamps from 7 to 10 January 2024 are available. Playback waits for each requested snapshot, advances by the actual 12-hour source interval and stops at the end. It does not invent intermediate frames. While a new timestamp or variable loads, the last verified field stays visible with its original variable, date, colour range, view and isosurface threshold. A small progress notice identifies the pending selection and the field still shown. Scene picking is paused during this interval; a failed request preserves the labelled previous view and offers retry. The new field and its identifying labels switch together, without blending scalar values or timestamps. Reduced-motion preference disables automatic playback while retaining manual time selection.

## Device and failure handling

Auto is the initial setting. WebGL2 failure, shader compilation failure or lost graphics context switches to a real 2D view with an explanation and retry. Failed scientific requests produce a recoverable error, without substituting illustrative data. The existing version-change reload path is preserved.

The renderer caps device pixel ratio at 1.25. Auto observes the browser frame following each draw, excludes hidden-tab and idle intervals, and allows five initial draws for warm-up. Four net slow observations above 55 ms reduce pixel ratio to 0.7. After another warm-up, four net observations above 100 ms switch to Basic. A fast observation reduces the slow count. These are practical responsiveness thresholds, not a measured hardware classification. Balanced 3D lets the user retain 3D without this automatic reduction. Analytical arrays, probe values and source timestamps do not change with graphics quality.

Only dirty frames are drawn. The renderer is dynamically loaded after the case is available. Switching to geographic context retains the explorer and camera while suspending its rendering and playback. Resources are disposed on actual unmount or a switch to Basic. Cutaway, volume-probe and graphics-preference updates reuse the existing texture and geometry where the field is unchanged. The client rejects mismatched variable, unit, timestamp and display-coordinate responses. Current renderer contracts bound each display axis to 64 coordinates; larger datasets need the later subsetting/scale work.

The API compresses eligible responses with gzip. The first temperature display response measured 882,764 decoded bytes and 131,927 compressed bytes locally. This is a real response-size observation, not a general network guarantee. The Three.js scene is a separate dynamically loaded bundle of approximately 580 kB minified and 145 kB gzipped. Vite reports its 500 kB chunk advisory; it is recorded rather than suppressed.

## Verification and reproducibility

```powershell
npm --prefix web run build
npm --prefix web run test:science
.venv/Scripts/python.exe -m pytest tests -q
$env:OCEAN_TEST_REPORT='../docs/evidence/phase-03-local-browser-final.json'
node web/node_modules/@playwright/test/cli.js test --config=web/playwright.config.ts --project=chromium-desktop --project=webkit-desktop --project=chromium-mobile
$env:OCEAN_BENCH_NAME='clarity-verification'
node web/benchmarks/continuity.cjs
```

The 17 pure numerical checks use an independently specified affine field and irregular depths. They cover physical interpolation, masks, metre geometry, depth ratios, sections, isosurface crossings, vector magnitude, log mapping and nearest-coordinate selection. Four checks cover depth windows, coverage counts, source-aligned cutaway faces and the separation of missing-cell hatching from scalar data. One additional check bounds the display-only easing and its reversal/reduced-motion endpoints. The existing 21 backend checks cover source handling and API contracts.

Browser picking checks use an independent perspective calculation and expected values read directly from packed NetCDF integers, with the original scale and offset applied without application adapters. One 100-metre point lies between display nodes but on the native grid; another section point is 1,000 metres deep. A new cut-face fixture at 500 metres is 9.832999517093413 degrees Celsius, read from the packed source independently. A 4,000-metre hatched-face click must return no value. The fixture records the source-file hash in `web/e2e/fixtures/phase-03-source.json`. Both 3D and Basic clicks must recover the expected source coordinates and values.

Browser checks also exercise every view, missing deep water, an empty isosurface, real timestamps, colour/exaggeration invariance, reduced motion, API recovery and missing WebGL. Context loss is injected in Chromium. An explicitly scaled frame clock checks Auto fallback without modifying scientific responses. That test is a failure-path check, not a performance benchmark.

Performance is measured separately without a concurrent browser suite. `web/benchmarks/phase-03.cjs` records the browser, viewport, reported graphics renderer, first-volume latency, request sizes and RAF intervals during repeated camera rotation. Headless Chromium here uses SwiftShader software rendering. WebKit on Windows reports an Apple GPU string, which does not establish physical Apple-hardware coverage. Screenshots cover desktop, 390-pixel mobile and 200% text at 768 pixels. The clarity audit also checks 320-pixel width. Current results are under `docs/evidence/motion-*`; the previous clarity review is under `clarity-*`; original-release evidence remains under `phase-03-*`. The new audit measures RAF intervals in Auto mode, which may switch to Basic during the interval and must not be reported as sustained 3D FPS.

Firefox automation still cannot launch on this Windows installation because of the previously recorded side-by-side binary error. Docker has not been run. Neither is reported as passing. Public browser checks and final release measurements are recorded in the project state.

## Next boundary

P04 adds geospatial instrument overlays, depth-profile charts and supported ingestion workflows. The seven existing Argo records remain a list/record inspector in this release. P05 adds scientific model-observation comparisons. P11 particles, P12 heat/depth and P13 ENSO/IOD remain in the roadmap. This phase completes no claim of live forecasting, independent observational validation, arbitrary global coverage or operational INCOIS deployment.

## Continuity and motion details

Verified historical fields and native columns are cached in browser memory for ten minutes of inactivity. Cache keys separate the application release, case, variable, timestamp and native location; columns additionally use the display field's manifest fingerprint. The case pack is immutable within a release. Data are not written to browser storage. After the selected field is ready, a small sequential queue preloads the next timestamp and other variables at the current timestamp, along with native columns at the current point. Data-saving and 2G connections skip this optional work. No all-ocean or indefinite prefetch runs.

The cutaway uses a 460 ms smoothstep reveal from the surface downward. It changes clipping thresholds only, leaving cross-section vertices, masks and scalar attributes at their original coordinates. Picking pauses during the transition. The moving preview uses 64 ray samples and caps DPR at 0.75, then restores 160 samples and the prior pixel ratio. This reduces drawing cost during motion without changing numerical inspection. An interrupted toggle reverses from its current display progress. Reduced motion applies the endpoint immediately.

A new field/view has a short 180 ms opacity arrival; datasets are not cross-blended. The first request still needs network time and has a loading explanation. Subsequent uncached requests retain the verified scene. No fabricated loading percentage or completion counter is shown. Cold loads, slow software graphics and remote service errors remain possible.

The browser suite verifies no extra source requests for depth changes, constant texture/rebuild counts for cutaway changes, correct labels and thresholds during slow updates, cached revisits, failure/retry, cancellation of an abandoned timestamp, reduced motion, geographic-context preservation and rejection of mismatched native coordinates. The original independent NetCDF checks remain in place. `web/benchmarks/interaction.cjs` records the request counts, individual action timings and transition frames separately from the test suite. A mixed animation/idle RAF interval is not a sustained 3D frame-rate claim.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
