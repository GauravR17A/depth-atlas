# Standards service setup

The public app stays on Vercel. THREDDS is a separate persistent Java service. A browser user needs no Java, Python or local setup.

## Tested Windows setup

From the repository root, with the documented Python science environment installed:

```powershell
.venv/Scripts/python.exe deploy/run_standards.py --install
```

This downloads vendor-checksummed Java 17.0.20.1, Tomcat 10.1.60 and THREDDS 5.9 into ignored `.runtime/p06`. The pinned ZIPs are Windows x64; the launcher does not change machine-wide Java or PATH. An incomplete download fails its checksum rather than being executed. If that occurs, remove only that named archive and repeat the command.

The launcher checks the bundled exchange file, prepares a dedicated Tomcat base and runs in the terminal. Open `http://127.0.0.1:8096/thredds/catalog.html`. Stop with Ctrl+C. Do not start a second instance on the same port. To check a fresh runtime base after stopping the first:

```powershell
.venv/Scripts/python.exe deploy/run_standards.py --base .runtime/p06/fresh-server
.venv/Scripts/python.exe -m science.verify_p06_standards
```

The second command runs in another terminal while the server is ready. It needs the original acquired model files for independent reference values. To obtain those when absent, follow `docs/PHASE_02_DATA.md`. Normal service startup uses the bundled checked exchange file and needs no source-server connection.

## Requests

```text
http://127.0.0.1:8096/thredds/wms/ocean/bay-bengal-2024-01.nc?service=WMS&version=1.3.0&request=GetCapabilities
http://127.0.0.1:8096/thredds/wcs/ocean/bay-bengal-2024-01.nc?service=WCS&version=1.0.0&request=GetCapabilities
http://127.0.0.1:8096/thredds/wcs/ocean/bay-bengal-2024-01.nc?service=WCS&version=1.0.0&request=GetCoverage&coverage=temperature&format=NetCDF3&time=2024-01-07T12:00:00Z&vertical=100&bbox=86,12.5,87,13.5
http://127.0.0.1:8096/thredds/dodsC/ocean/bay-bengal-2024-01.nc.dods?temperature[1:1:1][19:1:19][10:1:12][10:1:12]
```

DAP endpoints are datasets; use a DAP client such as pydap or xarray to decode binary responses. The verifier uses OWSLib to construct WMS/WCS requests, reads NetCDF coverage files, and compares them with source values. WMS 1.3.0 uses longitude/latitude for CRS:84 and latitude/longitude for EPSG:4326. WCS 1.0.0 uses west/south/east/north in the tested native geographic grid. Depth selections are positive down in metres.

The native NetCDF and DAP coordinates are exact. THREDDS can regularize horizontal axes for WMS/WCS. The tested WCS longitude change is at most 0.0000826928 degree; the explicit test tolerance is 0.0001 degree. Numerical values and masks passed at 1e-12 absolute tolerance. No interpolation or universal reprojection support is claimed.

## Linux / institutional server

Use maintained Java 17 and Tomcat 10.1 releases. The same Python launcher accepts `--java /path/to/java --tomcat-home /path/to/tomcat --war /path/to/thredds.war --base /path/to/ocean-runtime`. Use the WAR checksum from the lock file. Do not use `--install` for Linux because its JRE archive is Windows-specific. That Linux path is documented but has not been executed here.

An optional Compose profile is also supplied:

```sh
docker compose -f deploy/compose.yaml --profile standards up --build
```

Docker is unavailable on the development machine. This recipe is not recorded as tested. The application Dockerfile now includes `adapters/`, required by supported instrument imports. The separate TDS image verifies its WAR, runs as a non-root user and mounts data read-only. Host ports bind only to loopback. Tomcat cache, generated files and logs are writable within its container; they are not user investigation storage.

## Resources and public deployment

The tested launcher uses 128 MB initial and 768 MB maximum Java heap, 12 connector threads and 1024-by-1024 maximum WMS images. DAP ASCII and binary limits are configured at 5 MB and 64 MB. WCS has no claimed equivalent response-size cap in this configuration. Its exposure is bounded by the single published case, but concurrent requests can still increase memory/CPU use. One post-test process sample used approximately 357 MB working set. This is a measurement from one local run, not a capacity guarantee.

The optional container has a 1.5 GB memory limit, two-CPU limit and 128-process limit. Reserve additional memory for the Python app, host and filesystem cache. Disk must hold the source artifact, approximately 100 MB WAR, Java/Tomcat files, expanded libraries, caches and rotated logs. Benchmark the actual institutional machine and expected concurrency before selecting production resources.

To expose TDS publicly, the institution must provide a persistent host, HTTPS reverse proxy, DNS, patching and resource/log management. Keep manager/admin applications disabled and remote-dataset fetching disabled. Configure the proxy's request/rate/time limits and re-run the protocol verifier through its public URL. This project has no verified INCOIS server access, no public TDS hostname and no authorization to buy an extra hosting service. Public Vercel REST and native downloads are independent of that deployment.

Configuration templates use `__OCEAN_DATA__`, substituted by the launcher or Docker build. It is not a THREDDS environment-variable placeholder. Original prototype attempts using `${tds.content.root.path}` in the catalogue failed to resolve as a dataset path; the explicit absolute directory fixed that startup error.
