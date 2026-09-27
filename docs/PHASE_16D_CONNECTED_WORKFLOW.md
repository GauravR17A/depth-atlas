# P16D: connected scientific investigation

Started 27 September 2026 after the user's "lessgo". Astra Extra High recommended. Accepted release: 0.16.9. This record owns follow-ups 19, 20, 21, 22 and 29. Final accepted deployment and evidence are recorded in PROJECT_STATE.md.

## Implemented scope

Source sample identity and supported variable now travel between source profile and comparison. Both retain the shared model timestamp. Eligible comparisons position the native model probe in the matched column at its nearest native depth; the numerical residual still uses the existing native-depth interpolation. Unmatched samples, independent model picks, changed time and changed variable do not become invented observation matches. Profile saves retain the model context time for both bundled and imported data. Legacy records omit that optional field and retain their old replay identity.

The comparison has a co-visible model panel, with an explicit option to expand the comparison. Narrow screens stack the model and charts. Existing responsive charts, Basic graphics fallback, matching controls and tool access remain. The moving Basic/In-depth tutorials and the prepared guided case remain separate from the new five-step Investigation Builder. The builder walks through choosing data, exploring depth, inspecting a reading, comparing and explicitly saving. It performs no automatic save, preserves its step during a lab detour, resets when the case changes and states unsupported monthly comparisons.

Find structures adds an optional observation-support panel for the selected region. Its plan view shows that region's native footprint, columns with eligible pairs and coverage gaps. Rings make supported columns visible without enlarging their native cell area. Each accepted sample exposes the source date, physical depth, observed/model values and residual. Opening a pair restores its matching rules, model snapshot, profile and exact source sample in comparison. Matching sensitivity preserves a reference for the same structure and observation source. A source or structure change clears that support reference.

## Scientific contract

POST `/api/cases/{case_id}/features/support` takes a P07 query and region ID, compatible P05 matching settings and an optional bounded P16C original-file envelope. The query and matching variable/time must agree. Monthly potential temperature and unsupported observed quantities are rejected. Source/QC/time/distance/native-depth/mask gates are unchanged. Imported bytes are reparsed with the same request-scoped stores, without global file/result caching.

Eligible pairs are associated with the selected region by their matched native column and source depth's midpoint bin. The depth centre and source depth must both lie within the queried interval, following the existing P07 rule. Distinct native cells, distinct columns and profiles are counted once even when several samples land there. Residuals are model minus observed at the source depth, not a bin-centre difference. Observations need not satisfy the model's threshold. Exclusions apply to the selected collection, not an inferred count inside the structure.

Coverage counts are neither confidence nor volume fractions. A supported plan-view column can retain unsampled depths. Gaps describe the chosen collection and matching rules, not absence of every observation. Model agreement may involve assimilated observations and is not independent validation. No source dates, model arrays or existing P05/P07 responses are rewritten.

Support method: `p16d-native-support-v1`. Request body remains at most 3 MB; imported originals remain 2 MB. Support collections are bounded at 128 profiles/100,000 samples and decoded JSON output at 4.2 MB. Oversized output rejects rather than silently truncates. No new upload, hosting or concurrency capacity is claimed.

## Save and export boundary

The existing comparison/structure records still provide recalculated replay. The support panel exports its complete accepted rows, applied rules, source/model identities and optional sensitivity reference as a JSON result snapshot. Imported snapshots include source, parser, parsed-profile and mapping-context identities but do not embed original bytes. A support snapshot is not a replay bundle. Save the structure or linked comparison separately for checked replay. Builder progress and support references remain in the tab until reload. Privacy and Terms reflect these operations.

## Demonstration

Open Build investigation and follow the five steps with the January Bay case. Select a source reading, compare it and inspect the distinct dates. Use Find a useful comparison when the selected snapshot has no pairs. Save explicitly, download and reopen.

For structure support, choose the January Bay case at 7 January 12:00 UTC, default temperature threshold 26 degrees C and 0-300 m. The largest region has 34 eligible pairs in two profiles, touching 23 of 80,203 native cells; 80,180 cells have no eligible pair under those rules. These are source-backed counts, not validation percentages. Retain the support reference and set a zero-hour time window to see the eligible count become zero without changing the structure or source dates.

For the imported path, choose March Bay at 29 March 00:00 UTC. Preview/add SR1902594_034.nc in Instruments. Find structures at temperature >=20 degrees C over 0-300 m, then choose that imported file in Observation support. Open an eligible pair in comparison. The full profile has 245 eligible temperature pairs under default rules, while the structure panel contains only the associated subset. The observation keeps 29 March 02:30:44 UTC. Chlorophyll remains observation-only.

## Acceptance and remaining evidence

Numerical acceptance uses independent irregular-bin boundary/duplicate fixtures, real P05 row equality, January association counts, March original-file identity and stricter-window empty cases. Client contracts reject changed residuals, counts, dates, native coordinates, settings and import identities. Browser checks cover linked selections, explicit saves, restored source samples, imported support, failed requests, monthly incompatibility, keyboard and responsive paths. Final local/public test logs and visual review are linked from PROJECT_STATE.md.

The participant script is P16D_USER_TASK.md. Automated interaction and manual screenshot review do not close the actual unfamiliar-user/domain-user gates. P16E larger workloads, refresh and offline continuity is next, with Astra Ultra recommended. P17 security and release audit remain deferred until authorized.

Accepted 27 September 2026: all four steps passed their declared gates. Backend regression: 163 passes; client science: 73; final public release: 24; support: 24; imported and legacy replay: 61; public browser: 34; public visual: 12 captures at three sizes. Counts overlap. Exact commands, timings, initial failures and corrections are retained in PROJECT_STATE.md and evidence/p16d-acceptance.json. The runtime was not changed to make the public HTTP/2 transport failure disappear; a separate unchanged-build repeat passed.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
