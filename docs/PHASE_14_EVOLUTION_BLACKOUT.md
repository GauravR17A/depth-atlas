# Phase 14: feature evolution and observation blackout

P14.1-P14.4 and X25-X26 completed 24 September 2026. Release 0.14.1 is deployed and verified on the existing Vercel project. Implementation started 23 September. The initial 0.14.0 deployment and its failed acceptance remain recorded below.

## User purpose

Follow a defined ocean structure across available historical frames, inspect competing branches, and see how nearby threshold choices affect the result. Separately remove selected observation profiles or groups from the available evidence and inspect exactly what disappears.

## Method commitments

Evolution uses the full native three-dimensional memberships from the existing feature engine. Equal frame-local region IDs do not establish identity. Correspondence is an explicit shared-volume overlap rule, with both directional fractions retained. Splits, merges, competing matches, missing support and time gaps remain inspectable. No continuous water-parcel trajectory is inferred. Initial evolution cases are the two Indian Ocean January 2024 packs; the monthly Pacific cases are not silently treated as 12-hour snapshots.

Blackout exclusions are an additional user selection, separate from provider QC and the existing quantity/time/distance/depth gates. The original source fields and source observations remain intact. Original and excluded coverage, eligible comparisons, residual summaries and affected statements are computed under the same settings. Excluding an already ineligible profile may correctly have no effect on eligible evidence. This is an evidence-dependence experiment, not a model rerun or a forecast-impact test.

Both modes use versioned methods, original source identities and exact investigation replay. New recipe families must preserve prior saved records. Source and replay fingerprints remain exact; independent numerical checks do not relax that requirement.

## Acceptance plan

- Hand-computable split, merge, ambiguous, disappearance, no-overlap, missing-support and skipped-frame fixtures.
- Native-volume weighting and threshold sensitivity, including depth/mask boundaries and explicit resource bounds.
- Remove-none, single profile, group union, remove-all, no-eligible-evidence and invalid-identity exclusion tests.
- Invariance of source arrays, QC and cached baseline results, plus exact original/modified replay and exported tables.
- Frontend-to-API workflows on supported desktop browsers and mobile emulation, error recovery, stale-result handling, keyboard controls and narrow layouts.
- Anonymous public API and browser checks after deployment, including cross-platform exact replay of new and retained earlier records.

## Recovery checkpoint

A local source/data archive was created at `.runtime/p14-start-checkpoint.zip`; its SHA-256 and scope are in `evidence/p14-checkpoint.json`. It excludes ignored environment/credential/runtime files and the large `docs/evidence` tree. This is a local recovery copy, not a Git commit or remote backup.

## Service and saved-record contract

| Operation | Contract |
| --- | --- |
| `POST /api/cases/{case_id}/evolution/run` | `EvolutionQuery`: variable and exact units, inclusive threshold operator, depth interval, first/last source indices, frame step, minimum overlap and sensitivity delta. Returns every accepted frame region, native-column footprints, adjacency links, missing/gap events, eligibility context and sensitivity summaries. |
| `POST /api/cases/{case_id}/blackout/run` | `BlackoutQuery`: unchanged `MatchSettings`, excluded profile IDs, instrument types, platforms and collections. Returns original and retained coverage, eligible sample metrics, exact lost source sample indices and before/after evidence statements. |
| `GET /api/cases/{case_id}/blackout/catalog` | Source-derived profiles, exact selectable groups, model timestamps, available variables and default query. |
| Saved investigations | New `evolution` and `blackout` recipes. Evolution retains the selected node. Both pin model and observation-library hashes and their own methods. Original and modified blackout records are separately reproducible. Earlier methods and source identities remain unchanged. |

Current evolution method: `p14-native-overlap-v2`. Blackout method: `p14-blackout-v1`. The first evolution method and its public replay failure are documented below.

Evolution is bounded to seven source frames, 512 regions per frame, 2,048 region instances per run, 8,192 overlapping pairs per transition and 200,000 footprint indices. The existing native engine also bounds cells and region construction. A zero sensitivity delta explicitly disables additional runs; a positive delta evaluates both shifted thresholds. A between interval shifts both endpoints. Work that exceeds bounds returns an explanation, not a truncated correspondence graph. The graph draws at most 12 connected nodes per frame, labels that presentation limit and leaves all calculated regions selectable.

