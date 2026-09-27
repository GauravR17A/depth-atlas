# Phase 16: learning through real actions

Completed provider-free implementation on 26 September 2026 and deployed as release 0.16.0. Extra High was recommended. The conditional P16.3 external language-model adapter remains unconfigured and incomplete.

## Problem-statement priority

The official SIH2026 problem page was rechecked on 26 September: https://www.the event.gov.in/sih2026PS, statement the project brief. Its central request is a browser workspace combining depth-resolved model fields with instrument observations. The current statement retains the core rendering, profiles, ingestion, configurable display, lightweight backend, extensibility and open-standards requirements already recorded in docs/reference/official-2026/the project brief-statement.txt. It also explicitly includes outreach to students and the public. There is no published feature-weight table in this statement.

Our demonstration order is a product decision, not an official scoring scheme:

1. See a real model in 3D, open a cutaway, inspect depth, switch variables and time, and read the colour key.
2. Co-display measurements, inspect timestamped profiles, compare eligible readings, and demonstrate supported file ingestion.
3. Show source access and preservation of evidence. Explain browser access, backend and interoperability without making infrastructure the visitor's first task.
4. After the core tour, offer investigations: structures, Drift, Heat & Depth, Climate, Expedition, evolution, blackout and wider regions.

## User-requested interaction

Basic is selected by default. It performs one real app action per step and briefly explains the resulting output. In-depth is deliberately selected and adds the concepts, method and limitations behind each feature, plus optional comprehension questions. Visitors control Next, Back, replay, practice and Skip. There is no forced continuous autoplay. The initial choice fits the viewport without scrolling. Shared investigation links retain direct replay access.

Tutorial actions call existing component handlers and use parsed result snapshots. Missing or failed requests cannot produce a success explanation. Source dates remain historical. The explanation assistant uses bounded, visible query plans and explicit supported topics; arbitrary prose never supplies measurements. A language-model provider is optional and currently not configured. No account or external model service will be invented to mark that integration complete.

## Acceptance to run

- Both modes, every core and additional demonstration, Next/Back/Skip/replay/practice, keyboard, narrow/landscape layouts and reduced motion.
- Actual backend values and query parameters agree with tutorial outputs, source references and explanations.
- Unknown questions, forged values/source attribution, absent sources, delayed/stale requests and resource bounds.
- Existing scientific fixtures and representative prior workflows, then local/public visual checks and the deployed release verifier.
- Record exact outcomes and corrected initial failures. Real unfamiliar-user feedback remains the separate P09.5 gate.

## Implemented design

There are 27 demonstrations: 17 essential steps followed by 10 optional lab steps. Model depth, co-located instruments and eligible model-observation comparison appear before the additional experiments. Visitors can choose any lesson, pause to experiment, resume, replay, or skip. The first choice is a short illustrated panel, not a scrolling document. Release 0.16.1 replaces the fixed coach with anchored callouts. On a small screen the highlighted control or chart stays beside or above the callout; Next stays available. Completed source values take priority over a repeated action sentence on short screens.

The same lesson action contracts are used in both modes. In-depth adds separate Watch, Understand, Method and optional question views. The question feedback teaches distinctions such as model versus observation, missing versus zero, and a display stretch versus a changed physical depth. No score or answer history is stored. Shared investigation links retain direct replay rather than being blocked by a new tutorial.

`web/src/learning/bridge.ts` connects each existing workspace handler to a current, parsed result snapshot. A lesson waits for its own command ID and an available result. Actual imports use the bundled public CSV/NetCDF files and the ordinary parser. Numerical simulations call the existing solver. Save opens the real form without automatically persisting, downloading or sharing a record. Skipping cancels tutorial-owned asynchronous work; a manual tool change or assistant action pauses the coach.

## Grounded explanation and query scope

Explain reads the current result's provenance kind, facts, units, applied parameters, sources and limitations. Its numbers come from parsed results, not prose generation. Reviewed definitions cover the concepts behind the tools. Supported commands include `Show salinity at 200 m`, `Open cutaway`, `Show depth slice` and `Show current vectors`. The visitor reviews a query before applying it. The depth must exist in that case's original coordinate list; unsupported values are not silently rounded.

The request parser is anchored and bounded to 300 characters. Unknown questions, injected instructions, forged measurements/source attribution and arbitrary external URLs cannot become numerical queries. A missing, loading or failed result has no completed-result explanation. Requests and optional comprehension answers stay in this tab; no external language model is connected and there is no provider billing path. Existing data requests still use the app's backend. Privacy and Terms describe this distinction.

P16.3 is conditional. No provider/account is configured for this workspace, so no external LLM adapter, broad conversational capability or additional language is claimed. The provider-free explanation and validated-query path is implemented. This preserves the roadmap's explicit provider-free completion option without marking the optional provider integration complete.

## Prepared short explanation

The tutorial operates Depth Atlas one step at a time. First it opens real model fields, then checks source measurements and explains the output. Basic mode shows how to use each feature. In-depth adds the science, the method and the limits. Visitors can stop, try the controls and resume whenever they want. Explain reads the current result and its sources, so missing evidence stays missing.

