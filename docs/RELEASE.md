# Depth Atlas 0.17.1

Release checked on 27 September 2026. [Open the app](https://depth-atlas-seifuku.vercel.app/).

This release adopts the Depth Atlas name and team address, updates public identity labels and preserves the full name on small screens. A narrow header overflow was corrected. Scientific methods and the 304-file checked data publication remain unchanged.

Publication identity: `4665900474b7560a85d27f881ad4a5c2c9752150c1f154551a3fc8ff284939b0`.

## Verification

| Check | Result and boundary |
| --- | --- |
| Source package backend tests | 854 passed; 109 skipped because their original acquired reference archives are not bundled. Three existing test/dependency warnings. |
| Original-archive checks affected by test portability changes | 145 passed on the development host where the reference archives are present. Numerical assertions were retained. |
| Client numerical checks | 82 passed in the exported package. |
| Production release | 24 anonymous API, page, asset-byte and release checks passed without retries. |
| Production replay | 61 exact checks across 17 requests passed. |
| Current browser journey | Desktop, 390-pixel mobile and 320-pixel narrow layouts passed. The desktop journey retained 3D, optional cutaway, native temperature 22.303, 103 eligible pairs, residual -0.152, explicit save and exact recalculation. |
| Public pages | About, Privacy, Terms and data access passed the new-name checks. |

These checks overlap and should not be added into a unique-test total. The browser checks used Chromium automation on Windows; mobile sizes are emulation, not physical-device tests. The source-package checks use a fresh frontend dependency install and the established Python environment on that host, not a newly provisioned machine.

The first clean-package test run exposed absent raw-reference prerequisites and a module-wide test client exhausting its process-local budget. Tests now explicitly skip missing archives and isolate the heat API client per test. The application rate limits and scientific tolerances did not change. Earlier compatibility records preserve their result and replay identities, including deliberate rejection of obsolete methods.

## Remaining limits

The system is a research and demonstration prototype with bounded historical coverage. Independent oceanographic review, unfamiliar-user studies, physical-device coverage, full external CF certification, persistent public standards hosting and actual institutional installation remain separate work. No operational forecast improvement or institutional endorsement is claimed.

Private development logs, earlier repository history and submission records are outside this initial public release. Original source credits and third-party licences remain included. The main app can be reproduced from the checked case packs; independent source-reference tests need the original archives described in the method documents.