Blackout accepts at most 128 profiles and 100,000 source samples per bounded library. Selections are sorted and deduplicated; their union removes each profile once. Unknown selections are rejected. Source files are checked even when earlier caches are warm. The baseline includes source-backed alternate eligible timestamps, so exports retain references to all contributing model frames.

Exports provide evolution regions, overlap links, transitions and sensitivity tables, or blackout coverage, profile effects, removed eligible sample identifiers and changed statements. Numerical values are unrounded in CSV/JSON. Null residuals after complete exclusion remain missing, not zero. Depth contacts distinguish the selected depth interval from the original native domain boundary.

## Demonstration

1. Choose Arabian Sea, then Evolution. The default 26 C, 0-300 m condition supplies seven native snapshots, 21 region instances and 26 overlap links. Two split groups and two merge groups occur under the declared rule. Select a graph node and inspect both overlap fractions, geographic extent and available observation context.
2. Compare the nearby threshold rows. Open the advanced controls and choose every second frame to demonstrate explicit 24-hour gaps. No links are inferred across those gaps.
3. Choose Bay of Bengal, then Blackout. The initial checked time has 206 eligible pairs. Select one contributing profile and apply the exclusion: 103 pairs remain. Removing an already ineligible glider changes the selected profile count without reducing the eligible-pair count. Removing all contributing profiles leaves no residual metric, rather than a zero error.
4. Save original evidence and modified evidence separately. Recalculate a saved record and download its evidence ZIP to inspect exact source sample indices, settings, source identities and numerical tables.
5. A Pacific blackout explicitly displays monthly potential temperature and its full averaging interval. It keeps the original observations inspectable but produces no incompatible instantaneous temperature residuals. Pacific monthly evolution remains unavailable.

## Initial numerical and local acceptance

The initial complete backend suite passed 798 tests with zero skips and three existing warnings. The renderer/geographic suite passes 31 tests. These totals include the new API/save/replay cases and relevant earlier phase regressions; focused suites are not added to those totals again.

The evolution oracle reads the original packed HYCOM data and independently calculates segmentation, native geometry and overlap correspondence using separate SciPy, Decimal and set-based calculations. Its 56-test suite covers 42 frame/threshold combinations and 36 transition combinations. The generated fixture rebuilds byte-for-byte. The separate review checks all 26 emitted default Arabian overlap links exactly and both selected-depth boundary labels. See [independent method review](P14_INDEPENDENT_METHOD_REVIEW.md) for what each check does and does not establish. Blackout's 46 tests include small arithmetic fixtures, original eligible sample identities, source invariance and unchanged cached evidence; the combined blackout/evidence run passes 131 tests.

Local HTTP acceptance passes 48 checks across 72 requests with no failures or retries. Eight new investigations match the local methods, capture, replay and export exactly. All 36 retained earlier investigations replay successfully. The archive check compares numerical CSV content, saved settings and source references with the checked record. It establishes transport consistency; its reused CSV helper is not an independent arithmetic oracle.

Recorded reports: `evidence/p14-backend-final.xml`, `evidence/p14-renderer.log`, `evidence/p14-evolution-fixtures-final.xml`, `evidence/p14-evolution-reference-rebuild.json`, `evidence/p14-independent-links.json`, `evidence/p14-local-http.json` and `evidence/p14-local-records.json`.

The subsequent [independent blackout review](P14_BLACKOUT_INDEPENDENT_REVIEW.md) identified two integration errors: original source sample identifiers can exceed a grouped profile's row count, and a monthly source file can list several timestamps rather than one. The browser parser now preserves sparse original identifiers, and blackout exports retain matching multi-timestamp model source files. Both errors were reproduced before correction. Their original reports are `evidence/p14-parser-sparse-initial.log` and `evidence/p14-monthly-source-initial.xml`.

