# P06: standards and extension contract

Implementation date: 22 September 2026. Historical case dates remain 7-10 January 2024.

## What this phase provides

The app adds horizontal kinetic energy as a registered derived scalar, using the existing volume, slice, section, isosurface and native-point inspection paths. The formula is `(u² + v²) / 2`, in `m²/s²`. It is energy per unit mass from horizontal velocity, not total three-component or eddy kinetic energy. Both input masks are retained. Calculation precedes display decimation and float32 rounding.

The native exchange NetCDF contains all seven snapshots, forty irregular depths, 76 latitudes, 63 longitudes and five fields. It is generated from checked analytical arrays, not the display mesh. No interpolation or gap filling is applied. Its SHA-256 and original case identity are in `casepacks/standards/manifest.json`. The original model manifest remains unchanged.

The new Use the data page links the download, source identity, REST example, OpenAPI reference and service contract. It states public availability explicitly. Vercel serves the 27.6 MB file as a CDN asset, avoiding the serverless response size limit. Normal browsing still uses bounded, cached scientific requests.

## Standards service and independent checks

The separate service is THREDDS 5.9, Apache Tomcat 10.1.60 and Eclipse Temurin Java 17.0.20.1. Download URLs and vendor checksums are locked in `deploy/standards-runtime-lock.json`. It binds to loopback port 8096. No system-wide Java change or public tunnel was made.

Actual requests were made with OWSLib 0.35.0 and pydap 3.5.9. The independent verifier decodes the original packed NetCDF files manually in float64, without importing the app's adapters, store or product calculator. It compares every field in every snapshot with xarray's reading of the exchange file, including missing masks.

The 143-check protocol/source run includes WMS 1.3.0 capabilities, PNG maps in CRS:84 and EPSG:4326, four geolocated GetFeatureInfo readings, WCS 1.0.0 capabilities and ten NetCDF3 coverages, and five strided DAP2 subsets. WCS requests check time, depth, coordinates, values and masks at 100 m and 5000 m. Unsupported WMS layers produce service exceptions. An oversized 1025-pixel map request was also rejected by the configured 1024-pixel limit.

An initial run exposed two issues in the verification assumptions. THREDDS regularizes horizontal axes for WCS; maximum tested longitude change was 0.0000826928 degree, approximately nine metres. A declared 0.0001-degree tolerance is used for WMS/WCS geolocation, with a separate 1e-12 absolute tolerance for values. Source arrays and values are not modified to accommodate this behavior. Use the download or OPeNDAP when exact source coordinates matter. The pydap slice object drops attributes, so the checker must read `_FillValue` from its parent variable before masking the response. Both initial and corrected reports are retained.

The service was started again in a fresh runtime base with the packaged launcher and the final configuration. The protocol checks passed against that fresh instance. Docker remains unavailable on this machine, so the optional Compose image is prepared but unexecuted. Actual INCOIS installation, public THREDDS hosting, concurrency capacity and universal OGC certification have not been established.

## CF interpretation

The exchange declares CF-1.10. Its scoped checker verifies 1D increasing numeric coordinates, explicit axis/standard-name/unit metadata, unfilled/unpacked coordinate variables, positive-down metre depths, Gregorian time round trips, four declared source-variable definitions, derived-field units, float64 fields with typed fill values, finite unmasked samples and source identity. Adversarial tests alter units, calendar, depth direction, fill metadata, variable definition, axis presence and coordinate order.

The original HYCOM practical-salinity field uses `sea_water_salinity` and `psu`. The exchange expresses the project's documented practical-salinity interpretation as `sea_water_practical_salinity`, unit `1`, with unchanged numbers. Original standard name, units and variable name remain attached. This is a declared metadata normalization, not a numerical conversion to absolute salinity. The horizontal-only energy field has a descriptive `long_name` and units without an invented CF standard name.

Supported cases have independent rectilinear time/depth/latitude/longitude axes and declared in-situ temperature, practical salinity and earth-relative horizontal velocities. Curvilinear or staggered grids, rotated vectors, sigma or pressure vertical axes, arbitrary unit conversion and non-Gregorian calendars need distinct adapters. These checks do not certify every CF construct.

## Extension contract

`adapters/registry.py` registers trusted, versioned Python entry points. The original HYCOM adapter and the new CF exchange adapter both return the same `ModelGrid/native-float64/v1` contract. The exchange adapter accepts latitude/longitude axis names and explicit dimensionless practical salinity, preserving values and physical coordinates. The existing preparation path now selects its HYCOM reader through the registry.

`science/products.py` registers metadata, dependency names and a native-array calculation. Duplicate registrations, missing dependencies, mismatched grids, changed output shapes and non-finite valid results are rejected. Output cannot fill an input's missing cells. Registrations are maintained code; uploading a file cannot install or execute a plugin.

The metadata contract distinguishes derived and externally produced ML products. ML metadata requires model version, training-data reference, validation reference and stated limitations. No ML model or predictions are installed. The current public product allowlist, API schema and frontend presentation metadata still require explicit maintainer updates when adding another quantity; the scientific renderer does not.

