# Phase 10: Virtual Expedition

Project date: 22 September 2026. Source dates: January 2024. Release: 0.10.1. P10.1-P10.5 and X15-X17 are complete within the bounded scope below. The release is deployed and verified on Vercel.

## What this phase adds

Virtual Expedition connects three actions in the existing workspace: suggest stations, sample a line, and compare sampling strategies. It supports the checked Bay of Bengal and Arabian Sea cases, temperature or salinity, and exact native depths from 0 to 1000 m. It is an extra investigation tool built on the the event viewer and evidence requirements.

The station budget counts one scalar measurement at one depth and snapshot. The user chooses 3 to 16 stations, minimum spacing from 0 to 150 km, and either prior gradient plus geographic spread or space-filling coverage. Every station exposes its coordinates, prior value, local gradient and selection reason. Changing the draft does not relabel previously calculated output.

The survey takes two endpoints and 2 to 81 positions along their straight longitude/latitude segment. Each position selects the nearest native column at the chosen depth and time. Requested coordinates, actual coordinates and offsets remain inspectable. Numerical ties within 1e-10 km use source order. Missing values stay missing. The chart and export identify all values as simulated model samples.

## Frozen experimental design

The first snapshot supplies all planning information. Candidate locations occupy every sixth native latitude/longitude index plus each final index, filtered only by the prior's finite mask. All remaining finite prior points are reserved for evaluation, disjoint from every possible station. Preview sampling is a display choice and never enters the calculation.

The gradient plan greedily balances normalized prior gradient (weight 0.65) with distance from selected stations (0.35). Physical differences use great-circle kilometres. The coverage strategy and uniform-coverage baseline use greedy farthest-point selection, starting nearest the candidate coordinate centre. It approximates uniform geographic coverage rather than a regular lattice. Five fixed random-order plans use the same candidate pool, spacing and budget. All plans are finalized before later arrays are read. No retry is chosen because it scored better.

Snapshots 2, 4 and 6 supply simulated station measurements and evaluation truth. They are three correlated times in one case, not three independent events. Every sampled strategy reconstructs the field as the fixed prior plus inverse-distance-squared interpolation of station residuals. The power is fixed at 2, without tuning. Persistence retains the prior and uses no new measurements. All strategies are evaluated on the same target-finite reserved points. RMSE, mean absolute error and signed reconstructed-minus-target bias are point-weighted and retain units and denominators.

An incomplete greedy design or a missing target station is a failed trial. Missing evaluation truth is excluded identically across strategies. Failures and successful-run counts remain visible. Summary means describe successful runs only; unequal success sets must not be treated as directly comparable. Selected and uniform plans coincide by design when the coverage objective is chosen.

The future is hidden from selection algorithms, not secret from users who can inspect the same historical fields elsewhere. Repeatedly tuning settings after seeing errors is exploration, not external validation. There is no instrument noise, coastal barrier treatment, physical conservation, calibrated uncertainty, ship routing or demonstrated forecast benefit. These are model reconstruction experiments, not a validated operational OSSE.

## Actual default results

Default: temperature, surface, eight stations, 30 km minimum spacing, gradient objective and seed 26067. Mean pointwise RMSE across the three times is shown below. Random averages pool five plans across those times, with no failures in these runs.

| Case | Selected gradient plan | Space-filling baseline | Five random plans | Unchanged prior |
| --- | --- | --- | --- | --- |
| Bay of Bengal | 0.162475 degrees C | 0.155987 degrees C | 0.168171 degrees C | 0.203111 degrees C |
| Arabian Sea | 0.311115 degrees C | 0.207471 degrees C | 0.234092 degrees C | 0.250760 degrees C |

The gradient plan loses to space filling in both cases. It also loses to persistence in the Arabian case. We retain these results rather than presenting a suggested location as an optimal location. The methods were not changed after examining these scores.

## Save, replay and export

Applied plan settings, a compatible survey and an optional experiment use the existing investigation system. The method identity is added only to expedition recipes, preserving earlier saved records. Reopening recalculates and checks source, recipe, output and document fingerprints. Records retain random seeds and failures. CSV files provide stations, simulated samples and all benchmark trials; ZIP includes these, the complete record, settings, a readable HTML report and source attribution. Browser saves remain local copies, not cloud backups.

## Verification and limitations

Independent numerical tests decode the original packed NetCDF and calculate their own Cartesian great-circle distances and IDW errors. They verify both case benchmarks, surveys at 0/100/1000 m, gradient masks, exact and constant residuals, source-order ties, strict budgets, future-data isolation and retained missing-station failures. See P10_INDEPENDENT_METHOD_REVIEW.md and the evidence files for actual outcomes.

