# Source adapters

`cf_model.py` supports bounded rectilinear NetCDF with declared in-situ temperature, practical salinity and eastward/northward currents. It preserves source metadata, masks and irregular coordinates, and rejects incompatible grids/units.

`argo.py` supports core Argo profiles with explicit mode-based raw/adjusted selection, retained QC/errors, original level indices and pressure-to-depth conversion through GSW. It does not substitute raw values for missing adjusted readings.

`instruments.py` implements the bounded P04 Argo, glider, CTD Exchange and documented CSV import paths, preserving per-source QC and provenance.

P06 adds `registry.py` with explicit versioned entry points and `cf_exchange.py`, a second model adapter. It maps the exchange file's latitude/longitude names and dimensionless practical-salinity metadata into the same native `ModelGrid`. Registered code is installed by maintainers; uploads cannot install plugins. See `docs/PHASE_06_STANDARDS.md` for the tested extension and limitations.

Derived scalar registrations live in `science/products.py`. Horizontal kinetic energy is the working example. A new quantity needs a scientific definition, units, native dependencies, mask behavior, numerical checks, public allowlist/schema and frontend presentation metadata. The 3D renderer consumes the existing shared grid. The external ML metadata interface is defined, but no ML product is installed.
