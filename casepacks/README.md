# Checked historical case packs

These are real source-derived scientific assets, not synthetic demonstration values. `bay-bengal-2024-01/manifest.json` defines the supported historical case, file fingerprints and provenance.

Analytical arrays preserve decoded source values in little-endian float64. Display arrays use declared spatial decimation and float32 rounding. Both preserve missing cells. Original acquisition files stay under ignored `data/raw/`; `science.acquire_case` and `science.prepare_case` reproduce the pipeline.

Files are read-only deployment assets and can be included in the repository. Preserve the HYCOM and Argo citations and terms in each manifest. They are not app-user data, a live feed or official operational advisories.
