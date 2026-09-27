"""Bounded Argo/BGC, IOOS row-NetCDF, CTD Exchange and documented CSV readers.

NetCDF reads are serialized because the underlying C library is not thread safe.
No URL fetching, filesystem writes, extrapolation or raw fallback occurs here.
"""
import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from threading import Lock

import gsw
import netCDF4
import numpy as np

from science.contracts import UnsupportedData
from science.instruments import ImportResult, InstrumentProfile, Measurement, Parameter, Reading

MAX_BYTES = 2_000_000
MAX_LEVELS = 5000
NETCDF_LOCK = Lock()
DEFINITIONS = {
    'temperature': ('Temperature', '°C', 'In-situ sea-water temperature'),
    'salinity': ('Practical salinity', 'psu', 'Practical salinity, PSS-78; not absolute salinity'),
    'oxygen': ('Dissolved oxygen', 'µmol/kg', 'Dissolved oxygen per mass of sea water'),
    'chlorophyll': ('Chlorophyll a', 'mg/m³', 'Chlorophyll-a concentration reported by the source'),
    'nitrate': ('Nitrate', 'µmol/kg', 'Nitrate per mass of sea water'),
}
ARGO_FIELDS = {'PRES':'pressure', 'TEMP':'temperature', 'PSAL':'salinity', 'DOXY':'oxygen', 'CHLA':'chlorophyll', 'NITRATE':'nitrate'}
UNITS = {'pressure':{'dbar','decibar','DBAR'}, 'temperature':{'degree_Celsius','degrees_Celsius','degrees_C','degC','DEG_C','°C'}, 'salinity':{'1','psu','PSS-78'}, 'oxygen':{'micromole/kg','umol kg-1','µmol/kg','UMOL/KG'}, 'chlorophyll':{'mg/m3','mg m-3','mg/m³'}, 'nitrate':{'micromole/kg','µmol/kg'}}


def fail(code, message):
    raise UnsupportedData(code, message)


def text(a):
    if np.ndim(a)==0 and np.ma.is_masked(a): return ''
    a = np.ma.filled(a, b' ' if getattr(a, 'dtype', np.dtype('S1')).kind == 'S' else '')
    if np.ndim(a):
        return ''.join(text(x) for x in a).strip()
    v = np.asarray(a).item()
    return (v.decode('utf8', errors='replace') if isinstance(v, bytes) else str(v)).strip().strip('\x00')


def number(x):
    if np.ma.is_masked(x): return None
    v = float(x)
    return v if math.isfinite(v) else None


def stamp(s):
    try:
        d = datetime.fromisoformat(str(s).replace('Z','+00:00'))
        if d.tzinfo is None: fail('invalid_time','Timestamps must include Z or a UTC offset.')
        return d.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    except (ValueError, TypeError): fail('invalid_time','A valid ISO 8601 timestamp with timezone is required.')


def nc_time(v, x):
    if number(x) is None: fail('invalid_time','A source timestamp is missing.')
    calendar = getattr(v,'calendar','standard')
    if calendar not in {'standard','gregorian','proleptic_gregorian'}: fail('unsupported_calendar',f'Unsupported calendar: {calendar}.')
    try:
        d = netCDF4.num2date(float(x),v.units,calendar=calendar)
        # Round source fractional seconds, preserving the raw number in metadata where relevant.
        epoch=netCDF4.date2num(d,'seconds since 1970-01-01',calendar=calendar)
        return datetime.fromtimestamp(round(float(epoch)),timezone.utc).isoformat().replace('+00:00','Z')
    except (ValueError,AttributeError,OverflowError): fail('invalid_time','Time units could not be decoded.')


def position(lat,lon):
    lat,lon=number(lat),number(lon)
    if lat is None or lon is None or not -90<=lat<=90 or not -180<=lon<=180: fail('invalid_position','Latitude/longitude must be finite WGS84 decimal degrees in [-90,90] and [-180,180].')
    return lat,lon


def depth(p,lat):
    return max(0.0,float(-gsw.z_from_p(p,lat))) if p is not None and 0<=p<=12000 else None


