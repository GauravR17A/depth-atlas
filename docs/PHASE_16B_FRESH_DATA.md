# P16B: fresh model input and portable setup

27 September 2026. Release 0.16.7 is accepted and deployed on the existing Vercel project.

## What changed

A newly acquired HYCOM case covers 28-30 March 2024 in a bounded Bay of Bengal area. Five instantaneous snapshots retain all 40 native output depths and the 26 by 13 horizontal grid. Temperature, practical salinity and earth-relative currents pass through the existing adapter, preparation, API and scientific renderer. This is fresh acquisition of different historical files from the existing provider, not a new model family or live feed.

The real chlorophyll example SR1902594_034.nc now has a model case that includes its location and date. Import it manually to see both together. The model has no chlorophyll quantity. Imported numerical comparison and persistence remain P16C. No glider or CTD temporal/geographic overlap is claimed.

## Reproduction

```powershell
.venv/Scripts/python.exe -m science.acquire_case --case bay-bengal-2024-03
.venv/Scripts/python.exe -m science.prepare_case --case bay-bengal-2024-03
.venv/Scripts/python.exe -m science.prepare_standards --case bay-bengal-2024-03
.venv/Scripts/python.exe -m science.verify_p16b --reference
.venv/Scripts/python.exe -m pytest tests/test_fresh_model.py -q
.venv/Scripts/python.exe -m science.verify_p16b --url http://127.0.0.1:8026 --report docs/evidence/p16b-local-http.json
```

Source: https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0
Provider description: https://www.hycom.org/dataserver/gofs-3pt1/analysis
The acquisition journal in casepacks/bay-bengal-2024-03/source-metadata.json records request indices, exact timestamps, original variable metadata and SHA-256 fingerprints. Reconstructed NetCDF subsets retain original packed source values and float32 packing attributes. No spatial interpolation or missing-value filling is applied. A repeat acquisition verifies cached fingerprints instead of silently replacing them.

The prepared pack is 726,586 bytes. The native CF exchange is 1,595,051 bytes. These are file sizes, not runtime memory or total function-bundle size. All original case and observation-library files remain unchanged.

## Extension work

| Extension | Actual maintained changes | Boundary |
| --- | --- | --- |
| Another compatible HYCOM case | One recipe declares bounds, exact dates, title, adapter and observation policy | Source coordinates and physical definitions must pass the registered adapter |
| Preparation and acquisition | Removed the fixed seven-frame assumption for recipes with explicit dates; optional observations produce no invented provenance | Original recipes retain their behavior |
| API registration | CaseStore includes maintained recipe IDs after the existing five IDs | User-provided paths never become registry keys |
| New case in browser | Existing case selector, scientific renderer, palettes and native-value inspection are reused | Tools with separate source requirements still need explicit availability |
| CF export and THREDDS | Date-aware export title/history; launcher registers integrity-checked exchanges | Not arbitrary NetCDF support or a public service |
| New variable/product/sensor | Existing trusted adapter, product and instrument contracts remain; CF exchange reimports every new native field; P16A proves chlorophyll observations | Public variable IDs, units and UI metadata remain maintained allowlists. No zero-code arbitrary sensor/variable claim |

Heat & Depth requires its separately acquired surface time series. Expedition and Evolution also retain their explicit seven-frame January method gates. The catalogue now derives unavailable tools from the scientific registries and the case metadata, so the March case offers a supported January case before opening these tools. No method gate was loosened. Tool selection still contains those two checked fallback cases. This is recorded coupling, not universal automatic discovery. These availability rules also apply when changing cases while a tool is open. The wider connected workflow remains P16D.

## Standards and CF

The existing January THREDDS service repeated 143 source/protocol checks. A fresh March service on loopback port 8097 passed 123 checks covering source-to-exchange values and masks, WMS 1.3.0 images and geolocated readings, WCS 1.0.0 coverages, and strided DAP2 requests. The differing count follows five versus seven source snapshots.

```powershell
.venv/Scripts/python.exe -m deploy.run_standards --base .runtime/p06/p16b-march-server --port 8097
.venv/Scripts/python.exe -m science.verify_p06_standards --base http://127.0.0.1:8097/thredds --prefix p16b-march-accepted --case bay-bengal-2024-03
```

Use the pinned runtime installer in deploy/run_standards.py when Java/Tomcat/TDS are not already installed. Port and runtime base are configurable; only loopback is bound. Native downloads and REST are public on Vercel after deployment. Persistent public THREDDS remains unconfigured.

The local scoped CF-1.10 checker and adversarial metadata tests pass. An independent IOOS compliance-checker 6.1.0 installation was attempted in an isolated environment. Its cf-units wheel build failed because UDUNITS2_XML_PATH/native UDUNITS support is absent on this Windows host. No full independent CF certification is claimed. Keep the installation failure log. THREDDS also logs a Windows EPSG-cache path error; the tested CRS:84/EPSG:4326 paths pass, but other projections are not verified.

Initial March protocol checking retained a fixed January image width/height in the verifier. This made the two image-shape assertions fail. Requests now use the new native horizontal dimensions. All original value and coordinate tolerances are unchanged; both the initial failure and final report remain.