The corrected API and existing saved-investigation suite passes 40 tests, with two existing warnings, in `evidence/p14-source-closure-tests.xml`. All 34 frontend numerical, geographic and parser tests pass in `evidence/p14-renderer-and-parser-final.log`; the three new parser tests are included in that total. Final local HTTP acceptance passes 49 checks across 76 requests, with zero failures or retries. Its nine records include a Pacific monthly blackout with zero incompatible residuals and the original GODAS source checksum. All 36 earlier investigations still replay. Reports are `evidence/p14-local-http-final.json` and `evidence/p14-local-records-final.json`. Scientific result identities and earlier phase reference behavior were not changed.

## Corrections retained in the evidence

The review corrected missing labels for the requested depth interval, while keeping native source-boundary contacts separate. A blackout CSV column now says source or matching exclusions because those counts include the matching gates as well as source QC. Browser review corrected duplicate accessible labels, an empty-graph imaginary node, late responses overwriting newer control edits, and misleading Pacific instantaneous/in-situ labels. Residual-change validation now compares exact metrics even when rounded explanatory sentences happen to match.

Initial reports remain preserved. An early evolution test incorrectly expected a valid 5000 m source depth to be rejected. A blackout corruption test changed only JSON whitespace, which does not alter semantic source identity; it now changes actual source metadata. The first exploratory browser run had five passes and three failures: two duplicate-label failures and a request-wait error in a test. The subsequent 48-case run passed before the last three targeted scenarios were added. No source values, source QC, exact replay checks or numerical tolerances were weakened to obtain a pass.

## Final interface and public acceptance

The initial broad browser regression passed 174 of 180 scenarios. Its six failures were two test assertions repeated across Chromium desktop, WebKit desktop and Chromium mobile: a fuzzy control label also matched a hidden Evolution control, and the generic disabled-state matcher misreported a disabled native option. Exact label selection and native `disabled` property checking corrected those assertions. The report and traces remain in `evidence/p14-local-browser-final.json` and `evidence/p14-browser-broad-initial-traces/`. Despite its filename, that JSON is the initial broad run, not a green final result.

The corrected Evolution, Blackout and structure-search suite passes all 75 checks, with zero failures, skips or flaky cases, in `evidence/p14-local-browser-corrections.json`. It includes the 57 new Phase 14 scenarios across three browser projects. The unchanged earlier navigation/evidence/climate/saved flows retain their successful checks from the broad run.

The local visual harness captured 43 views with zero page/console errors, visible alerts or document overflow. It exercised real saves and downloaded an actual evidence ZIP. Desktop, 320/390 px layouts and 200% root text are included. Nine actual captures were opened and inspected. Small pluralization corrections and a visible graph-scroll hint followed that inspection; the final public run below covers them. See `evidence/p14-visual-local-initial/checks.json` and [visual review](evidence/p14-visual-review.md).

The initial 0.14.0 TypeScript/Vite build passed, retaining the existing large-chunk warning. `evidence/p14-build-release-final.log` identifies `workspace-BTy1L6-a.js`, `scene-DI_dmGZR.js`, `RegionMesh-DuSyiAHQ.js` and `workspace-BPdjCEkt.css`. Production deployment `dpl_5xCUoD13f6e7hSbrksvLNtEoqu8h` is READY on the existing project; its immutable URL is https://depth-atlas-seifuku.vercel.app/. The public alias remains https://depth-atlas-seifuku.vercel.app/. Deployment evidence is `evidence/p14-vercel-deploy.log`.

All 19 anonymous release checks pass in `evidence/p14-public-release.json`: health/version, exactly five cases, public pages, legal information, favicon, required notices and every built JS/CSS asset match the local production build. Five bounded source/config/document/log paths return 404. This is a release-content check, not an exhaustive security audit.

The first public scientific run did not pass: 61 checks passed and six failed across 88 requests, with no retries. Complete comparison isolated six Bay temperature differences and four salinity differences to copied NumPy region volumes and weighted means. Native memberships, frame totals, overlap links/fractions and sensitivity summaries matched exactly in the checked responses. Diagnostic requests, identities and every different leaf are retained in `evidence/p14-v1-cross-runtime-diagnosis.json`. A concurrent replay also reached the 30-second function limit. The first public browser run passed 81 of 84 scenarios; three WebKit evolution response waits timed out. Initial reports and traces remain in `evidence/p14-public-http.json`, `evidence/p14-public-browser.json` and `evidence/p14-public-browser-v1-traces/`.