def reading(value,qc,scheme,coordinate_ok,mode='reported',bgc=False,**raw):
    good={'argo':{'1','2'},'qartod':{'1'},'woce':{'2'},'declared':{'1','2'}}[scheme]
    reason='Accepted by the displayed QC policy.'
    if value is None: reason='Missing source value.'
    elif not coordinate_ok: reason='Pressure, position or time is not eligible.'
    elif qc not in good: reason=f'{scheme.upper()} flag {qc or "missing"} is excluded.'
    elif bgc and mode=='R': reason='Unadjusted BGC value; inspect only.'
    else: return Reading(value=value,qc=qc,accepted=True,reason=reason,**raw)
    return Reading(value=value,qc=qc,accepted=False,reason=reason,**raw)


def parameter(key,field,mode,scheme):
    label,units,definition=DEFINITIONS[key]
    return Parameter(label=label,units=units,definition=definition,source_field=field,mode=mode,qc_scheme=scheme)


def profile(*,body,filename,source_url,identifier,instrument,platform,title,levels,parameters,metadata=None,warnings=None):
    if not levels: fail('empty_profile','The file contains no profile samples.')
    digest=hashlib.sha256(body).hexdigest()
    for k,p in parameters.items(): p.accepted_count=sum(l.readings[k].accepted for l in levels)
    depths=[l.depth_m for l in levels if l.depth_m is not None]
    # A display track preserves source order. The complete per-sample positions remain in levels.
    track=[]
    for l in levels:
        xy=(l.longitude,l.latitude)
        if not track or xy!=track[-1]: track.append(xy)
    return InstrumentProfile(id=f'{instrument}-{identifier}-{digest[:10]}',instrument=instrument,platform=platform,title=title,time=min(l.time for l in levels),time_end=max(l.time for l in levels),latitude=levels[0].latitude,longitude=levels[0].longitude,samples=len(levels),depth_range_m=(min(depths),max(depths)) if depths else None,parameters=parameters,source_url=source_url,source_file=filename,source_sha256=digest,track=track,depth_method=f'-gsw.z_from_p(sea pressure in dbar, sample latitude), GSW {gsw.__version__}; dynamic height and surface geopotential default to zero. Source order is retained.',qc_policy='Per-variable QC: Argo 1/2; QARTOD 1 only; WOCE 2 only; documented CSV 1/2. Depth requires eligible pressure and position/time. Raw BGC R mode is inspect-only. Missing adjusted values never fall back to raw.',warnings=warnings or [],metadata=metadata or {},levels=levels)


def check_units(v,key):
    if getattr(v,'units','') not in UNITS[key]: fail('incompatible_units',f'{v.name}: unsupported {key} units {getattr(v,"units","missing")}.')


def nc_values(v, allow_invalid_range=False):
    # Bound allocation before asking the netCDF library to decode any variable.
    if v.size>500_000 or v.dtype.kind not in 'fiSu': fail('unsupported_variable',f'Unsupported or oversized NetCDF variable {v.name}.')
    for low,high in [('valid_min','valid_max')]:
        if hasattr(v,low) and hasattr(v,high) and getattr(v,low)>getattr(v,high):
            if not allow_invalid_range: fail('invalid_metadata',f'{v.name}: valid_min exceeds valid_max.')
            # Preserve inspectable source values, but the caller must exclude them.
            v.set_auto_mask(False)
            a=np.asarray(v[:],dtype=float)
            for key in ['_FillValue','missing_value']:
                if hasattr(v,key): a[a==getattr(v,key)]=np.nan
            a[~np.isfinite(a)]=np.nan
            return np.ma.masked_invalid(a)
    return v[:]


