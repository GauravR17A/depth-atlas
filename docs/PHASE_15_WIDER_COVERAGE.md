# Phase 15: wider coverage and scale

Status: P15.1-P15.5 and X27-X29 complete, 26 September 2026. Release 0.15.2 is deployed and verified on the existing Vercel project. The user chose Extra High; acceptance gates were unchanged. P16 has not started.

## Scope and source contracts

The Regions workspace adds bounded requests over two pinned sources. It is part of the existing app and shares its renderer, native values, provenance and explicit-error conventions. Earlier scientific labs remain attached to their five verified case sources.

- NOAA GODAS monthly potential temperature and source salinity, September and October 2022. Native 28 x 418 x 360 grids cover 5-459 m and approximately 74.5 S to 64.499 N. Original 0-360 longitudes and irregular latitude/depth levels are retained. Potential temperature converts kelvin to Celsius in Float64. Salinity converts source kg/kg to g/kg, without claiming practical salinity or TEOS-10 Absolute Salinity.
- GOBAI-O2 v2.2, NCEI archive release 4.4, monthly oxygen and the producer's separate total uncertainty for September and October 2022. Native 58 x 145 x 360 fields retain pressure 2.5-1975 dbar and cyclic longitude storage. Source timestamps are the middle of each month; calendar averaging intervals remain explicit. Pressure is never relabelled as metres. Product values, including negative estimates and independent missing uncertainty masks, are preserved.
- There is no arbitrary-region observation library. Existing Argo, glider, CTD and BGC support remains in the curated cases.

