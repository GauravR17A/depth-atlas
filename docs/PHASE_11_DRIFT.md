# Phase 11: Drift Lab

Project date: 23 September 2026. Sources: 7-10 January 2024. P11.1-P11.5 complete in release 0.11.1, method p11-drift-v2. Deployed on the existing [Vercel application](https://depth-atlas-seifuku.vercel.app/). Scope and acceptance evidence are recorded below.

## What users can do

Drift Lab releases passive tracers into either checked historical study area. A user chooses a point or a rectangular release area, one native depth from 0 to 1000 m, a source starting snapshot, 1 to 72 whole hours and 1 to 64 particles. The available source end bounds the duration. Unsupported requests fail clearly instead of silently shortening a trajectory. An optional target rectangle records first simulated entries.

The default uses 24 particles in a small central box over 24 hours. A point release has identical paths under identical forcing; no artificial jitter is added. Box releases use a pinned seeded generator, uniform in longitude and latitude rather than exactly uniform in area. Invalid release locations remain in the reported totals.

Run A and optional Run B retain their own applied settings. The user can change release location, date, depth, seed or duration and compare the results. A shared elapsed-time slider does not imply equal calendar timestamps. Each run retains its actual historical start and end. Changes to draft controls do not relabel completed paths or saved results.

The map has a study-area view and a fit-paths view, keyboard coordinate alternatives, an individual particle inspector and a complete results table. Start-snapshot current arrows provide context and remain explicitly static. Press Play to animate calculated output points. Rendering interpolates these points for visual continuity; it does not supply additional numerical integration or physical detail. Reduced-motion settings pause automatic playback changes. There is no decorative random motion.

## Numerical method

The production kernel adapts OceanParcels 3.1.4 `AdvectionRK4`, retaining the four-stage weighted displacement calculation. The array runner, data adapter, strict masks, progress stream and export logic belong to this application. We do not claim to ship the complete OceanParcels runtime on Vercel. Upstream MIT licensing and the source file identity are retained in `science/vendor/` and public third-party notices.

The full pinned framework is installed separately for offline reference checks using `requirements-drift-reference.txt`. This keeps its xarray, SciPy, Dask, Zarr and compiler-related dependencies out of the public function. The existing NumPy runtime is sufficient for the bounded runner. This replaces the initial separate-worker plan for P11's small checked cases; a durable worker/queue remains a possible later scaling choice, not an undeployed hidden dependency.

Both current components come from the same native rectilinear HYCOM z-level grid. Metadata declares eastward and northward m/s, so no additional grid rotation or staggering adjustment is applied. Interpolation is bilinear in native longitude/latitude and linear between available times. The depth is fixed at a selected native level. No vertical velocity, extrapolation, nearest-wet relocation or fill-to-zero conversion is introduced.

At every Runge-Kutta stage, velocity converts to angular motion using 111120 metres per latitude degree and the same factor times cosine(latitude) per longitude degree, matching the Parcels convention. A fixed-order binary64 cosine polynomial on the explicitly bounded latitude domain avoids platform-dependent trigonometric calls. Independent tests compare its accuracy across the supported domain and its trajectories against the full framework. Source values and numerical trajectories are not rounded to weaken replay checks.

Allowed integration steps are 300, 600 and 1200 seconds, default 600. Whole-hour duration and 12-hour source boundaries are exact multiples. Output cadence is `lcm(1800, timestep)`: 1800 seconds for 300/600 and 3600 seconds for 1200, with the last accepted point retained. Display cadence does not change the solver. Integration cannot reconstruct current variability absent from the source snapshots.

## Boundaries, arrivals and distance

A complete finite U/V interpolation cell is required, including zero-weight spatial corners under the declared conservative rule. Exact-time point samples use that snapshot alone; movement through a time interval requires the source brackets supporting that interval. Every stage and endpoint must lie inside the source domain. The full rectangle of traversed interpolation cells must also remain supported. This deliberately conservative check prevents crossing an unsupported strip but can stop earlier than a geometric coastline intersection.

A failed step retains the last accepted position and elapsed time. Status distinguishes completed duration, leaving the study area, missing current support and invalid initial release. These are not observed beaching events or exact collision times. A stopped marker remains at its last supported point.

Target arrival is the first intersection with a closed target rectangle along an accepted integration-step segment. Time is interpolated linearly within that step, so this is an approximate numerical entry time. Valid initial particles already inside arrive at zero. Invalid releases never become arrivals. Arrival fraction uses all requested particles, including invalid releases; mean path distance uses valid releases only. Arrival can occur before a later early stop.

Distance accumulates the midpoint spherical-metric length of each accepted step. It is an approximation to the calculated path length, not endpoint separation or a navigable travel route. Neither arrivals nor comparisons form real-world probabilities or calibrated uncertainty.

## Jobs, cancellation and reproducibility

Calculations are request-scoped jobs. POST `/drift/stream` emits actual completed integration-step counts and then a complete checked result. Work is chunked at no more than 12 solver steps between progress events. Cancelling disconnects the browser request; the server stops after the current bounded chunk. No partial result is saved or cached. A failed or cancelled request keeps the previous completed run visible. There is no durable background-job queue or database in this phase.

POST `/drift/run` produces the same result for numerical replay. Warm result caching is bounded to four results; current-plane caching is bounded to four case/depth combinations. Cached results retain the full source, method and query identity. A cold maximum-sized run measured about 0.67 seconds locally; that observation is not a public latency guarantee. The deployed function retains its 30-second bound.

Saved investigations use recipe mode `drift`, a required run A and an optional distinct run B. Modules `drift_run` and `reference_drift_run` retain seeds, methods, all paths and stopping reasons. Reopening recalculates and checks fingerprints. Original P08/P09/P10 method identities are unchanged. CSV exports retain actual timestamps, coordinates, native depth, seed, simulation status and source identity. The ZIP adds full JSON, settings, reports and attribution. Browser saves remain local copies.

## Independent evidence and limits

The separate scientific review passed 45 checks with no skips locally. It decoded original packed provider files, checked analytical motion, manufactured-flow convergence, source interpolation, masks, step boundaries, forcing exhaustion, output cadence, target crossing and denominators. Twelve 24-hour paths across two cases and two depths matched full OceanParcels final coordinates exactly on the checked machine. The test tolerance and environment remain recorded separately from strict saved-record fingerprints.

The largest checked 600-versus-150-second endpoint difference was 0.002059 m. This measures numerical convergence for selected paths, not ocean accuracy. Independent NOAA GDP queries retrieved no overlapping tracks within either exact case and date range; a wider control query returned real records outside the cases. Independent drifter validation is therefore not established. See [independent review](P11_INDEPENDENT_METHOD_REVIEW.md), [reference comparisons](evidence/p11-reference-convergence.json) and [drifter search](evidence/p11-drifter-search.json).

The tracer model excludes sinking, buoyancy, windage, swimming, added diffusion, oil chemistry and invented vertical movement. It does not establish operational rescue, forecast or ship-routing skill. Real unfamiliar-user feedback, physical-device coverage, the known Firefox runtime limitation, Docker execution and institutional/public standards hosting remain separately open.

## Final acceptance

P11.1-P11.5 and feature rows X18-X19 pass their bounded acceptance gates. Real drifter validation remains unavailable, as permitted by P11.5's explicit requirement to seek and report it. No later feature or unfamiliar-user gate is marked complete.

The initial release passed 478 backend checks, 242 local browser checks with one inherited skip, 24 final local Drift checks and 51 public browser checks. Twenty local visual captures passed. Public HTTP verification retained 90 passes and eight failures involving replay/export of four Windows records. All trajectories and individual distances were exact across platforms; only the summary mean differed due to the changed floating-point summation in Python 3.12. See D039, [initial HTTP evidence](evidence/p11-api-public-http.json) and [exact differences](evidence/p11-api-cross-platform-differences.json).

The 0.11.1 correction pins sequential addition as method p11-drift-v2. Old v1 archives remain readable and explicitly report a replay method mismatch. No fuzzy hashes or output rounding are introduced. Final acceptance verifies the new method in both directions, independently of the initial browser passes.

| Check | Recorded outcome | Evidence |
| --- | --- | --- |
| Full backend before summary correction | 478 passed; no skips | [Full report](evidence/p11-backend-full.xml) |
| Final backend scope | 139 passed; 68 API, 45 independent scientific and 26 existing investigation checks; no skips | [Final backend](evidence/p11-v2-backend-focused.xml) |
| Renderer and transport regression | 26 passed | [Renderer report](evidence/p11-renderer-check.json) |
| Full local browser before summary correction | 242 passed; one inherited unsupported WebKit context-loss injection skipped | [Full local browser](evidence/p11-local-browser-full.json) |
| Final local Drift browser checks | 27 passed across Chromium desktop, WebKit desktop and mobile Chromium emulation | [Final local browser](evidence/p11-v2-local-browser.json) |
| Final public Drift and existing investigation workflows | 54 passed across the same three projects | [Public browser](evidence/p11-v2-public-browser.json) |
| Final public HTTP, streams, limits, old archives and exports | 100 checks passed across 114 requests; no retries | [Public API](evidence/p11-v2-public-http.json) |
| Exact final-method replay across platforms | Eight Windows records replayed exactly on Vercel; eight Vercel records replayed exactly on Windows | [Windows to Vercel](evidence/p11-v2-public-http.json), [Vercel to Windows](evidence/p11-v2-public-to-local-replay.json) |
| Public responsive and scientific visual audit | 20 captures; no page errors, document overflow or unexpected alerts; representative paths, arrival comparison and 320-pixel views visually inspected | [Visual audit](evidence/p11-visual-public/checks.json) |
| Maximum record capacity | Two 64-particle, 72-hour, 300-second-step runs fit the existing import limit and retain complete exports; initial-method test remains preserved | [Capacity evidence](evidence/p11-max-record-check.json) |
| Production build and deployment | TypeScript/Vite passed; existing large-chunk advisory remains; deployment READY with verified public release and assets | [Final deployment](evidence/p11-deployment-final.json) |

The public API check also verifies all four original P08 and eight P10 archives without changing their methods. Initial P11 failures, failed test-harness attempts and the first rejected CLI deployment request remain retained. The browser harness stopped depending on an unavailable DevTools response-body read for streaming requests; it now checks the visible result and separately checks the numerical endpoint. The initial unscoped Vercel CLI request returned an authorization error, while an explicit existing-team scoped retry succeeded. No account permissions or project configuration changed, and the initial request's cause is not established.

These checks establish implementation consistency for the supplied cases and tested platforms. They do not establish physical-device coverage, universal availability, unfamiliar-user understanding or observed ocean prediction skill.

## Demonstration and next phase

Choose Drift Lab, inspect the release box, and calculate run A. Press Play paths, scrub time, inspect one particle and its source time, then add a target rectangle or move the release for run B. Compare the declared settings and denominators. Choose a late start with an excessive duration to see the explicit forcing limit. Save, export, then recalculate and reopen the experiment.

Next is P12 Heat & Depth Lab when the user authorizes it. Ultra is recommended for baseline definitions, event detection and thermodynamic diagnostics. P09.5 still needs actual unfamiliar-user task results.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