def argo(ds,body,filename,source_url):
    required={'N_PROF','N_LEVELS'}
    if not required.issubset(ds.dimensions): fail('unsupported_format','Argo N_PROF and N_LEVELS dimensions are required.')
    count=len(ds.dimensions['N_PROF']);n=len(ds.dimensions['N_LEVELS'])
    if not 0<count<=24 or count*n>MAX_LEVELS: fail('file_limits','Argo input is limited to 24 profiles and 5,000 total levels.')
    base=['POSITION_QC','JULD_QC','LATITUDE','LONGITUDE','JULD','PLATFORM_NUMBER','CYCLE_NUMBER','PRES','PRES_QC']
    if any(k not in ds.variables for k in base): fail('missing_variable','Argo pressure, coordinates, time, platform, mode and QC fields are required.')
    for name,v in ds.variables.items():
        if any(name==f+s for f in ARGO_FIELDS for s in ('','_QC','_ADJUSTED','_ADJUSTED_QC','_ADJUSTED_ERROR')) and v.dimensions!=('N_PROF','N_LEVELS'):
            fail('invalid_dimensions',f'{name}: expected N_PROF by N_LEVELS.')
    if sum(v.size for v in ds.variables.values())>1_000_000: fail('file_limits','The NetCDF variables exceed the decoded element budget.')
    arrays={k:nc_values(v) for k,v in ds.variables.items() if k in base or k in {'DATA_MODE','STATION_PARAMETERS','PARAMETER_DATA_MODE'} or any(k==f+s for f in ARGO_FIELDS for s in ('','_QC','_ADJUSTED','_ADJUSTED_QC','_ADJUSTED_ERROR'))}
    bgc=any(k in arrays for k in ('DOXY','CHLA','NITRATE'))
    if bgc and not {'STATION_PARAMETERS','PARAMETER_DATA_MODE'}.issubset(arrays): fail('missing_data_mode','BGC requires STATION_PARAMETERS and PARAMETER_DATA_MODE.')
    result=[]
    for i in range(count):
        lat,lon=position(arrays['LATITUDE'][i],arrays['LONGITUDE'][i]);time=nc_time(ds['JULD'],arrays['JULD'][i])
        modes={text(p):text(m) for p,m in zip(arrays['STATION_PARAMETERS'][i],arrays['PARAMETER_DATA_MODE'][i])} if 'PARAMETER_DATA_MODE' in arrays else {}
        chosen={};params={};flags={};values={};m={}
        for f,key in ARGO_FIELDS.items():
            if f not in arrays: continue
            mode=modes.get(f,text(arrays['DATA_MODE'][i]) if 'DATA_MODE' in arrays else '') if not bgc else modes.get(f,'')
            if mode not in {'R','A','D'}: fail('unsupported_data_mode',f'{f}: R, A or D parameter mode is required.')
            choice=f if mode=='R' else f+'_ADJUSTED'
            if any(k not in arrays for k in [choice,choice+'_QC',f+'_QC']): fail('missing_variable',f'Missing Argo value/QC field {choice}; no raw fallback is allowed.')
            check_units(ds[choice],key);check_units(ds[f],key)
            standard=getattr(ds[choice],'standard_name','')
            expected={'pressure':{'sea_water_pressure'},'temperature':{'sea_water_temperature'},'salinity':{'sea_water_salinity','sea_water_practical_salinity'},'oxygen':{'moles_of_oxygen_per_unit_mass_in_sea_water'},'chlorophyll':{'mass_concentration_of_chlorophyll_a_in_sea_water'},'nitrate':{'moles_of_nitrate_per_unit_mass_in_sea_water'}}
            if key in expected and standard not in expected[key]: fail('incompatible_variable',f'{choice}: incompatible or missing standard_name.')
            if arrays[choice][i].shape!=(n,): fail('invalid_dimensions',f'{choice}: expected one value per source level.')
            chosen[f]=choice;m[f]=mode;values[f]=arrays[choice][i];flags[f]=[text(v) for v in arrays[choice+'_QC'][i]]
            if key!='pressure': params[key]=parameter(key,choice,mode,'argo')
        if not params: fail('missing_variable','No supported measured variable accompanies pressure.')
        levels=[];position_qc=text(arrays['POSITION_QC'][i]);time_qc=text(arrays['JULD_QC'][i])
        for j in range(n):
            p=number(values['PRES'][j]);z=depth(p,lat);ok=z is not None and flags['PRES'][j] in {'1','2'} and position_qc in {'1','2'} and time_qc in {'1','2'}
            readings={}
            for f,key in ARGO_FIELDS.items():
                if key not in params: continue
                def value(s): return number(arrays[f+s][i,j]) if f+s in arrays else None
                def flag(s): return text(arrays[f+s][i,j]) if f+s in arrays else ''
                readings[key]=reading(number(values[f][j]),flags[f][j],'argo',ok,m[f],key in {'oxygen','nitrate','chlorophyll'},raw=value(''),raw_qc=flag('_QC'),adjusted=value('_ADJUSTED'),adjusted_qc=flag('_ADJUSTED_QC'),adjusted_error=value('_ADJUSTED_ERROR'))
            levels.append(Measurement(index=j,depth_m=z,pressure_dbar=p,latitude=lat,longitude=lon,time=time,coordinate_status=f'Pressure QC {flags["PRES"][j]}; position QC {position_qc}; time QC {time_qc}',coordinate_qc={'pressure':flags['PRES'][j],'position':position_qc,'time':time_qc,'scheme':'argo'},coordinate_eligible=ok,readings=readings))
        platform=text(arrays['PLATFORM_NUMBER'][i]);cycle=int(arrays['CYCLE_NUMBER'][i])
        metadata={'parameter_modes':m,'pressure_field':chosen['PRES'],'position_qc':position_qc,'time_qc':time_qc,'source_juld':number(arrays['JULD'][i]),'source_juld_units':ds['JULD'].units,'source_profile_index':i,'attributes':{f:{a:str(ds[f].getncattr(a)) for a in ds[f].ncattrs()} for f in chosen.values()}}
        metadata['unsupported_parameters']=[text(p) for p in arrays['STATION_PARAMETERS'][i] if text(p) and text(p) not in ARGO_FIELDS] if 'STATION_PARAMETERS' in arrays else []
        # Preserve word spacing and each calibration/parameter entry. The compact
        # identifier helper intentionally strips spaces from character tokens.
        metadata['scientific_calibration']={key:[str(v).rstrip('\x00 ') for v in netCDF4.chartostring(np.ma.filled(nc_values(ds[key])[i],b' ')).ravel()] for key in ('SCIENTIFIC_CALIB_COMMENT','SCIENTIFIC_CALIB_EQUATION','SCIENTIFIC_CALIB_COEFFICIENT') if key in ds.variables and ds[key].dimensions[0]=='N_PROF'}
        warnings=['Historical observations; selecting a profile does not establish a model match.']
        if 'verification run' in ' '.join(metadata['scientific_calibration'].get('SCIENTIFIC_CALIB_COMMENT',[])).lower():
            warnings.append('Source calibration text mentions a verification run. Quantitative comparison is held pending source clarification; original source QC flags are unchanged.')
        if bgc: warnings.append('BGC S-files align sensor sampling levels at the source. BGC variables can have different data modes; this is not a simulated profile.')
        result.append(profile(body=body,filename=filename,source_url=source_url,identifier=f'{platform}-{cycle}-{i}',instrument='bgc' if bgc else 'argo',platform=platform,title=f'{"BGC Argo" if bgc else "Argo"} {platform} · cycle {cycle}',levels=levels,parameters=params,metadata=metadata,warnings=warnings))
    return result