## Demonstration path

Open the app with Basic selected. Start, open the cutaway, inspect 100 m, and proceed to sensor markers, the Argo profile and eligible comparison. Show the actual count and explain why agreement is not automatically independent validation. Continue to time, salinity, currents, isosurface, section, display controls and genuine imports. Open the save form and close it without saving if no record is needed. At the core completion screen, choose the additional labs. The remaining steps demonstrate structures, eight fixed-depth passive particles over six historical hours, heat evidence, El Nino and La Nina, virtual stations, evolution, blackout and a bounded wider-source region.

Reopen Guide and explicitly choose In-depth to show Understand, Method and one optional question. Open Explain, review an exact-depth query and apply it. Ask for an unsupported depth to demonstrate the honest refusal path.

## Limits and next work

The tutorial uses historical prepared cases, not live conditions or equal coverage everywhere. Basic graphics disclose their 2D fallback. The external LLM adapter remains unconfigured. Automated interactions and visual inspection do not establish that unfamiliar people understand the concepts; P09.5 still requires real participants. P17 is the next separately authorized implementation phase and Ultra is recommended for its cross-feature scientific and release audit. Operator/contact identity and persistent public THREDDS remain open dependencies.


## Local acceptance and retained corrections

- `npm --prefix web run build` passed TypeScript and Vite for release 0.16.0. The existing large-chunk warning remains; see `evidence/p16-build-final.log`.
- `npm --prefix web run test:science`: 60 passed, no failures or skips, including 21 new bounded-query/explanation cases. See `evidence/p16-science-final.log`. The scientific Python algorithms, source packs, tolerances and method versions were not changed; the earlier 857-test P15 backend run is historical and was not rerun for this phase.
- The final local learning/UX suite passes 78 scenarios across Chromium desktop, WebKit desktop and Chromium mobile emulation (`evidence/p16-local-learning-final.json`). The later final button/input layout adjustment passes a focused 12-scenario run, including all 27 demonstrations in each engine (`p16-final-layout-browser.json`).
- The broader initial local regression has 163 passed, four failed and one existing WebKit context-loss skip (`p16-browser-third.json`). Its failures exposed a resume-state race and an enlarged-text mobile overflow. Both were corrected and their focused/full learning checks now pass. The original report is retained; it was not a single green 168-test local run.
- The final local visual harness records 31 captures with no measured overflow, welcome-fit, Next-visibility, input-width or page/console-error failures (`p16-visual-release-candidate/checks.json`). Screenshots were inspected, not only counted. The short-screen coach may scroll internally while Next stays visible; the initial tutorial choice fits without scrolling at the checked normal-text sizes.

Earlier checks found a wider-source readiness stall, a Retry button that needed to refetch failed data, inconsistent focus after Skip, an enlarged-text welcome overflow, a small-screen Next position, and a collapsed desktop explanation input. Those are fixed. Initial browser reports remain: 21/27 passed, then 59/66. Some first-run failures were test defects: 200 m is the selected case's native index 22, not index 27 (500 m), and two controls had incorrect accessible-name expectations. The selected option text now verifies the physical depth directly. One explanation test looked for the word 'eligible' where the correct text said 'matching rules'; the assertion was corrected without changing scientific behavior.

The full initial smoke reached 25 steps before the wider readiness defect. A corrected run completed 26, and the final sequence with the save-form lesson completed all 27 without recorded page/console errors (`evidence/p16-third/result.json`). The browser suite adds explicit checks of native values, 100 m selection, the 20 degree isosurface threshold, eligible pairs, applied particle count/duration, ENSO season changes, actual CSV/NetCDF imports and the blackout result.


## Public acceptance and handoff

