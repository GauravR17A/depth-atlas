# P16E: import workload, publication and offline continuity

27 September 2026. Release 0.16.10. The scoped acceptance record is evidence/p16e-acceptance.json; public connection limitations and failed checks remain part of that record.

## Delivered scope

P16E owns follow-ups 14, 23, 24 and 30. Batch review remains mounted while model metadata arrives or the model context changes. It reads up to eight original observations sequentially, shows each result and lets the user add ready files explicitly. A failed file, cancelled queue or workspace quota failure preserves earlier successful additions. CSV mapping and QC review remain available per file. Duplicate profile IDs replace their earlier copy rather than consuming another sample quota. Original input, parser identity, units and scientific matching methods are unchanged.

Sources > Data publication and updates shows the serving dataset identity, historical coverage, source retrieval dates and publication check time. A status check preserves its previous information when offline, cancelled or timed out. The public site publishes checked case packs with an application deployment. A maintainer-only local pipeline supports isolated candidates, integrity checks, atomic activation, durable status and retained previous releases. There is no public dataset-write endpoint, live-data claim or scheduled provider acquisition.

Saved investigations > Offline viewer downloads a self-contained HTML for observation profiles, model comparisons, comparison references and native model columns. It preserves exact saved values, irregular depths, missing samples, QC and source identity. Observation dates and model dates are shown separately above the chart. It includes variable/sample controls, source context, a plot and the original investigation JSON. The UI states the snapshot age and unavailable computations. Other laboratory modes keep existing JSON, CSV and report exports. The existing regional offline pack also remains available.

Save, replay and verified online exports expose cancellable request stages. Cancellation ignores late client results and keeps earlier records. A server calculation that has already started may finish within its existing bounds. The short IndexedDB commit stage cannot be cancelled midway; it is labelled Writing local record. Quota/storage failure leaves verified portable evidence available without claiming a successful local save.

## Measured and enforced budgets

| Boundary | Limit |
| --- | --- |
| Each original observation | 2 MB, 24 profiles, 5,000 source samples |
| Each parser review response | Existing 3.5 MB decoded JSON limit |
| Batch review queue | 8 files, 16 MB originals, 24 MB decoded reviews |
| Imported workspace | 32 profiles, 20,000 samples, 16 MB originals, 24 MB decoded profiles |
| Imported replay/comparison request | Existing 3 MB JSON envelope |
| Imported investigation response | Existing 4.2 MB limit |
| Local investigation record/library | Existing 8 MB per record, 25 records / 32 MB total |
| Offline viewer data envelope | 16 MB, including original record and prepared series; HTML escaping and viewer code add bytes |
| Prepared publication | 250 MB, 5,000 files, 100 MB per file |
| Maintainer publication store | 1 GB including retained releases; no automatic deletion |
| Import/status/investigation request deadline | 30 / 15 / 45 seconds per client request |

MB means decimal bytes. Queue and workspace can coexist, so their budgets add. Base64, object overhead, temporary JSON serialization, React and scientific scenes require additional memory. Limits bound accepted data; they do not certify a fixed browser RSS on every device.

`science.verify_p16e_workloads` parses six genuine source examples and eight generated resource fixtures. The generated fixtures are clearly marked tests and are never bundled as ocean observations. Their aggregate 20,000 samples occupy 1,693,480 original bytes and 13,611,208 normalized JSON bytes. Serial parser time was 2.339 seconds on this Windows machine. Tracemalloc measures Python allocations rather than all native memory. Browser measurements and deployment checks are separate evidence, with no concurrency or universal device claim.

## Dataset publication procedure

1. Acquire and prepare supported sources in a separate checkout or staging tree using the existing source recipes and adapters. Retain provider timestamps, attribution, masks and original hashes. New case IDs or layouts still need their registered compatibility changes and scientific verification.
2. Use the compatible application version to run:

```powershell
.venv/Scripts/python.exe -m science.publication --candidate C:/prepared/casepacks --store C:/ocean-publications --timeout 120
```

The candidate and store must be separate directories. The pipeline validates registered model manifests, declared file checksums, decoded array dimensions, observation libraries, example files and standards downloads. A portable, case-sensitive ordering of relative path strings makes publication IDs identical on Windows and Linux. An inventory binds every prepared file, including other laboratory packs; their existing module-specific gates remain unchanged. Validation is a compatibility/integrity check, not a new independent scientific certification.