def glider(ds,body,filename,source_url):
    names=['profile_id','trajectory','precise_time','precise_lat','precise_lon','pressure','temperature','salinity','pressure_qartod_summary_flag','temperature_qartod_summary_flag','salinity_qartod_summary_flag']
    if any(n not in ds.variables for n in names): fail('missing_variable','IOOS row-NetCDF requires per-sample precise_time/lat/lon, pressure, temperature, salinity and QARTOD summary flags.')
    n=ds['profile_id'].size
    if n>MAX_LEVELS or ds['profile_id'].dimensions!=('row',): fail('file_limits','IOOS input requires a bounded one-dimensional row layout, at most 5,000 samples.')
    if any(ds[k].dimensions!=('row',) for k in names if k!='trajectory') or ds['trajectory'].size>MAX_LEVELS*128: fail('invalid_dimensions','IOOS measurements must have exactly one value per row and bounded trajectory names.')
    for key in ['pressure','temperature','salinity']: check_units(ds[key],key)
    standards={'pressure':'sea_water_pressure','temperature':'sea_water_temperature','salinity':'sea_water_practical_salinity'}
    for key,standard in standards.items():
        if getattr(ds[key],'standard_name','')!=standard: fail('incompatible_variable',f'{key}: expected {standard}.')
    for key,units in [('precise_lat',{'degree_north','degrees_north'}),('precise_lon',{'degree_east','degrees_east'})]:
        if getattr(ds[key],'units','') not in units: fail('incompatible_units',f'{key}: decimal geographic degrees are required.')
    invalid={k for k in ['temperature','salinity','pressure'] if hasattr(ds[k],'valid_min') and hasattr(ds[k],'valid_max') and ds[k].valid_min>ds[k].valid_max}
    data={k:nc_values(ds[k],allow_invalid_range=k in invalid) for k in names};groups={}
    for j,pid in enumerate(data['profile_id']):
        if number(pid) is None: fail('missing_profile_id','Each glider sample needs a profile ID.')
        groups.setdefault(int(pid),[]).append(j)
    if len(groups)>24: fail('file_limits','At most 24 glider profiles can be imported together.')
    result=[]
    for pid,indices in groups.items():
        levels=[];platform=text(data['trajectory'][indices[0]])
        for j in indices:
            lat,lon=position(data['precise_lat'][j],data['precise_lon'][j]);t=nc_time(ds['precise_time'],data['precise_time'][j]);p=number(data['pressure'][j]);z=depth(p,lat)
            pqc=str(int(data['pressure_qartod_summary_flag'][j])) if number(data['pressure_qartod_summary_flag'][j]) is not None else ''
            readings={key:reading(number(data[key][j]),str(int(data[key+'_qartod_summary_flag'][j])) if number(data[key+'_qartod_summary_flag'][j]) is not None else '', 'qartod',z is not None and pqc=='1',raw=number(data[key][j])) for key in ['temperature','salinity']}
            for key,value in readings.items():
                if key in invalid or 'pressure' in invalid: value.accepted=False;value.reason='Source valid_min exceeds valid_max. Values retained for inspection only; metadata needs correction by the provider.'
            levels.append(Measurement(index=j,depth_m=z,pressure_dbar=p,latitude=lat,longitude=lon,time=t,coordinate_status=f'Per-sample source coordinates; pressure QARTOD {pqc}. Separate position/time QC flags are not supplied in this subset.',coordinate_qc={'pressure':pqc,'position':'','time':'','scheme':'qartod'},coordinate_eligible=z is not None and pqc=='1' and 'pressure' not in invalid,readings=readings))
        params={k:parameter(k,k,'source processed','qartod') for k in ['temperature','salinity']}
        warnings=['Per-sample positions and times are retained. Underwater locations can be estimated by the provider; the track does not prove a directly measured GPS fix at every depth.','QARTOD 2 means not evaluated and is excluded; it is not Argo probably-good flag 2.']
        if invalid: warnings.append(f'Source range metadata is reversed for {", ".join(sorted(invalid))}. Those values are inspect-only, regardless of the provider QC flag. No range is guessed or repaired.')
        result.append(profile(body=body,filename=filename,source_url=source_url,identifier=f'{platform}-{pid}',instrument='glider',platform=platform,title=f'Glider {platform} · profile {pid}',levels=levels,parameters=params,metadata={'profile_id':pid,'position_method':getattr(ds['precise_lat'],'comment','Source per-sample position; underwater locations may be interpolated between GPS fixes.'),'source_variables':names,'source_time_units':ds['precise_time'].units,'range_metadata':{k:{a:float(getattr(ds[k],a)) for a in ['valid_min','valid_max'] if hasattr(ds[k],a)} for k in ['pressure','temperature','salinity']}},warnings=warnings))
    return result


