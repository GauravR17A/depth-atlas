"""Second compatible model adapter, using the same normalized grid and renderer."""
from pathlib import Path
import netCDF4
from adapters.cf_model import MODEL_VARIABLES, load_model
from science.contracts import UnsupportedData


def load_exchange(path: Path):
    with netCDF4.Dataset(path) as ds:
        if 'CF-1.10' not in getattr(ds, 'Conventions', '').split():
            raise UnsupportedData('unsupported_conventions', 'This adapter requires the declared CF-1.10 exchange contract.')
        for name, standard in [('time','time'),('depth','depth'),('latitude','latitude'),('longitude','longitude')]:
            if name not in ds.variables or getattr(ds[name], 'standard_name', None) != standard:
                raise UnsupportedData('unsupported_grid', 'Exchange axes require explicit standard names.')
    specs = dict(MODEL_VARIABLES)
    specs['salinity'] = ('salinity', 'sea_water_practical_salinity', {'1'}, 'psu', 'Practical salinity', 'Dimensionless PSS-78 practical salinity. The viewer retains its conventional psu label; values are unchanged.')
    grid = load_model(path, {key: key for key in specs}, axis_map={'time':'time','depth':'depth','latitude':'lat','longitude':'lon'}, variable_specs=specs)
    grid.transformations.append('cf-exchange/v1 maps latitude/longitude axis names and the explicit practical-salinity definition to the shared ModelGrid contract; no numeric unit scaling.')
    return grid
