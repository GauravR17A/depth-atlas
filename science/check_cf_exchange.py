"""Scoped CF-1.10 exchange checks. This is not a universal CF certification tool."""
from pathlib import Path
import netCDF4
import numpy as np

AXES = {'time':('T','time','hours since 2024-01-07 00:00:00'), 'depth':('Z','depth','m'),
        'latitude':('Y','latitude','degrees_north'), 'longitude':('X','longitude','degrees_east')}
VARIABLES = {'temperature':('sea_water_temperature','degree_Celsius'), 'salinity':('sea_water_practical_salinity','1'),
             'eastward_velocity':('eastward_sea_water_velocity','m s-1'), 'northward_velocity':('northward_sea_water_velocity','m s-1'),
             'horizontal_kinetic_energy':(None,'m2 s-2')}


def check_exchange(path: Path):
    checks=[]
    def check(name,passed): checks.append(dict(check=name,passed=bool(passed)))
    with netCDF4.Dataset(path) as ds:
        check('CF-1.10 declaration',getattr(ds,'Conventions',None)=='CF-1.10')
        for name,(axis,standard,units) in AXES.items():
            if name not in ds.variables:
                check(name+' present',False);continue
            v=ds[name];v.set_auto_maskandscale(False);a=np.asarray(v[:])
            check(name+' independent numeric coordinate',v.dimensions==(name,) and a.dtype.kind in 'ifu' and a.size>0)
            check(name+' finite strictly increasing',np.isfinite(a).all() and (np.diff(a)>0).all())
            check(name+' axis / standard name / units',(getattr(v,'axis',None),getattr(v,'standard_name',None),getattr(v,'units',None))==(axis,standard,units))
            check(name+' no coordinate fill or packing',not any(k in v.ncattrs() for k in ['_FillValue','missing_value','scale_factor','add_offset']))
        if 'depth' in ds.variables: check('depth explicitly positive down',getattr(ds['depth'],'positive',None)=='down' and np.min(ds['depth'][:])>=0)
        if 'time' in ds.variables:
            t=ds['time'];check('supported calendar',getattr(t,'calendar',None)=='proleptic_gregorian')
            try:
                decoded=netCDF4.num2date(t[:],t.units,t.calendar)
                check('time decode/encode round trip',np.array_equal(t[:],netCDF4.date2num(decoded,t.units,t.calendar)))
            except (ValueError,AttributeError):check('time decode/encode round trip',False)
        for name,(standard,units) in VARIABLES.items():
            if name not in ds.variables:
                check(name+' present',False);continue
            v=ds[name]
            check(name+' dimensions',v.dimensions==tuple(AXES))
            check(name+' definition and units',getattr(v,'standard_name',None)==standard and getattr(v,'units',None)==units and bool(getattr(v,'long_name','')))
            check(name+' unpacked float64 with typed fill',v.dtype==np.dtype('float64') and isinstance(getattr(v,'_FillValue',None),np.float64) and not any(k in v.ncattrs() for k in ['scale_factor','add_offset']))
            a=v[:];check(name+' finite unmasked values',np.isfinite(a.compressed()).all())
        check('source identity',len(getattr(ds,'source_manifest_sha256',''))==64 and bool(getattr(ds,'source','')) and bool(getattr(ds,'history','')))
    return dict(scope='Project CF-1.10 exchange profile: explicit rectilinear geographic axes, positive-down metres, Gregorian time, declared units, unpacked float64 and missing-value semantics. Not all CF features or external certification.',passed=all(c['passed'] for c in checks),checks=checks)