3. Each success writes a new immutable-by-convention release under `releases/<attempt>/casepacks`, its full inventory and an atomic `active.json` pointer. Running readers keep their startup-pinned release. Failure, timeout, Ctrl+C or exhausted storage leaves the previous pointer untouched. Before starting an institutional/local service, set `OCEAN_PUBLICATION_ROOT` to the store. Startup rechecks the selected inventory and application version. Restart to activate a new pointer. There is no in-request swapping of scientific arrays.
4. For Vercel, do not set a writable publication store. `deploy/prepare_vercel.py` validates bundled case packs and generates `api/publication.json` before CDN packaging. Deploy the compatible frontend/API/data together on the existing project, then run release and numerical checks. Vercel's previously deployed release remains the fallback if the candidate build fails. Runtime status exposes no server paths or uploaded files.

The job lock blocks concurrent writers. After an abrupt kill, the last stage can remain recorded and the lock stays in place. Confirm its recorded PID is no longer running before removing that exact lock and any unselected incomplete staging directory. Do not delete the selected release or any release still used by a running process. Storage reclamation and scheduler configuration require a maintainer. A status journal is not a job heartbeat. Power loss, clustered writers and distributed filesystem guarantees are not certified by these tests.

No persistent external scheduler, public THREDDS service or institutional deployment is available. The phase supplies a working bounded manual publication pipeline and records those infrastructure dependencies. A refreshed publication does not change historical measurements to 2026 observations. Changed data/method identities stop old replay; keeping an old directory does not automatically route replay to it.

## Offline inventory and data rights

The downloaded HTML contains its viewer script/styles, original saved investigation, result arrays, QC, settings, references and any original import already embedded in the saved record. No fonts, tiles, textures, libraries or network services are required. A SHA-256 envelope is checked before displaying data; this checks file integrity, not authenticity. A restrictive CSP blocks network access, forms and external content. Source-derived text is inserted as text, not executable markup.

Full model grids, server calculations, new observations, interactive 3D navigation and unlisted lab computation are omitted. Model comparison plots use existing saved pair/residual values. They do not recompute metrics or interpolate new samples. Native current components remain separate quantities. Missing values are omitted, excluded values are optional hollow markers and depth remains positive down. Chlorophyll remains an observed quantity with no model residual.

Save dates and snapshot age refer to the record, while source timestamps remain attached to data. Delete downloaded HTML/JSON files to remove those copies. Remove local copy in Saved deletes only IndexedDB records; clearing site data does not delete downloads. The original providers' licences and uploader's sharing permissions still apply. Privacy Policy and Terms describe these flows. No new account, analytics, external provider or upload storage was added.

## Demonstration

Open Instruments > Import observations. Select genuine Argo and BGC files together. Review both, then choose Add all reviewed files. Select the BGC collection and inspect chlorophyll QC. Save the profile and download Offline viewer. Open that HTML with networking unavailable, switch variables and inspect an original sample. The file still shows its source time and exclusions. Recalculation remains an explicit online operation.

For publication status, return to Sources and open Data publication and updates. Explain the difference between observation/model dates, provider retrieval and publication checking. The maintainer demonstration publishes an unchanged genuine historical pack, adds another checked historical case, then rejects a corrupted candidate. A running process keeps its old catalogue until restarted, and the failed attempt preserves the last usable pointer.

## Limits and next work

The final full public phase run had 20 passes and two failures: a Chromium HTTP/2 body-transfer failure, and a comparison assertion that ended while the result was still loading. All six targeted desktop/mobile recovery checks subsequently passed, including a deliberately interrupted transfer followed by explicit Retry. The original failures are retained. This establishes the tested recovery path, not universal network reliability. The public visual report is separate from the API/source and browser reports.

P17 retains final cross-feature performance/security audit, participant/domain-user testing, release freeze, capability wording review and submission preparation. P16E does not establish universal hardware support, scientific endorsement, operational forecast improvement, equal coverage everywhere or actual INCOIS installation. Full offline laboratory recomputation and live automatic provider updates are outside this declared implementation.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