Sources: [NOAA GODAS](https://psl.noaa.gov/data/gridded/data.godas.html), [GOBAI archive](https://doi.org/10.25921/z72m-yz67), [producer method paper](https://doi.org/10.5194/essd-15-4481-2023). The paper describes v2.1 methods; this app pins v2.2 values separately. The GOBAI licence supplied by the archive is CC0 1.0 and is included. No model is trained here.

## Method and resources

Method `p15-native-subset-v1` selects original source indices in an eastward-unwrapped bounded region. Finite ascending rectilinear latitude/vertical axes and one cyclic eastward longitude axis are required. Curvilinear grids, unsupported dates/variables, polar coverage, empty coordinate selections and oversized requests are explicit errors. Missing land/ice/source support is not filled, and no separate ice classification is invented.

Requests allow at most 90 longitude degrees, 40 latitude degrees and 120,000 native values. Query bodies are limited to 8 KB; imported/replayed envelopes to 4.5 MB and canonical numerical payloads to 4 MB. At most four regional operations execute per server instance; excess requests return 429. These are per-instance bounds, not distributed account quotas.

A 12 x 12 x 8 preview precedes a display using at most 40 x 40 horizontal points and all selected native vertical levels. Profiles, CSV and regional packs use native values. Server caches allow 40 MiB / three native arrays and 12 MiB / twelve responses. Source checksums are rechecked before cache hits. Browser display cache is 8 MiB / six fields. Display settings do not change the scientific export.

Cancellation stops the browser from waiting and ignores late results. A bounded server calculation already started can finish. Adaptive/basic display is separate from native precision. Regional requests do not fetch user-provided URLs.

## Portable evidence

A pack carries exact canonical JSON, source/packed-file hashes, native coordinate indices, method, query and values, with provider uncertainty where applicable. Local SHA-256 checks detect corruption; only online replay compares the pack with the currently pinned original sources. No signature or source authenticity is inferred from a self-contained checksum.

One explicit regional pack can be saved on the device, replaced or deleted. JSON import works without network calls. A separate self-contained HTML viewer opens with no app server or connection. This is not a promise that the entire website reloads offline. Privacy and Terms describe actual transmission and storage; operator identity/contact details remain blank as requested.

## Initial verification and corrections

Initial full backend: 853 passed, three failures. One regression changed the missing-source HTTP status of older investigations and has been corrected without weakening the earlier contract. Adapter-count expectations were updated to the explicit four supported adapters. A unit-label encoding defect was fixed. Initial browser run: 36 passed across Chromium desktop, WebKit desktop and Chromium mobile emulation. Subsequent review corrected saved-pack replay cancellation, changed-selection comparison, single-level section availability and offline cell selection alignment. Final acceptance evidence is recorded below.

## Demonstration

Open Regions, inspect source availability, then Open selected region. Select a native column. Change to Source salinity and October, then try the date-line and Southern Indian presets. Choose GOBAI oxygen to inspect pressure and separately reported uncertainty. Save a pack, open it locally and verify replay online. Download the offline viewer and open it with the network disabled. Earlier laboratories remain available through the same navigation.

## Limits and next work

This is historical, source-specific wider coverage, not live global analysis or independent ocean validation. Browser emulation does not establish physical-device support or actual unfamiliar-user comprehension; P09.5 remains open. P16 learning mode and grounded explanations is next, on a separate instruction, with Extra High recommended.


## Source acquisition and reproducibility

`science.acquire_wider` retrieves GODAS in four-depth slabs because an initial larger provider response was truncated. Metadata pins units and native coordinates. `science.acquire_gobai` reads bounded, explicitly acknowledged HTTP byte ranges from the original CDF-2 file, checks source ETag/Last-Modified identity during acquisition and retains the original range hashes. The 11 GB original is not downloaded in full and no full-file hash is claimed. Both commands are maintainers' preparation tools, not public arbitrary-fetch endpoints.

All eight packed arrays were compared value-for-value with their original acquired slabs/ranges: 28,964,160 values including NaN equality and endian conversion. GODAS raw hashes identify little-endian prepared bytes; GOBAI raw hashes identify the original big-endian source ranges. The initial performance verifier incorrectly treated these two hash definitions as identical. Its failed log remains, and the corrected verifier independently checks original-range and packed-file identities. A cached source rebuild preserves all ten prepared metadata/data hashes plus the original licence file exactly; see `evidence/p15-source-rebuild.json` for the actual file list.

## Measured resources

Measurements are small reproducible samples on this Windows computer, not capacity forecasts. The source preparation audit and fresh-process/cache benchmark are separate from public network measurements. Working-set memory is measured using the Windows process API; an initial measurement returned zero because its handle signature was missing, so those zero readings are invalid and superseded by `p15-local-performance-final.json`. OS disk cache was not flushed. A fresh store is used for the first preview; subsequent display/native stages reuse the source array.

The corrected local working-set samples are about 94-100 MiB, including the Python process. Source array and serialized response caches remain inside their 40/12 MiB ceilings. The browser cache has its independent 8 MiB/six-field bound. Four simultaneous HTTP clients completed both measured rounds, with deterministic saturation/recovery checked separately. Elapsed calculation durations are recorded; CPU utilization was not sampled, and there is no claim of a deployment-wide memory ceiling or sustained throughput guarantee.

A Chromium CDP regional-request throttle of 400 ms latency and 50,000 bytes/second download/upload produced a preview response in about 0.94 s and completion in about 3.43 s locally, with Save-Data selecting Basic view. The app shell had already loaded, so this is not an initial-page-load benchmark. The final hosted sample measured a 0.92 s preview response and 3.44 s completion under the same regional-request throttle. Cancellation ignores late responses and preserves completed data; the server can finish already-started bounded work.

## React and interaction review

The Regions workspace is imported only when first opened. Shared scalar rendering does not require a different ocean calculation. Aborted requests and generation counters protect against late responses; source identities distinguish cached fields. Effects dispose renderers/listeners and stop background work when the workspace is hidden. Source/variable/month/quality controls have accessible labels, status/error regions identify progress and failure, and the inspected 320 px view has no document overflow. Display-only decimation keeps offline native packs below renderer axis limits without changing profiles or exports. These technical checks do not close the real-user pilot.


## Final pressure-axis correction

Manual inspection of the first public screenshots found a clipped leading digit on a long pressure-axis tick label. Automated document-overflow checks had passed because this was text inside a canvas. Release 0.15.2 reserves a wider left margin for pressure sections and uses the same plotting geometry when interpreting clicks. A browser regression measures actual drawn text and independently checks that a click at the middle of the known longitude range requests 70 E. It passes in Chromium desktop, WebKit desktop and Chromium mobile. Existing metre-based plots keep their original geometry. No numerical source, method, export or cache setting changed in this visual patch.

The requested stop/restart command for the previous local server was blocked by automatic policy review. A new task-owned server was started non-destructively on port 8016 instead. The previous port 8015 is not the final acceptance server. No permission workaround or unrelated process termination was used.


### Local transfer and cache samples

| Source / resolution | First call, seconds | Cached call, seconds | JSON bytes | Gzip bytes |
| --- | ---: | ---: | ---: | ---: |
| godas-2022 / preview | 0.0746 | 0.0076 | 26078 | 7986 |
| godas-2022 / display | 0.0163 | 0.0113 | 430659 | 80422 |
| godas-2022 / native | 0.0171 | 0.0122 | 483972 | 89557 |
| gobai-v2.2 / preview | 0.0467 | 0.0067 | 26110 | 11006 |
| gobai-v2.2 / display | 0.0127 | 0.0096 | 326754 | 112441 |
| gobai-v2.2 / native | 0.0128 | 0.0098 | 326753 | 112441 |

Gzip sizes above are measured compression of the JSON bytes, not a claim that every hosting response uses gzip. First-call timing is a fresh store only for preview; later resolutions share the loaded native array. Browser cache reuse is separately checked by counting zero repeated subset requests.


## Final acceptance record

- **Backend:** `.venv/Scripts/python.exe -m pytest tests -q --junitxml=docs/evidence/p15-v1-backend-final.xml` passed **857 tests**, zero failures/skips and three existing warnings. This includes 50 P15 tests. The final 0.15.2 patch changes pressure-axis drawing/click geometry and release identity only; scientific Python code is unchanged from that run.
- **Frontend/build:** `npm --prefix web run test:science` passes **39** checks in `evidence/p15-v2-frontend-science.log`. `npm --prefix web run build` passes TypeScript/Vite in `p15-v2-build-final.log`. The existing large-chunk warning remains.
- **Original sources:** `science.verify_p15_performance --source-audit` checks eight arrays, **28,964,160 original values**, all exact including missing values. The corrected memory/size/cache report is `evidence/p15-local-performance-final.json`. `science.acquire_wider` and `science.acquire_gobai` preserve all eleven prepared-file hashes on rebuild, in `evidence/p15-source-rebuild.json`.
- **Public transport:** `.venv/Scripts/python.exe -m science.verify_p15_public --base-url https://depth-atlas-seifuku.vercel.app --output docs/evidence/p15-v2-public-http.json --records-output docs/evidence/p15-v2-public-records.json --replay-records docs/evidence/p15-local-records.json` passes **23 checks across 79 requests**, without retries. Seven regional records match local native/display/profile/CSV calculations and exact pack identities. Reverse replay against local port 8016 passes **nine checks across sixteen requests** in `p15-v2-public-to-local-replay.json`.
- **Earlier phases:** retained replay of **45 earlier investigations**, with all nine P14 numerical export bundles, passes **55 checks/requests** on Vercel in `p15-v1-public-prior-replay.json`. That run precedes the pressure-axis-only UI patch. The same 55 checks pass locally. No older method or scientific fingerprint changed.
- **Browser regression:** the broader 0.15.1 public run passes **113 scenarios**, with one pre-existing WebKit graphics-context-loss skip and zero failures, in `p15-v1-public-browser.json`. After the pressure fix, direct Node Playwright runs over the wider suite and independent 3D/Basic coordinate test pass **45 scenarios**, zero failures/skips/flaky results, across Chromium desktop, WebKit desktop and Chromium mobile emulation. Final report: `evidence/p15-v2-public-browser.json`. The three focused local pressure-axis checks also pass.
- **Visual/offline:** `node web/benchmarks/p15-visual.mjs https://depth-atlas-seifuku.vercel.app docs/evidence/p15-v2-visual-public` captures **20 views**. Eighteen layout snapshots have no overflow/alerts; there are no recorded page/console errors. A 645,943-byte oxygen offline viewer opens with networking disabled and makes zero HTTP requests. Nine final screenshots were opened and inspected, including the corrected full pressure label at 320 px. See `evidence/p15-visual-review.md`.
- **Concurrency/performance:** `node web/benchmarks/p15-evaluators.mjs` passes four isolated simultaneous Chromium workflows through source selection, regional load, profile, device save and exact online replay. Region-load samples are **1.37-2.90 seconds**; sampled JS heap is about **9.9-24.4 MiB**. This is one computer and a small sample, not a 100-user guarantee. `science.verify_p15_performance` also passes two four-client HTTP rounds, **eight requests**, in `p15-v2-public-performance.json`, with sampled request durations **0.51-1.27 seconds**. Saturation, body limits, cache bounds, corrupt/missing files, cancellation and recovery have separate regression checks.
- **Deployment:** `npx --yes vercel@59.23.2 deploy --prod --yes --scope kai-vexen-studios` publishes to the existing project. Final deployment `dpl_4eG8oBzSgXxaL8XceTA767SUEmnn` is READY at `https://depth-atlas-seifuku.vercel.app/`. The normal public URL serves the same release. `science.verify_p15_release --url https://depth-atlas-seifuku.vercel.app --report docs/evidence/p15-v2-public-release.json --deployment-id dpl_4eG8oBzSgXxaL8XceTA767SUEmnn` passes **21 anonymous checks**, including API identity, all eight built JS/CSS assets, legal pages/favicon/notices and five bounded private-path 404 checks. This is not an exhaustive security audit.

All initial reports and failures are retained. The first full backend run was 853/856, not initially green. The initial source-hash and Windows memory verifier assumptions were corrected, and the canvas label defect found by actual visual inspection was fixed. The local focused pressure browser command reported a shell exit of 1 despite its JSON/list reporters confirming three passes, zero errors/failures/skips; final public runs independently pass those scenarios. No acceptance tolerance, original numerical field or older investigation fingerprint was weakened.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
