# P17 security review and request safeguards

Reviewed 27 September 2026. This is an application security review with targeted regression tests, not an independent penetration test, a compliance certification or a promise that the service cannot be abused.

## Implemented changes

The public API now limits requests before decoding JSON or running scientific work. A pure ASGI guard counts bytes even when Content-Length is absent. It rejects invalid or oversized lengths, compressed request bodies, excessive header/query data and browser POST requests from another origin. A body deadline stops incomplete uploads. Errors retain the existing JSON envelope, request ID, app version and no-store response policy.

| Boundary | Current limit |
| --- | --- |
| Ordinary scientific JSON | 65,536 bytes before parsing |
| Original observation upload | 2,000,000 bytes |
| Imported comparison/support and investigation replay/export | 3,000,000 bytes |
| Regional pack replay | 4,500,000 bytes |
| Request headers / query string | 32,768 / 8,192 bytes |
| Body completion | 15 seconds after admission |
| API requests per client, per process | 360 per minute, burst 360 |
| POST calculations per client, per process | 60 per minute, burst 60 |
| Concurrent API requests per process | 24 |
| Concurrent POST calculations per process | 4 |
| Counter identities per process | 2,048, idle expiry after 10 minutes |

Admission is immediate. A full calculation slot or exhausted token bucket returns HTTP 429 with Retry-After instead of growing an unbounded queue. Slots are released after a response, a disconnect, timeout or exception. Counters use a process-specific salted HMAC of the client address; raw addresses and request payloads are not retained by this guard. The Privacy Policy describes these counters. It does not make a provider-wide log deletion promise.

Vercel deployments use the platform-supplied `x-vercel-forwarded-for` only when the server's VERCEL environment flag is set. Direct installations use the ASGI peer address and ignore raw forwarded headers. Institutions using a reverse proxy must configure its trusted proxy addresses correctly and apply their own public edge limits. The generic X-Forwarded-For header is not trusted by application code. [Vercel request header documentation](https://vercel.com/docs/headers/request-headers).

**These are process-local controls.** Independent serverless workers have separate counters; cold starts reset them. They are not a distributed quota, bot detector or DDoS protection claim. The deployment uses the existing Vercel project. A shared edge policy or external atomic store would be needed for one globally consistent quota. No new paid service, account or secret was introduced.

The four-slot budget applies specifically to POST requests. Native subset, evidence comparison/coverage and drift-context GET requests can also perform substantial calculations; they share the 24-request total and the 360-per-minute client budget. This is a finite bound, not a claim that 24 cold scientific requests fit every machine's memory or response target. An institutional proxy must tune its workload limits against measured datasets and worker resources. No security setting is exposed as a public API or user-controlled environment input.

## Browser and deployment controls

The viewer uses a Content Security Policy with same-origin API connections and scripts, the exact SHA-256 of its existing inline startup recovery guard, no arbitrary inline JavaScript, no eval, no objects, no base URL changes and no form submission. Inline styles remain allowed because React places the tutorial and scientific overlays dynamically. Framing is denied, and camera, microphone, device location, payment and USB permissions are disabled. Vercel responses declare HTTPS Strict-Transport-Security.

The separate `/api/docs` page retains its pre-existing Swagger CDN dependency with an explicit CDN allowlist and the hash of its fixed startup script. This exception applies to API documentation, not the application workspace. The docs page still needs internet access for its reference UI; the OpenAPI JSON is served locally. Existing downloaded offline investigation files have their own hash-based CSP and no network permissions. Viewer controls do not replace those file policies.

Both Python and Vercel header definitions are checked against the source startup script. If that script changes, its allowed hash must change in both places before deployment. Source maps remain disabled in the frontend build. `.env*`, `.vercel`, local runtime directories, tests, logs and documentation remain excluded from the public deployment.

## Existing boundaries checked

- The viewer is account-free. There is no password store, session cookie, payment endpoint, user database or external language-model adapter to harden in this release. No API key is required by the browser. Future providers must keep credentials on the server and trigger another policy/security review.
- Public source data is packaged by maintainer tools. Runtime requests do not fetch an arbitrary user URL. Case IDs, example names and profiles resolve through checked collections, not arbitrary file paths.
- Observation parsing rejects unsupported formats and nested NetCDF groups. Limits include 160 variables, 32 dimensions, 5,000 source samples and 24 Argo profiles; Argo total decoded elements and individual selected NetCDF variables have bounds before decoding. Imported responses are capped at 3.5 MB. Native NetCDF access is serialized.
- Imported original files are reparsed from bounded bytes and retained only for the request. Uploaded files do not enter the public immutable result cache. File checksums and parser/method versions remain checked during replay.
- Existing scientific schemas cap coordinate ranges, sample counts, iteration settings and output sizes. The broader new transport guard does not replace these scientific checks or change calculations.
- Investigation HTML escapes source/user text. Offline data escapes the `<` character before embedding JSON and uses textContent for display. CSV exports protect formula-like text while retaining negative numeric values. Portable original filenames reject directory separators and control characters.
- The publication switch remains a maintainer-only local operation; there is no public publication mutation endpoint. New publication/source identities are validated before startup.

## Evidence and reproduction

