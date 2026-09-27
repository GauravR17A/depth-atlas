# P16C: imported comparison and reproducible saving

Work date: 27 September 2026. Release 0.16.8 is deployed. All four acceptance steps pass for the declared scope. Public and local evidence is recorded in PROJECT_STATE.md and evidence/p16c-acceptance.json. This checkpoint owns follow-ups 15-18, extending R05/R06, X03, X10 and X11.

## What changed

A supported imported observation can use the existing native-column comparator. The original file is reparsed for every comparison, coverage, capture, replay and verified export request. The service does not accept client-supplied normalized profiles as scientific input. The selected file supplies its own temporary observation catalogue; the frozen bundled library and its source hashes remain unchanged.

Comparison retains the existing variable-definition, source-review, coordinate QC, reading QC, physical depth, geography, time-window, distance, mask and adjacent-depth interpolation gates. Temperature means in-situ Celsius and salinity means practical salinity. No potential-temperature substitution, temporal interpolation, masked-gap bridging or chlorophyll model value is introduced. Residuals are model minus observation; summary statistics use eligible source samples only. Coverage and discovery explicitly cover the selected imported file. A reference can compare settings within that file; changing between files or the bundled library clears the old reference.

The real BGC 1902594 cycle 34 file dated 29 March 2024 overlaps the March HYCOM case. At the 29 March 00:00 UTC snapshot and the default 6-hour, 5-km, 500-m limits, 245 temperature samples and 243 salinity samples qualify. These are observed counts for this file and configuration, not a performance or accuracy score. Chlorophyll remains an observed estimate with its original adjustment and QC; the model has no chlorophyll field. HYCOM assimilation prevents treating agreement as independent validation.

## Source identity and replay

- Original bytes are embedded as bounded base64 with filename, SHA-256, parser version and explicit CSV mapping. Source URLs are never fetched during replay. Recognized public examples retain their checked attribution by byte hash.
- Parser: observation-preview-v1. Imported workflow: p16c-original-input-v1. Comparison mathematics: p05-native-column-v1. Pressure-to-depth and native source metadata remain those of the existing adapter. Parser changes require a new version and explicit migration policy.
- Source identity binds the model manifest, imported catalogue, original-file context and all reparsed profiles. The settings/result fingerprints use the existing tagged-json-f64-sha256-v1 cross-language representation.
- Reopening reparses the embedded original, verifies parser/method/source identity, recalculates outputs and checks exact result hashes before restoring the workspace. Corruption, unavailable models, changed mappings or unsupported versions stop replay. Hashes establish consistency, not authenticity, ownership or scientific truth.
- Saved imported profiles preserve selected variable, sample, excluded-value preference and model context snapshot. The new optional snapshot field is omitted when absent, preserving old instrument recipes. Comparisons retain snapshot, variable, matching policy, selected sample and optional reference policy.
- Existing archived records keep their original recipe, library and result identities. An old result's historical capability sentence about inspect-only imports remains inside the fingerprinted archive. Current UI and readable reports explain the current imported-comparison capability without rewriting historical numerical modules.

## Storage, sharing and limits

Save on this browser is explicit. IndexedDB retains the original file, mapping, parsed profiles, settings and results. Existing limits remain 25 records, 32 MB total and 8 MB per local record. Removing a local copy does not delete downloads. Clearing imported profiles clears that active workspace and its imported comparison query cache, without deleting separately saved records. Browser cleanup or storage eviction can remove local records.

JSON downloads and evidence ZIPs include the original uploaded file. The ZIP also provides the unmodified file under original-observation/, full-precision numerical CSV, settings, source references and a readable report. Only share files that the uploader is authorized to distribute. Imported data is excluded from URL sharing; model data remains a pinned external dependency. HTML/CSV are readable evidence, not complete offline replay engines. Reopening needs the app service and matching model pack.

The service processes uploads in request memory, does not write upload files or saved records, and bypasses the bundled comparator's process-wide caches for imported profiles. Comparison/replay/export send the embedded file back to the service. Privacy and Terms describe this behavior, with the existing operator and no-affiliation wording retained. This is not completion of the deferred P17 security audit.

Original file limit: 2 MB. Existing parser bounds: 24 profiles and 5,000 samples per file. Workspace: 24 profiles and 12,000 samples. New JSON request envelope: 3 MB. Imported investigation response budget: 4.2 MB; an oversized result returns an explicit smaller-input suggestion. Local records remain limited to 8 MB. Larger uploads, batch jobs and persistent server storage are not added by this checkpoint.

## Demonstration path

1. Open the March Bay of Bengal study case and choose 29 March 2024 00:00 UTC.
2. Tools > Open instruments > Import observations > Formats and genuine example files. Preview SR1902594_034.nc, review its variables/QC and add it.
3. Inspect chlorophyll and its source flags. Choose Compare with model to compare temperature, or switch the comparison variable to salinity. Read eligible counts, residuals and exclusions.
4. Keep a reference. Narrow the time window to one hour and apply it. The temperature comparison becomes empty because the actual observation is at 02:30:44 UTC; the six-hour reference remains available.
5. Save investigation, name it and choose Save on this browser. Download JSON or the evidence ZIP. A replay link is intentionally unavailable for imported data.
6. Reload, or use another browser context. Open the record from Saved or import the JSON, then choose Recalculate and reopen. Matching source, settings and results are required before restoration.

## Verification and boundaries

tests/test_imported_investigations.py checks original TEMP values/QC from the raw BGC NetCDF; independent great-circle column selection, physical-depth interpolation and metrics from the checked native CF exchange; mapping and missing/QC behavior; source/parser/method/result failures; request budgets; exact exports; and no mutation of the frozen library or import retention through its global caches. Existing investigation, import, evidence, source-provenance, instrument and fresh-model tests are retained.

web/e2e/imported-investigations.spec.ts exercises fresh-context portable replay, reload/deletion, mapped Kelvin CSV, rejected tampering, source switching and matching sensitivity. Existing saved investigations, import review and March model paths are regression checked. Browser automation is not a substitute for an oceanographer or unfamiliar-user study.

science.verify_p16c compares served results with fresh local calculations, checks original bytes in ZIPs, rejection paths and four archived P08 modes. web/benchmarks/p16c-visual.mjs captures desktop/tablet/mobile controls, scientific charts and save disclosure. Actual accepted run counts, public URLs and reviewed images are in PROJECT_STATE.md and the acceptance report.

Glider/CTD examples still need appropriate co-located model cases for a real simultaneous demonstration. No universal model compatibility, independent scientific certification, offline exact server replay, cloud account storage or operational forecast skill is claimed. Next checkpoint: P16D connected scientific views and guided investigation, with Astra Extra High recommended.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