## Evidence

- `evidence/p06-protocol-initial.json`: retained initial protocol assumptions and failures.
- `evidence/p06-protocol-verification.json`: final 143 checks plus scoped CF results.
- `evidence/p06-protocol/`: actual capabilities, PNG maps and downloaded WCS coverages.
- `evidence/p06-science-api.xml`: 176 passing science/API tests, including 39 new P06 cases; two existing dependency deprecation warnings.
- Renderer numerical suite: 17 passing checks.
- Local browser full run: 122 passed, three new-test failures and one deliberate WebKit context-loss skip. Initial failures included a closed-details selector, a genuine frontend superscript-unit encoding defect, and a selector for a control hidden in Compare. After the unit correction and test fixes, all nine P06 checks passed. Initial, intermediate and final reports are retained.
- Public browser full run: 117 passed, eight failed, one deliberate skip. Failures involved incomplete loading, request recovery deadlines, one page-receive error and an import interaction timeout. All eight passed a focused recheck with the same code and three workers in 20.7 seconds. The precise transport/runtime cause is not established; these results do not promise uninterrupted service. All nine P06 checks passed in the initial public run.
- `evidence/p06-public-http.json`: 49 checks over 50 anonymous requests passed, including the complete 27,554,963-byte download and 27 independent derived-value/missing-data fixtures.
- `evidence/p06-public-visual-review.json`: fifteen views across desktop Chromium, Windows WebKit, 390 px, 320 px and 768 px with 200% text. No page overflow or page errors. Screenshots were retained and representative desktop, mobile and large-text views were inspected.
- `evidence/p06-public-assets.json`: public JavaScript matches after generated asset-name normalization. CSS differs only by the previously identified unused `.table{display:table}` rule emitted locally from test files. Both raw hashes are retained.
- `evidence/p06-deterministic-exchange.json`: a fresh export is byte-identical. `pip check` reports no dependency conflicts.
- `evidence/p06-release.json`: Vercel release 0.6.0, deployment `dpl_GnUzron9LPS3jh3TCVftUSjDjUTt`. The first publish attempt reported Not authorized; read-only identity/project inspection succeeded and an unchanged retry published successfully. No credentials, permissions or account plan were changed.

P06.1-P06.5 are complete for this documented scope. Public persistent THREDDS hosting, Docker execution, physical-device/Firefox coverage and actual INCOIS installation remain open. R09, R10 and R12 remain unchecked; R02, R08, R11 and X07 now have their required bounded evidence. P07 has not started.

## Checkpoint B: official requirements

| Requirement | Supported result | Remaining boundary |
| --- | --- | --- |
| R01 | Tested volume, slices, isosurfaces, native depth and time views | Device/GPU breadth and final release audit |
| R02 | Temperature, salinity, current vectors and working derived scalar extension | New variables still require explicit definitions and registration |
| R03 | Checked depth/time controls and deliberate display transitions | No temporal interpolation or live stream claim |
| R04 | Genuine Argo, glider, CTD and BGC records, geographic markers | Only declared source collections; no global model coverage inferred |
| R05 | Source/QC profile charts and eligible model comparison | One Argo provenance hold, CTD temperature scale unresolved |
| R06 | Bounded NetCDF and documented delimited imports | Arbitrary NetCDF/Excel unsupported |
| R07 | Palette, limits, log/linear, opacity and vertical exaggeration | Masks and analytical values are preserved |
| R08 | Modern browser frontend, REST and tested DAP2 service path | Public Vercel REST; THREDDS public host not configured |
| R09 | Browser-only client, portable app and tested local service package | Container execution and institutional deployment remain unverified |
| R10 | Adapter/product contracts, second adapter and derived example | P15 expansion and externally supplied ML integration remain open |
| R11 | Scoped CF interpretation and actual independently checked WMS/WCS | Listed coordinate tolerance; no universal certification |
| R12 | Basic orientation and source explanations | Guided cases, outreach and user feedback remain P09/P16/P17 |

## Primary references

- [Unidata installation requirements](https://docs.unidata.ucar.edu/tds/current/userguide/install_java_tomcat.html): Java 17 and Tomcat 10.1 for the current TDS.
- [Unidata service configuration](https://docs.unidata.ucar.edu/tds/current/userguide/adding_ogc_iso_services.html) and [WCS reference](https://docs.unidata.ucar.edu/tds/current/userguide/wcs_ref.html): real service paths and WCS subset limits.
- [TDS release metadata](https://downloads.unidata.ucar.edu/tds/release_info.json) and [Tomcat downloads](https://tomcat.apache.org/download-10.cgi): actual runtime versions and checksums consulted for this implementation.
- [CF-1.10 conventions](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.10/cf-conventions.html) and [CF standard-name table](https://cfconventions.org/Data/cf-standard-names/76/build/cf-standard-name-table.html): coordinate, packing and practical-salinity interpretation.


Publication note: this is a dated method record. Historical evidence paths refer to the development archive unless present in this source release. See RELEASE.md for current package checks.