Local browser, public endpoint and visual acceptance results are recorded below. The earlier P09.5 unfamiliar-user pilot is still open. Automated interactions cannot prove that an unfamiliar judge understands the workflow. Existing Firefox runtime, physical-device, public standards hosting and institutional deployment limits remain in PROJECT_STATE.md.

## Demonstration path

Open Expedition from the existing workspace. Inspect a numbered station and its reason. Change the budget and apply the plan. Draw a line or enter its coordinates, choose a source time, and inspect a simulated sample. Run Compare strategies and inspect all trial rows, including an example where the selected design loses. Increase spacing to 150 km with 16 stations and observe the explicit budget failure. Save the applied investigation, download the evidence, then recalculate and reopen it.

Next phase is P11 Drift Lab, the moving particle or pebbles experiment. Ultra is recommended for current interpretation, integration, boundaries and convergence checks. It requires a separate user instruction.

## Replay correction in 0.10.1

The initial public release passed all 87 targeted browser checks, but exact replay of eight Windows-generated expedition records failed on Vercel. The report retains 100 passes and 16 replay/export failures. Inspection found only tiny platform-dependent gradient-norm differences, with a maximum 6.94e-18 across the captured records. Source values, selected stations and benchmark errors were unchanged.

Method `p10-sampling-v2` computes the norm with explicit, separate binary64 multiplications, addition and square root. It keeps full source precision and strict fingerprints rather than rounding outputs or accepting approximate hashes. After this change, 77 focused backend checks passed, including 26 independent source/method checks, and all 24 local Expedition browser checks passed. These include reading an initial v1 record, retaining its downloaded JSON, and receiving an explicit method mismatch on replay. Existing P08/P09 records retain their original identities. Exact replay now passes in both directions between the checked Windows and Vercel environments. This does not establish bitwise portability on every possible future platform.

## Final acceptance evidence

| Check actually executed | Outcome | Evidence |
| --- | --- | --- |
| Full backend suite before the targeted portability correction | 364 passed | [Backend report](evidence/p10-backend-final.xml) |
| Final method, original-source, API, export and investigation regression tests | 77 passed, including 26 independent scientific checks | [Final backend report](evidence/p10-portable-method-tests.xml) |
| Existing renderer and transport checks | 26 passed | [Renderer record](evidence/p10-renderer-check.json) |
| Full local browser suite before the targeted correction | 218 passed; one existing unsupported WebKit context-loss injection skipped | [Full browser report](evidence/p10-local-browser-full.json) |
| Final local Expedition workflows, including archived v1 compatibility | 24 passed | [Local browser report](evidence/p10-v2-local-browser.json) |
| Final local HTTP, capture, replay and exports | 100 checks passed across 103 requests | [Local HTTP report](evidence/p10-v2-local-http.json) |
| Final public HTTP, native samples, failures, guards, original records and exports | 116 checks passed across 119 requests; no failed checks | [Public HTTP report](evidence/p10-public-v2-check.json) |
| Final public Expedition and existing investigation browser workflows | 51 passed across desktop Chromium, Windows WebKit and Chromium mobile emulation | [Public browser report](evidence/p10-public-v2-browser.json) |
| Exact record replay across the two checked platforms | Eight Windows records passed on Vercel, and eight Vercel records passed on Windows | [Windows to Vercel](evidence/p10-public-v2-check.json), [Vercel to Windows](evidence/p10-public-to-local-replay.json) |
| Final public screenshot and layout audit | 18 captures; no page errors, unexpected alerts or document overflow | [Visual checks](evidence/p10-visual-public/checks.json) |
| Production build and deployment | TypeScript/Vite and Vercel Python bundle passed; deployment READY | [Deployment record](evidence/p10-deployment-final.json) |

Representative desktop, survey and 320-pixel benchmark screenshots were also visually inspected. Narrow tables intentionally scroll within their labelled container. These checks establish supported behavior on the tested configurations, not universal accessibility, device performance or first-time-user comprehension. Existing bundle-size and dependency warnings remain recorded.

Other verified corrections include support through the native 1000 m level, deterministic nearest-column ties, keeping draft routes separate from verified samples, matching the map and legend, accurate equal-error explanations, and retaining simulation status and actual sampling timestamps in standalone CSV files. Benchmark exports also identify their measurements as simulated.

The initial failed report [p10-public-check.json](evidence/p10-public-check.json) and cross-platform diagnostic files remain intact. Original v1 Expedition archives remain readable and downloadable; create a fresh v2 plan to obtain a replayable current-method record. No original source values or previous P08/P09 record identities were rewritten.

Public URL: https://depth-atlas-seifuku.vercel.app/. Deployment: `dpl_F3GCPZiayJEEY8UKARqKDLpt6nz9`. Choose **Expedition** in the navigation. The [simple project explanation](PROJECT_EXPLAINED_SIMPLY.md) includes the the event requirement comparison and a short spoken script.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