- `evidence/p17-security-regression.log`: 84 passing guard, API, original/import-preview, imported-replay and structure-support tests. This includes three parallel sessions, a 120-request read burst, rejection/recovery, timeout, disconnect, oversized chunked input, malformed headers and exact script hashes.
- `evidence/p17-security-tests.log`: initial 82 passing tests before the extra parallel-session and disconnect cases were added.
- `evidence/p17-security-deadline-tests.log`: all 13 guard tests pass after the independent code reviewer identified and corrected an absolute-deadline edge case. The regression advances a fake clock between immediately available chunks and requires a timeout before another chunk is read.
- `evidence/p17-python-secret-audit.json`: all 19 exact runtime pins queried successfully using the primary PyPI release JSON advisory records. Zero active advisories were returned at the recorded time. The scan found no listed secret signatures or tracked environment/credential paths among 1,270 tracked/build files.
- `evidence/p17-npm-audit.json`: npm reported zero known advisories in 158 frontend/build dependencies at the recorded audit.
- `evidence/p17-python-secret-audit-final.json`: the exact-pin/signature audit was repeated against the final 0.17.0 build. All 19 PyPI queries succeeded, with zero active advisories, candidate secret signatures or tracked sensitive paths in the same 1,270-file scan scope.
- `evidence/p17-security-built-headers.json`: 8/8 checks pass on the final local 0.17.0 worker at port 8038. The built startup script hash and headers on the workspace, three legal pages, API reference and health endpoint agree with the policy. This verifies local responses; the separate final public evidence is recorded below.
- `evidence/p17-drift-security-isolation.log` and `.xml`: 81/81 drift API and security checks passed after fixing scientific test isolation. The initial full backend run had 952 passes and 11 drift-test failures because one module-wide simulated client spent its 60-request POST burst across unrelated parameterized cases. Each scientific test now has a distinct simulated peer on the same shared app, preserving source caches, production rate defaults and stable identity within each test. No production limit was raised or bypassed. The original full-run failures remain in `p17-backend-final.log`.
- `evidence/p17-backend-accepted.log` and `.xml`: the complete integrated backend rerun passed all 963 tests in 295.24 seconds after that fixture correction. The three warnings concern deprecated test-client APIs and an existing JUnit property compatibility warning, not failed checks. Runtime source remained `5a5e6160a7165427d6f5a174b58083f5a2db7750`.
- `evidence/p17-security-public.json`: all 14 public security checks passed on READY deployment `dpl_6REGcXUreo8pXinNuhQp331W2ANe`, release 0.17.0, source checkpoint `0f5c417`. Thirteen bounded requests checked HTTPS/HSTS, exact workspace/legal/API-docs CSP, denied framing/permissions, unavailable private paths, malformed JSON and cross-origin rejection. Error envelopes retained app version, request IDs and no-store. A preceding single GET encountered a local report-script attribute error; no application defect was indicated and the corrected run is recorded.
- `evidence/p17-swagger-public.json` and `.png`: one actual public Chromium page rendered the Swagger API reference with 45 operations and version 0.17.0. Both existing CDN assets and local OpenAPI JSON returned 200. No page, console or request errors occurred. This checks that the API-docs CSP exception works in a browser, not only in response headers.

Run from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_security.py tests/test_api.py tests/test_instruments.py tests/test_import_preview.py tests/test_imported_investigations.py tests/test_structure_support.py -q
.venv/Scripts/python.exe deploy/security_audit.py --report docs/evidence/p17-python-secret-audit.json
npm --prefix web audit --json
```

The Python advisory check uses the same primary PyPI JSON records that are documented by [pip-audit](https://pypi.org/project/pip-audit/). It is a direct exact-pin query, not a claim that pip-audit was installed or run. The scanner prints only the file, line and signature type if it finds a candidate; it does not print a matched credential value. Ignored personal credential stores and env files are not read. Advisory absence and signature scans cannot prove there are no vulnerabilities or secrets.

## Remaining limits and deployment checks

The final public response-header, bounded-error and API-docs checks are recorded above. Complete tutorial, import, saved-export and numerical replay verification remains in the root release evidence, separate from these security requests. No public flood test was performed.

Native scientific dependencies include netCDF-C 4.9.3 and HDF5 1.14.6 in the checked Windows environment. The version-specific PyPI scan does not comprehensively audit those C libraries, the operating system or Vercel infrastructure. File limits and serialization reduce resource exposure but do not sandbox native parser vulnerabilities. A future institutional deployment accepting untrusted uploads at scale should isolate parsers in constrained workers and maintain its own OS/library patch process.

Already accepted server computations can finish after browser cancellation; this is stated in the Privacy Policy. Application bounds and Vercel's 30-second function duration remain relevant. A slow connection can exceed the 15-second upload admission window, and people sharing a network share its per-process client counter. Test automation is not evidence that every device or network will succeed.

Prepared explanation: The release adds limits around public requests and uploads, keeps credentials out of the browser bundle and saved investigations on the user's device, and restricts which browser resources can execute. The tests exercise those boundaries without changing scientific values. This is a hardened public prototype, with process-local rate limits and external infrastructure responsibilities stated explicitly.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