The correction uses P14-only ordered `math.fsum` for region volumes, means and weighted means, under `p14-native-overlap-v2`. Source fields, native memberships, geometry, P07 methods and the independent oracle remain unchanged. An eight-result per-instance cache retains completed calculations, validates source integrity before every lookup, shares duplicate concurrent work and returns isolated copies. Eviction, failures and warmed-source corruption are tested. This corrects repeated work in the current P14 paths; it does not complete P15 scaling benchmarks. D049 records the choice.

All 64 focused v2 numerical/source/cache checks pass in `evidence/p14-evolution-v2-cache.xml`. The independent link checker again passes 28 checks in `evidence/p14-v2-independent-links.json`. All 34 frontend numerical/geographic/parser checks pass in `evidence/p14-v2-renderer-parser.log`. The corrected local HTTP run passes 49 checks/76 requests with no retries, including nine new records and 36 older investigations (`evidence/p14-v2-local-http.json`, `evidence/p14-v2-local-records.json`). All 30 v2 evolution and legacy-archive browser scenarios pass across the three supported projects in `evidence/p14-v2-local-browser.json`. V1 files remain readable and their original JSON can be downloaded unchanged, while replay against v2 explicitly reports a different method.

### Final 0.14.1 acceptance

All **807 backend tests** pass with zero failures or skips and three existing warnings in `evidence/p14-v2-backend-final.xml` and its log. The focused 64 evolution/source/cache checks are included in that total. Final TypeScript/Vite builds successfully with the retained bundle-size warning (`evidence/p14-v2-build-final.log`). Final assets include `workspace-fwVeVJXC.js`, `scene-CthBvSyi.js`, `RegionMesh-O_93-nOP.js` and `workspace-BPdjCEkt.css`.

Production deployment `dpl_B8ZWmGAqL3kunpzdwareaX41ZKDJ` is READY at [the existing public app](https://depth-atlas-seifuku.vercel.app/), with [this immutable release URL](https://depth-atlas-seifuku.vercel.app/). Its log is `evidence/p14-v2-vercel-deploy.log`. All **19 anonymous static-release checks** pass in `evidence/p14-v2-public-release.json`, including exact served assets, five cases and legal/source notices.

Final public HTTP acceptance passes **67 checks across 94 requests** with zero failures or retries in `evidence/p14-v2-public-http.json`. Nine Windows-generated investigations and their numerical exports reproduce exactly on Vercel, and all 36 earlier investigations replay. The separate reverse run passes **19 checks/19 requests**, reproducing all nine public records and exports on Windows (`evidence/p14-v2-public-to-local-replay.json`). The public and local record files are `p14-v2-public-records.json` and `p14-v2-local-records.json`. Original source fingerprints and full numerical precision remain intact.

The final public browser suite passes **87 scenarios**, with zero failures, skips or flaky cases, across Chromium desktop, WebKit desktop and Chromium mobile emulation (`evidence/p14-v2-public-browser.json`). It ran concurrently with public HTTP acceptance, including the previously timed-out evolution paths. This verifies the tested workload; it is not a wider load or performance benchmark.

The final public visual harness captures **43 views**, with zero page/console errors, visible alerts or document overflow. Original and modified saves and a 168,638-byte evidence ZIP work. The integrating agent opened and inspected nine final public screenshots, including the branching graph, requested-depth contacts, exact lost source IDs, empty residuals, 320 px screens, enlarged text and monthly quantity limitations. The scroll hint and singular-count copy corrections are visible. See `evidence/p14-visual-public-final/checks.json` and [the actual inspection record](evidence/p14-visual-review.md).

No blocking defect remains in the checked P14 paths. These checks do not establish water-parcel identity, operational forecast impact or full ocean validation. The existing P09.5 unfamiliar-user pilot remains open. P15 requires a separate user instruction and is recommended on Ultra.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