def exchange(body,filename,source_url):
    lines=body.decode('utf-8-sig').splitlines();meta={};start=None
    for i,line in enumerate(lines):
        if line.startswith('CTDPRS,'): start=i;break
        if '=' in line and not line.startswith('#'):
            k,v=line.split('=',1);meta[k.strip()]=v.strip()
    if start is None or any(k not in meta for k in ['EXPOCODE','STNNBR','CASTNO','DATE','TIME','LATITUDE','LONGITUDE']): fail('missing_metadata','CTD Exchange needs cruise, station/cast, date/time and latitude/longitude headers.')
    fields=next(csv.reader([lines[start]]));units=next(csv.reader([lines[start+1]]));unitmap=dict(zip(fields,units));mapping={'CTDPRS':'pressure','CTDTMP':'temperature','CTDSAL':'salinity','CTDOXY':'oxygen'}
    selected={f:k for f,k in mapping.items() if f in fields}
    for f,k in selected.items():
        if unitmap[f].strip() not in UNITS[k] or f+'_FLAG_W' not in fields: fail('incompatible_units',f'{f} requires supported units and a WOCE flag column.')
    if 'CTDPRS' not in selected or len(selected)<2: fail('missing_variable','CTD pressure plus a supported measurement is required.')
    lat,lon=position(meta['LATITUDE'],meta['LONGITUDE'])
    try:time=datetime.strptime(meta['DATE']+meta['TIME'].zfill(4),'%Y%m%d%H%M').replace(tzinfo=timezone.utc).isoformat().replace('+00:00','Z')
    except ValueError: fail('invalid_time','CTD Exchange DATE/TIME are invalid.')
    params={k:parameter(k,f,'source processed','woce') for f,k in selected.items() if k!='pressure'};levels=[]
    data=[]
    for line in lines[start+2:]:
        if line.strip()=='END_DATA': break
        if line.strip(): data.append(line)
    if not any(line.strip()=='END_DATA' for line in lines[start+2:]): fail('incomplete_file','CTD Exchange END_DATA marker is missing.')
    if len(data)>MAX_LEVELS: fail('file_limits','At most 5,000 samples per file.')
    for j,row in enumerate(csv.DictReader(data,fieldnames=fields)):
        def val(f):
            x=float(row[f]);return None if x==-999 or not math.isfinite(x) else x
        p=val('CTDPRS');z=depth(p,lat);qc=row['CTDPRS_FLAG_W'].strip();ok=z is not None and qc=='2'
        readings={k:reading(val(f),row[f+'_FLAG_W'].strip(),'woce',ok,raw=val(f)) for f,k in selected.items() if k!='pressure'}
        levels.append(Measurement(index=j,depth_m=z,pressure_dbar=p,latitude=lat,longitude=lon,time=time,coordinate_status=f'Station position and time; pressure WOCE {qc}. Separate position/time QC flags are not supplied.',coordinate_qc={'pressure':qc,'position':'','time':'','scheme':'woce'},coordinate_eligible=ok,readings=readings))
    return [profile(body=body,filename=filename,source_url=source_url,identifier=f'{meta["EXPOCODE"]}-{meta["STNNBR"]}-{meta["CASTNO"]}',instrument='ctd',platform=meta['EXPOCODE'],title=f'Ship CTD {meta["EXPOCODE"]} · station {meta["STNNBR"]}',levels=levels,parameters=params,metadata=meta,warnings=['Position and timestamp identify the station/cast, not individual sample fixes. Temperature scale must be confirmed from the cruise report before quantitative model comparisons.'])]


