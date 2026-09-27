# Phase 8: saved investigations and numerical replay

Completed: 22 September 2026. Deployed release: 0.8.1. P08.1-P08.5 and X06/X10/X11 are complete within the supported case and investigation modes.

## What an investigation contains

An investigation saves one applied analysis from the ocean viewer, a checked observation profile, a model comparison or a structure query. It contains its recipe, case/region identity, source fingerprints, scientific method versions, software versions, calculated modules, source references and limitations. Comparison records retain an optional reference comparison with its own time, variable, profile and matching policy. Feature records retain the selected region, drawn section, selected native section sample and display choices.

Ocean records retain the selected native column and depth, variable/time, view, colour settings, depth window, cutaway, quality choice and exaggeration. Replay restores those settings; camera orbit and running animations reset. A saved investigation is one analysis, not a snapshot of every inactive tool. Unsubmitted form drafts and temporary observation imports are excluded. The interface disables capture while relevant requests or unapplied query changes are pending.

All numerical work still uses the existing P02/P04/P05/P07 methods. P08 does not add interpolation, change source arrays, relax quality gates or certify model skill. Native current profiles retain both horizontal components and their joint-mask speed. Missing values remain null in JSON and empty numeric CSV cells. Model and observation timestamps remain separate.

## Storage and sharing

The public app remains on Vercel. There is no account, server database or saved file in the function filesystem. Saving writes an explicit record to IndexedDB in the current browser, limited to 25 records and 32 MB, with an 8 MB individual-file limit. Save failure leaves the newly calculated investigation available for download and does not claim a successful local save. Local copies can be removed independently of downloaded files and shared links.