Deployment `dpl_DKCJL8hUP9kNgSPePaaoHFiawV5Z` is READY on the existing Vercel project. [Public app](https://depth-atlas-seifuku.vercel.app/?release=0.16.0); [immutable deployment](https://depth-atlas-seifuku.vercel.app/). The deploy command was `npx --yes vercel@59.23.2 deploy --prod --yes --scope kai-vexen-studios` and exited 0; see `evidence/p16-vercel-deploy.log`.

The broad public browser run has **162 passed, 5 failed and 1 skipped** across Chromium desktop, WebKit desktop and Chromium mobile emulation. A focused WebKit/mobile run with unchanged assertions and deadlines had **9 passed and one initial-case loading timeout**. A further isolated full WebKit tour then **passed all 27 demonstrations**, also with unchanged assertions and deadlines. The focused runs used one browser worker to isolate the timing observations. This was not a single green 168-scenario public run. Reports: `evidence/p16-public-browser.json` and `p16-public-focused-recheck.json`, followed by `p16-public-webkit-tour-recheck.json`. The retained skip is the existing WebKit graphics-context-loss scenario.

The initial hosted failures include an approximately 19.7-second JavaScript download, requests missing the client deadline, a delayed regional module, and a regional refinement exceeding its test deadline. They did not show an incorrect numerical result. The app retained explicit loading/error states. The trace alone does not establish whether origin, network or local browser scheduling caused the delays. A later passing run does not guarantee performance on every judge's connection. A separate three-request HTTP sample returned health and case metadata in about 0.53 s each and a display subset in 1.69 s, recorded in `evidence/p16-http-timing-sample.json`; this small sample does not explain or negate the browser timing failures. Timing observations are retained in `evidence/p16-public-timing-observations.json`; broader physical-device and performance work remains in P17.

The anonymous release verifier passed **21 checks / 21 requests**, zero retries, including API version, all five original cases, all eight built JS/CSS assets against local bytes, legal pages, favicon/notices and bounded private-path checks. Command: `.venv/Scripts/python.exe -m science.verify_release --url https://depth-atlas-seifuku.vercel.app --report docs/evidence/p16-public-release.json --deployment-id dpl_DKCJL8hUP9kNgSPePaaoHFiawV5Z`.

The final public visual harness passed **31 captures** with zero recorded page/console errors or measured layout/control failures. See `evidence/p16-visual-public/checks.json` and `p16-visual-review.md` for actual inspection, corrected defects and short-screen scrolling limits.

P16.1, P16.2 and P16.4 are delivered, with X30 and the provider-free scope of X31. P16.3 remains conditional and unconfigured. P09.5, R12 and X14 still require real participant evidence. P17 is not started. No source array, backend scientific method, numerical tolerance or runtime dependency changed. There is no Git commit or remote; a local recovery archive is recorded separately, not represented as source submission.


## Follow-up: a guide beside the feature

The user requested moving guidance after trying release 0.16.0. Release 0.16.1 replaces the reserved sidebar with measured callouts. Each lesson identifies a visible control or chart. The app moves that destination into view, points to it, and keeps Back, Next and Skip with the explanation. Controls remain interactive. Manual scrolling is respected, with a return action if the target leaves the viewport. Small-screen graphics make room for the guide, and enlarged explanation text scrolls separately from navigation.

The save lesson now includes a hint directly beneath the name field in the actual form. Closing that hint resumes the tour; it does not save anything. The provider-free explanation, all 27 real demonstrations and the scientific contracts are unchanged. Placement coverage is added in tutorial-anchor.spec.ts and the complete tour also requires every lesson to find its anchor. The follow-up is deployed. Corrected local learning/placement checks pass 54/54; the final narrow-value presentation passes 15/15 placement checks. The final local visual sweep has 41 captures with no recorded layout failures. Public API/assets pass 21/21, while browser runs retain intermittent request/script delivery failures. Exact outcomes and limits are recorded in PROJECT_STATE.md.

## Follow-up: teasers and direct feature tours

The additional demonstrations were available only after the core sequence or inside the lesson chooser. The new picker introduces each feature with a question, an icon, its result kind and the actual number of guided steps. It appears from the welcome teaser, the active guide's Extra features action, the core completion and the end of an individual feature tour. Two cards appear at a time over four pages. Back, More features and Close are explicit controls. Basic remains the default; In-depth can be chosen in either the welcome or picker.

| Feature teaser | Demonstrations launched |
| --- | --- |
| Drift | Calculate eight passive particles over six hours, then play the calculated paths |
| El Nino & La Nina | Inspect the supported 2015 comparison, then switch to the supported 2022 season |
| Heat & Depth | Inspect the checked surface heat event and available depth context |
| Ocean structures | Inspect native connected regions satisfying the displayed rule |
| Virtual expedition | Build and inspect a sampling plan from the declared prior |
| Feature evolution | Inspect native overlap links, including splits and merges |
| Sensor blackout | Exclude a profile and inspect remaining and lost comparisons |
| Explore other regions | Load a bounded region from the wider source controls |

The individual routes stop after their own steps and offer another feature or independent exploration. The complete 27-step path and complete extra-lab path remain available. The same real handlers, numerical snapshots, source limits and moving anchors are reused. The picker itself launches no lab calculations. First actions wait for the case catalogue, so selecting a teaser before the catalogue arrives cannot lose its intended destination; Skip cancels the pending tour.

Implementation: `featureTours.ts` defines routes, `FeatureTourPicker.tsx` renders teasers, and `LearningExperience.tsx` manages the bounded sequence and return path. `App.tsx` supplies catalogue readiness. `feature-tours.spec.ts` checks all direct entries, prerequisite order, bounds, mode, return/cancellation, delayed catalogue and layout. `p16-teaser-visual.mjs` captures normal and enlarged-text layouts. Actual acceptance and release evidence are recorded in PROJECT_STATE.md; the earlier public transport limitations and unfamiliar-user gate remain separate.

Release 0.16.2 is deployed and verified. The final new-feature suite passes 39/39 locally across the three checked browser configurations and 13/13 on public Chromium. The 60 frontend scientific/parser/explanation checks and all 21 anonymous release/API/asset checks pass. Final visual acceptance covers 29 captures without measured failures or page errors. The broader 90/93 local run retained three picker-fit failures, which were fixed and passed the final feature suite. Screenshots subsequently caught a completion-action visibility issue, corrected and verified in the final visual sweep. No tolerance or ready-result assertion was weakened. See PROJECT_STATE.md and `evidence/p16-teaser-visual-review.md` for exact commands, evidence and retained limitations.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