def table(body,filename,source_url):
    rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))
    required={'profile_id','instrument','platform','time','latitude','longitude','pressure_dbar','pressure_qc','position_qc','time_qc'}
    if not rows or not required.issubset(rows[0]): fail('missing_metadata','Use the documented Depth Atlas CSV columns: profile_id, instrument, platform, time, latitude, longitude, pressure_dbar, pressure_qc, position_qc, time_qc and a supported value/QC column.')
    if len(rows)>MAX_LEVELS: fail('file_limits','At most 5,000 samples per CSV.')
    columns={'temperature_c':'temperature','salinity_psu':'salinity','oxygen_umol_kg':'oxygen','chlorophyll_mg_m3':'chlorophyll','nitrate_umol_kg':'nitrate'}
    selected={f:k for f,k in columns.items() if f in rows[0]}
    if not selected or any(k+'_qc' not in rows[0] for k in selected.values()): fail('missing_variable','Supported measurements each need their documented QC column.')
    grouped={}
    for j,row in enumerate(rows):
        if None in row or any(v is None for v in row.values()): fail('invalid_csv','Every CSV row must have the same number of columns.')
        if not row['profile_id'] or len(row['profile_id'])>80: fail('invalid_profile','Profile IDs must contain 1 to 80 characters.')
        grouped.setdefault(row['profile_id'],[]).append((j,row))
    if len(grouped)>24: fail('file_limits','At most 24 CSV profiles per file.')
    result=[]
    for pid,group in grouped.items():
        first=group[0][1];levels=[]
        if first['instrument'] not in {'argo','bgc','glider','ctd'}: fail('unsupported_instrument','CSV instrument must be argo, bgc, glider or ctd.')
        for j,row in group:
            if any(row[k]!=first[k] for k in ['platform','instrument']): fail('inconsistent_metadata','A profile cannot change instrument or platform between samples.')
            lat,lon=position(row['latitude'],row['longitude']);t=stamp(row['time']);p=number(row['pressure_dbar']) if row['pressure_dbar'].strip() else None;z=depth(p,lat)
            ok=z is not None and all(row[k] in {'1','2'} for k in ['pressure_qc','position_qc','time_qc'])
            readings={}
            for f,k in selected.items():
                v=number(row[f]) if row[f].strip() else None
                readings[k]=reading(v,row[k+'_qc'],'declared',ok,raw=v)
            levels.append(Measurement(index=j,depth_m=z,pressure_dbar=p,latitude=lat,longitude=lon,time=t,coordinate_status=f'Declared CSV pressure/position/time flags: {row["pressure_qc"]}/{row["position_qc"]}/{row["time_qc"]}',coordinate_qc={'pressure':row['pressure_qc'],'position':row['position_qc'],'time':row['time_qc'],'scheme':'declared'},coordinate_eligible=ok,readings=readings))
        result.append(profile(body=body,filename=filename,source_url=source_url,identifier=pid,instrument=first['instrument'],platform=first['platform'],title=f'Imported {first["instrument"].upper()} {first["platform"]} · {pid}',levels=levels,parameters={k:parameter(k,f,'user supplied','declared') for f,k in selected.items()},warnings=['CSV quality flags and processing are declared by the uploader, not independently verified. Accepted flags mean accepted by this file schema only. Use native Argo NetCDF to preserve raw/adjusted history.']))
    return result