## Scientific and interaction evidence

- p16b-science.log: 117 passing tests, including complete native-array source hashes and CF reimport, retained replay and supported import boundaries.
- tests/fixtures/p16b-source-reference.json: 25 independently decoded arrays, five variables over five timestamps, with original file hashes and selected reference values.
- p16b-local-http.json: 35 checks over 33 serial requests, exact model replay/export and native download checksum. These timings are measurements, not a concurrency capacity claim.
- p16b-browser.json: 51 passing desktop Chromium, mobile emulation and Windows WebKit checks. Six are repeated pure marker-location fixtures. Browser checks cover the fresh case, imported chlorophyll, tool availability, old saved investigations and standards links.
- p16b-protocol-verification.json and p16b-march-accepted-protocol-verification.json: retained January and March protocol/source checks.

Visual review, clean installation and public checks are recorded at final acceptance. Docker is not present on this machine; its recipe is not claimed executed. No actual INCOIS installation, independent oceanographer review or physical-device testing is claimed.

## Demo path

Skip the introductory tutorial, choose Bay of Bengal 28-30 March 2024, then choose 29 March 00:00 UTC. Inspect the native 100 m temperature value and switch to a depth slice. Open Instruments, Import observations, Formats and genuine example files, Preview SR1902594_034.nc, then Add profiles. Inspect the chlorophyll curve beside the correctly dated model. Explain that this is real observation/model co-display, with no model chlorophyll comparison. Use the data provides the native NetCDF and source identity.

## Remaining coverage

| Area | Current March case support |
| --- | --- |
| Explorer, slices, isosurfaces, currents, native picking and source metadata | Existing engine with fresh source fields; tested rendering and native values |
| Instrument co-display | March BGC import overlaps geographically and temporally; no new frozen-library profiles |
| Model save/export/replay | Exact verified model investigation |
| Imported comparison/save/replay | P16C |
| Surface heatwave series | Not supplied for March; choose a checked January case |
| Glider/CTD matched evidence | Still needs a suitable source-model pair |
| WMS/WCS/DAP2 | Tested local January and March services; no persistent public endpoint |
| Expedition / Evolution | March is outside their checked case sets; choose January before opening |
| Docker / INCOIS installation | Not executed / not supplied |

Next phase is P16C only after instruction, with Astra Ultra recommended.


## Additional boundary found during acceptance

The initial 0.16.6 candidate passed core viewer/import checks but exposed Expedition and Evolution for March because the old menu inferred all lab availability from the presence of currents. Their backends correctly refused this unverified case. The broader lab check caught both errors on desktop and mobile. Release 0.16.7 adds catalogue availability derived from the actual method registries. Users are offered a checked January case before either tool opens. Switching to March while already in an unsupported tool returns to Explorer with an explanation. The original method restrictions and source fingerprints remain unchanged.

Two older tests pinned exactly five cases and only the January protocol case. Those expectations were updated to six cases and the two verified Bay protocol routes. Their original failed runs remain. The final regression passes all 106 cases. No numerical tolerance was relaxed.

The clean source baseline also required `.gitattributes` to preserve scientific JSON bytes. All 304 staged case-pack files were compared byte-for-byte; all 260 pre-existing scientific pack files are identical to the P16A checkpoint. Large Functions is configured after its real fallback path passed. These fixes address packaging and availability; they are not the deferred P17 security audit.


## Final acceptance

The final code baseline is local commit 3cd0f399bdce4f1bf195b7a50763753e7913929f. A fresh source archive was extracted into .runtime/p16b-portable-final, installed using requirements.txt and npm ci, built and served on port 8028. Its 35 HTTP checks and 24 Chromium desktop/mobile and WebKit checks passed. Dependency consistency passed. This is a separate installation environment on the same host, not another operating system or institution.

Production release 0.16.7 is READY as dpl_Ceg6EQpB7TpR3PpzSsWUaMBmZuqq at https://depth-atlas-seifuku.vercel.app/. Public results: 24 release/asset checks, 35 scientific HTTP checks, 36 desktop/mobile browser checks and six visual captures without horizontal overflow/page errors. The final public serial HTTP sample had a 0.4885-second median and a 3.0495-second maximum over 33 requests, including a native download. Final isolated local requests had a 0.0279-second median and a 0.1083-second maximum. These include client/network conditions and do not establish concurrent scalability or guarantees.

Before the final availability change, 117 science/adapter/import/replay tests, 106 core regression checks and 60 client science tests passed. The final capability patch passed 88 affected backend checks and 24 fresh-case browser checks. Counts overlap and must not be added into a unique-test total. The older 51-check browser suite and initial 26-check public suite are retained as candidate evidence, not a replacement for final checks.

Evidence index: p16b-acceptance.json, p16b-final-public-release.json, p16b-final-public-http.json, p16b-final-public-browser.json, p16b-portable-final-summary.json, p16b-capabilities-browser.json and p16b-visual-review.md. Initial failures, CF installation limitations and intermediate release evidence remain. All P16B.1-P16B.5 checks are complete within this documented scope. Next is P16C only after user instruction, with Astra Ultra recommended.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