Browser storage can be cleared or evicted, so the UI recommends a portable JSON backup. This follows the documented [IndexedDB storage model](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB) and [browser storage/eviction rules](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria). Vercel recommends external persistent storage for function writes; this implementation deliberately requires no paid storage service. See [Vercel file guidance](https://vercel.com/kb/guide/how-can-i-use-files-in-serverless-functions).

A replay link stores a bounded recipe and expected source/result identities in a URL fragment, encoded as UTF-8 base64url, up to 16,000 encoded characters. It is self-contained settings, not a short server record ID. Opening it prepares the recipe. Recalculate and reopen sends it to the API for verification. Anyone with the link can read its title and settings; the UI and policies say so. Sharing does not transmit imported files. Long-term link replay still depends on the required sources and method implementations remaining available.

## Replay and fingerprints

`POST /api/investigations/capture` recalculates a typed, bounded recipe against the current checked sources. Capture can require the fingerprint of the source visible when the user clicked Save. `POST /api/investigations/replay` checks the recipe fingerprint, method identity and source identity before calculating again. It compares the complete module results with the stored expected result fingerprint. A changed source, unsupported method, missing file or numerical mismatch stops reopening; it does not substitute another dataset or present a saved result as a successful recalculation.

The fingerprint format is `tagged-json-f64-sha256-v1`. Values carry explicit null, boolean, number, string, array and object tags. Numbers use their binary64 bytes in big-endian hexadecimal, with both zero signs normalized. Object keys sort by Unicode code point; arrays retain order. Tagged JSON uses ASCII escapes and compact separators before SHA-256. This avoids treating Python's `1.0` and JavaScript's `1` as different numerical values after a JSON round trip. Nonfinite values, unsafe integers and unsupported types are rejected. Browser file verification also checks the complete document and every module fingerprint.

Hashes establish consistency, not author identity or scientific truth. No digital signature or private signing key is claimed. Scientific result fingerprints exclude capture dates and the current app patch version. Software versions remain in the document, while explicit source/method identities decide compatibility. A UI-only patch can replay identical calculations; changed scientific methods require an explicit version and cannot silently migrate old records.

Each result module has `module`, `method_version`, `parameters`, `random_seed`, `output` and `output_sha256`. Current deterministic methods use a null seed. Later labs can add versioned typed recipes and modules using this envelope; unsupported modules are not accepted or executed in this release.

## Exports

Investigation JSON preserves the complete portable record. A readable, script-free HTML report explains the analysis and displays summaries, methods, sources and limitations. Its detailed recipe and fingerprints are expandable. Browser printing can produce a PDF; no generated PDF layout is claimed.

Numerical CSV exports include original values, units, source times, positions and missingness. Comparison CSV contains eligible and excluded source rows, depth-bracket values/weights, residuals, QC and exclusion reasons. A reference comparison has its own CSV. Section CSV records requested stations, actual native columns, offsets, depths, values and region membership. Region CSV labels volume as estimated and records full membership fingerprints.

The evidence ZIP contains `investigation.json`, `settings.json`, `report.html`, the applicable CSV files, `SOURCES.json`, source credits and a README. Exports are recalculated and checked before download. Only supported public-source subsets and outputs are included, with source terms, original fingerprints and native-download instructions. Uploaded/private observations and complete global datasets are not bundled. The report escapes text; CSV protects formula-like text without altering negative numerical values.

## Verification and fixes

The first P08 backend run passed 24 tests and exposed an incorrect fixture key in the new test. The corrected run passed all 25, including two separate fresh Python processes. The full suite then passed 306 tests and the existing renderer suite passed 24. Initial reports remain in `evidence/p08-initial-api.xml` and the subsequent records.

The first eight browser checks passed six and failed two text-comparison assertions: rendered `innerText` was compared with raw DOM text. Restored numeric selections were correct. The assertions now consistently use rendered text; initial traces are retained. The broader browser run also found a real WebKit focus-return defect in the new dialog. A fallback to the persistent Saved button addresses mouse clicks that do not focus the triggering button; all 24 P08 browser checks passed on the final build across Chromium desktop, WebKit and Chromium mobile emulation.

All 30 local visual workflow checks passed at desktop, WebKit, 390 px, 320 px and 200% root text. Saved records, capture forms and the exported report were also inspected as actual screenshots. The enlarged-text run recorded 28 px dialog text, double its normal 14 px. Four complete investigation records replayed in a second fresh Python process. All 19 local HTTP capture/replay/export and mismatch checks passed.

The 0.8.0 public browser suite passed 172 checks initially, failed four during resource loading and skipped the intentionally unsupported WebKit context-loss injection. Every new P08 browser test passed in that full run. All four failures passed unchanged rechecks. Complete traces are retained in `evidence/p08-public-browser-failures/`; `p08-public-failure-review.json` records incomplete field/manifest transfers and a navigation timeout. The exact network/browser/CDN/backend origin is not established. An earlier npm.ps1 launch consumed the project arguments and was interrupted; the corrected direct Playwright CLI ran the intended 177 checks. No test threshold was relaxed to obtain a pass.

All 30 separate public visual checks passed for 0.8.0. The subsequent 19-check archive audit found a real deployment defect: all four ZIPs omitted `source-credits.txt` because the backend bundle did not include the public attribution file. Numerical captures, replay and non-ZIP exports passed. Release 0.8.1 explicitly includes that file in the Vercel function and refuses to create a ZIP if required credits are missing. The regression test covers that failure path. All 307 backend tests and all 26 focused P08 backend tests pass on this revision.

All 19 public HTTP checks now pass against 0.8.1, using the earlier 0.8.0 records. Complete recalculated modules match the separately captured local records, and all four ZIPs include the required attribution, settings, report and numerical files. This also verifies that a packaging patch can replay unchanged scientific results without silently changing the method. Initial failing archive results remain in `evidence/p08-public-initial-replay.json`; final results are in `evidence/p08-public-replay.json`.

All 27 final public P08 browser checks pass on 0.8.1 across Chromium desktop, Windows WebKit and Chromium mobile emulation. The added deletion check confirms that removing a local copy persists after reload while its downloaded backup remains usable. All 49 existing public HTTP/source checks pass over 50 requests, including the complete native NetCDF checksum. Reports are `evidence/p08-public-081-browser.json` and `evidence/p08-public-existing-http.json`. The full 177-check regression and 30-check screenshot audit were run on 0.8.0; 0.8.1 changes attribution packaging, explicit ZIP failure and release versions, with focused verification of those paths. No scientific method or source array changed.

Existing Firefox/physical-device/user-study, Docker, public THREDDS and intermittent public-network limitations remain separate from this phase's verification. Hash matching establishes reproducibility against these source/method versions, not independent validation of the ocean model. P09 is unstarted and is recommended on Extra High.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