def parse_instruments(body:bytes,filename:str,source_url:str='') -> ImportResult:
    if not body or len(body)>MAX_BYTES: fail('file_limits','Choose a non-empty file no larger than 2 MB.')
    # Filenames are display metadata only, never filesystem paths.
    filename=filename.replace('\\','/').split('/')[-1][:120]
    try:
        if filename.lower().endswith('.nc'):
            if not (body.startswith(b'CDF') or body.startswith(b'\x89HDF')): fail('unsupported_format','This file is not supported NetCDF.')
            with NETCDF_LOCK, netCDF4.Dataset('in-memory.nc',memory=body) as ds:
                if ds.groups or len(ds.variables)>160 or len(ds.dimensions)>32: fail('file_limits','Nested groups or excessive NetCDF fields are unsupported.')
                if 'N_PROF' in ds.dimensions: fmt='Argo NetCDF';profiles=argo(ds,body,filename,source_url)
                elif 'row' in ds.dimensions: fmt='IOOS row NetCDF';profiles=glider(ds,body,filename,source_url)
                else: fail('unsupported_format','Supported NetCDF layouts are Argo profiles and documented IOOS glider row subsets. Grids, arbitrary CF layouts and other sensor schemas need an adapter.')
        elif filename.lower().endswith(('.csv','.txt')):
            if body.decode('utf-8-sig').startswith('CTD,'): fmt='CTD Exchange';profiles=exchange(body,filename,source_url)
            else: fmt='Depth Atlas CSV v1';profiles=table(body,filename,source_url)
        else: fail('unsupported_format','Choose supported .nc, .csv or .txt input. Archives and arbitrary spreadsheets are not supported.')
        result=ImportResult(format=fmt,profiles=profiles)
        if len(result.model_dump_json().encode())>3_500_000: fail('file_limits','The decoded profiles exceed the 3.5 MB response limit. Import a smaller source subset.')
        return result
    except UnsupportedData: raise
    except (ValueError,TypeError,KeyError,IndexError,OSError,UnicodeError,OverflowError,AttributeError) as exc:
        fail('invalid_file',f'The file does not match a supported observation schema ({type(exc).__name__}). Check its metadata, columns, dimensions and units.')
