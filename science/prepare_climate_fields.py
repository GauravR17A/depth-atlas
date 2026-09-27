"""Prepare immutable GODAS fields and Pacific cases without gap filling or interpolation."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np

from adapters.argo import parse_argo
from adapters.cf_model import json_value
from adapters.instruments import parse_instruments
from science.acquire_climate_fields import ROOT, RAW, EVENT_YEARS, MONTHS, YEARS
from science.contracts import CaseManifest, CaseSummary, Coordinates, ProfileSummary, Provenance, Variable
from science.instruments import InstrumentSummary

VERSION = 'p13-fields-v1'


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n',encoding='utf8')


def record(path, root):
    return {'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def binary(root, relative, array, **detail):
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(array.tobytes(order='C'),compresslevel=6,mtime=0))
    return record(path,root)|detail|{'shape':list(array.shape),'dtype':array.dtype.str}


def read_source(item):
    path=ROOT/item['path']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError('Source checksum changed. Review before preparing.')
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        a=np.array(ds['pottmp'][:],dtype=np.float64)
        attrs={k:json_value(ds['pottmp'].getncattr(k)) for k in ds['pottmp'].ncattrs()}
        if attrs.get('units')!='K' or attrs.get('var_desc')!='potential temperature' or attrs.get('statistic')!='Monthly Mean':
            raise ValueError('Source variable definition changed; do not relabel.')
        missing=~np.isfinite(a)
        for key in ('_FillValue','missing_value'):
            if key in attrs: missing|=a==float(np.float32(attrs[key]))
        low,high=attrs['valid_range'];missing|=(a<low)|(a>high)
        a=np.where(missing,np.nan,a-273.15)
        axes={k:np.asarray(ds[k][:],dtype=np.float64) for k in ('time','level','lat','lon')}
        metadata={'global':{k:json_value(ds.getncattr(k)) for k in ds.ncattrs()},
            'variables':{key:{'dtype':str(v.dtype),'dimensions':list(v.dimensions),
                 'attributes':{k:json_value(v.getncattr(k)) for k in v.ncattrs()}}
                 for key,v in ds.variables.items()}}
        units=ds['time'].units
        stamps=[x.strftime('%Y-%m-%dT%H:%M:%SZ') for x in netCDF4.num2date(axes['time'],units,calendar='standard')]
    if stamps!=item['timestamps'] or a.shape!=(3,28,30,240): raise ValueError('Source time or shape changed.')
    return a,axes,metadata


def prepare():
    journal=json.loads((RAW/'field-acquisition.json').read_text(encoding='utf8'))
    sources={r['year']:r for r in journal['files'] if r['archive_kind']=='source_float32_subset_reconstructed_as_netcdf'}
    if set(sources)!=set(YEARS): raise ValueError('All 31 declared source years are required.')
    fields={};metadata={};axes=None
    for year in YEARS:
        a,c,m=read_source(sources[year]);fields[year]=a;metadata[year]=m
        if axes is None: axes=c
        elif any(not np.array_equal(axes[k],c[k]) for k in ('level','lat','lon')):
            raise ValueError('Source native grid changed; no implicit remapping.')
    assert axes is not None
    sums=np.zeros_like(fields[1991],dtype=np.float64);counts=np.zeros_like(sums,dtype=np.uint16)
    # Fixed ascending-year accumulation, not a parallel reduction or NaN-skipping climatology.
    for year in range(1991,2021):
        a=fields[year];valid=np.isfinite(a)
        sums+=np.where(valid,a,0.0);counts+=valid.astype(np.uint16)
    baseline=np.where(counts==30,sums/30.0,np.nan)
    climate=ROOT/'casepacks/climate';climate.mkdir(parents=True,exist_ok=True)
    files=[]
    for t,month in enumerate(MONTHS):
        files.append(binary(climate,f'baseline/potential-temperature-{month:02d}.bin.gz',baseline[t].astype('<f8'),role='baseline',year=None,month=month))
        files.append(binary(climate,f'baseline/count-{month:02d}.bin.gz',counts[t].astype('<u2'),role='baseline_count',year=None,month=month))
        for year in EVENT_YEARS:
            files.append(binary(climate,f'events/{year}/potential-temperature-{month:02d}.bin.gz',fields[year][t].astype('<f8'),role='event',year=year,month=month))
    metadata_path=climate/'field-source-metadata.json'
    write_json(metadata_path,{'acquisition':journal,'source_year_metadata':metadata})
    files.append(record(metadata_path,climate)|{'role':'source_metadata'})
    variable=Variable(id='temperature',source_name='pottmp',label='Potential temperature',
       standard_name='sea_water_potential_temperature',units='°C',source_units='K',
       definition='GODAS monthly mean sea-water potential temperature; not in-situ or Conservative Temperature. Kelvin values are converted to degrees Celsius by subtracting 273.15 in float64.',
       packing={'source_dtype':'float32','scale_factor':1.0,'add_offset':0.0,'kelvin_offset':273.15,
                'missing_value':metadata[2013]['variables']['pottmp']['attributes']['missing_value'],
                'valid_range_kelvin':[260,310]})
    common_limits=[
       'Bounded historical assimilative ocean analysis, not a forecast or independent ocean measurement.',
       'Calendar-month means are stamped at the first day of the month; they are not instantaneous samples.',
       'The source variable is potential temperature. Direct residuals against in-situ Argo temperature are not scientifically comparable and are disabled.',
       'Only potential temperature is bundled. The original GODAS current grids are staggered; no invented salinity or velocity field is supplied.',
       'Depth coverage is the 28 native levels from 5 to 459 m. The surface 0 m and deeper ocean are not supplied.',
       'The 1991-2020 baseline is computed separately for September, October and November. All 30 years must be finite at a cell; otherwise that baseline cell is missing.',
       'Profiles may have been assimilated by GODAS; co-display is not independent validation.',
    ]
    def model_provenance(records):
        return Provenance(source_id='noaa-godas-psl-pottmp-son',title='NOAA NCEP GODAS monthly potential temperature',
          kind='model_analysis',provider='NOAA NCEP Environmental Modeling Center; NOAA Physical Sciences Laboratory distribution',
          dataset_version='Bias-corrected GODAS monthly archive, retrieved 2026-09-23; source-file SHA-256 fingerprints pinned',
          source_url='https://psl.noaa.gov/data/gridded/data.godas.html',
          licence_url='https://psl.noaa.gov/data/gridded/data.godas.html',licence='Publicly available NOAA data; acknowledge NOAA PSL and NCEP GODAS. Provided without warranty.',
          citation='NOAA NCEP Global Ocean Data Assimilation System (GODAS), monthly potential temperature. Data provided by NOAA PSL, Boulder, Colorado, USA.',
          retrieved_at=journal['retrieved_at'],files=records,
          transformations=['Select contiguous original SON time, depth, latitude and longitude indices with native spacing; no interpolation.',
             'Mask source missing and invalid-range values before conversion. Convert source float32 Kelvin to float64, then subtract 273.15.',
             'Retain increasing source longitudes in [0,360) across the dateline; do not reorder across the globe.',
             'Assign CF sea_water_potential_temperature based on the explicit NOAA var_desc and Kelvin units; the original COARDS source did not supply that CF standard_name.'],
          limitations=common_limits)
    manifest={'schema_version':'1','processing_version':VERSION,
      'baseline':{'start_year':1991,'end_year':2020,'months':MONTHS,'strict_count':30,
        'method':'Accumulate float64 Celsius values in ascending source-year order 1991 through 2020 for each calendar month and native cell. Divide by 30 only when all 30 source values are finite; otherwise retain missing.'},
      'coordinates':{'depth_m':axes['level'].tolist(),'latitude':axes['lat'].tolist(),'longitude':axes['lon'].tolist(),
         'longitude_convention':'[0,360)','calendar':'standard','source_time_units':sources[1991]['source_time_units']},
      'event_years':EVENT_YEARS,'months':MONTHS,'variable':variable.model_dump(),'files':files,
      'sources':[model_provenance([sources[y] for y in YEARS]).model_dump()],
      'source':model_provenance([sources[y] for y in YEARS]).model_dump(),
      'source_files':[sources[y] for y in YEARS],
      'temporal_support':{'kind':'calendar_month_mean','timestamp_policy':'First day of averaging period.','months':MONTHS},
      'limitations':common_limits,
      'counts':{'minimum':int(counts.min()),'maximum':int(counts.max()),'complete_cells':int((counts==30).sum()),'missing_baseline_cells':int((counts!=30).sum())}}
    write_json(climate/'field-manifest.json',manifest)

    reports=[]
    for year in EVENT_YEARS:
        case_id=f'pacific-godas-{year}-son';pack=ROOT/'casepacks'/case_id;pack.mkdir(parents=True,exist_ok=True)
        x=np.flatnonzero((axes['lon']>=140)&(axes['lon']<=280))
        longitude=axes['lon'][x];a=fields[year][:,:,:,x]
        stamps=sources[year]['timestamps']
        coordinates=Coordinates(times=stamps,depth_m=axes['level'].tolist(),latitude=axes['lat'].tolist(),longitude=longitude.tolist(),
           longitude_convention='[0,360)',calendar='standard',source_time_units=sources[year]['source_time_units'],
           source_depth_units='m',source_longitude_convention='0 to 360')
        yi=sorted(set(range(0,len(axes['lat']),2))|{len(axes['lat'])-1});xi=sorted(set(range(0,len(longitude),3))|{len(longitude)-1})
        display=coordinates.model_copy(update={'latitude':axes['lat'][yi].tolist(),'longitude':longitude[xi].tolist()})
        pack_files=[];error=0.0
        for t in range(3):
            visual=a[t][:,yi,:][:,:,xi].astype('<f4')
            original=a[t][:,yi,:][:,:,xi]
            valid=np.isfinite(original)
            error=max(error,float(np.max(np.abs(original[valid]-visual[valid].astype(float)))))
            pack_files.append(binary(pack,f'analytical/temperature-{t}.bin.gz',a[t].astype('<f8'),representation='analytical',variable='temperature',time_index=t))
            pack_files.append(binary(pack,f'display/temperature-{t}.bin.gz',visual,representation='display',variable='temperature',time_index=t))
        records=[r for r in journal['files'] if r['archive_kind']=='original_gdac_file' and r['event_year']==year]
        if len(records)!=3: raise ValueError('Each case needs its three preselected original profiles.')
        profiles=[];summaries=[];instrument_profiles=[];instrument_files=[]
        instrument_root=ROOT/'casepacks/instruments'/case_id;instrument_root.mkdir(parents=True,exist_ok=True)
        for item in sorted(records,key=lambda r:r['event_month']):
            path=ROOT/item['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Argo fingerprint changed.')
            for p in parse_argo(path,item['source_url']):
                p.source_id='argo-gdac-pacific'
                p.overlap={'spatial':bool(coordinates.latitude[0]<=p.latitude<=coordinates.latitude[-1] and longitude[0]<=p.longitude%360<=longitude[-1]),
                   'temporal':f'{year}-09-01T00:00:00Z'<=p.time<f'{year}-12-01T00:00:00Z',
                   'vertical':bool(p.depth_range_m and max(p.depth_range_m[0],5)<=min(p.depth_range_m[1],459)),
                   'eligible':False,
                   'meaning':'Co-displayed historical observation within the model calendar season. GODAS is monthly potential temperature; this instantaneous in-situ profile is not used for a direct model-observation residual.',
                   'source_month':item['event_month'],'model_temporal_support':'calendar_month_mean'}
                target=pack/'profiles'/(p.id+'.json');write_json(target,p.model_dump());pack_files.append(record(target,pack))
                profiles.append(p);summaries.append(ProfileSummary.model_validate({k:getattr(p,k) for k in ProfileSummary.model_fields}))
            imported=parse_instruments(path.read_bytes(),path.name,item['source_url'])
            for p in imported.profiles:
                p.collection=f'Tropical Pacific · {year} SON'
                p.metadata.update(provider='International Argo Program; Ifremer GDAC distribution',acquired_date=journal['retrieved_at'][:10],
                    source_url=item['source_url'],godas_context_only=True,monthly_model_interval=[f'{year}-{item["event_month"]:02d}-01T00:00:00Z',f'{year}-{item["event_month"]+1:02d}-01T00:00:00Z'])
                p.warnings.append('GODAS stores monthly potential temperature. This original instantaneous in-situ Argo profile is context, not a directly comparable residual or independent validation.')
                target=instrument_root/(p.id+'.json');write_json(target,p.model_dump())
                instrument_files.append({'name':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
                instrument_profiles.append(InstrumentSummary.model_validate(p.model_dump(include=set(InstrumentSummary.model_fields))).model_dump())
        if not any(p.eligible_samples for p in profiles):raise ValueError('Preselected original profiles have no eligible QC samples; retain and report source failure.')
        write_json(instrument_root/'index.json',{'schema_version':'2','profiles':instrument_profiles,'files':instrument_files,'sources':records,'examples':[],
              'limitations':['Three historical Argo profiles per season; not basin-wide coverage.','Raw/adjusted readings, QC and original coordinates remain inspectable.','Monthly potential temperature and instantaneous in-situ temperature are not directly collocated.']})
        argo_provenance=Provenance(source_id='argo-gdac-pacific',title='Original Pacific Argo profiles',kind='observation',
          provider='International Argo Program; source DAC identified in each original URL; Ifremer GDAC distribution',
          dataset_version='Original GDAC files retrieved 2026-09-23; SHA-256 and source update metadata retained',
          source_url='https://data-argo.ifremer.fr/',licence_url='https://argo.ucsd.edu/data/acknowledging-argo/',
          licence='Freely available without restriction; acknowledge Argo and contributing national programs.',
          citation='Argo (2000), Argo float data and metadata from Global Data Assembly Centre (Argo GDAC), SEANOE, https://doi.org/10.17882/42182',
          retrieved_at=journal['retrieved_at'],files=records,
          transformations=['Parse original core Argo files with existing QC contracts; no raw fallback in adjusted/delayed mode.',profiles[0].depth_method],
          limitations=['Profiles may have been assimilated into GODAS. Co-display is not independent validation.','Profile in-situ temperature differs from model potential temperature; direct residual disabled.'])
        meta_path=pack/'source-metadata.json';write_json(meta_path,{'model':metadata[year],'acquisition':sources[year],
              'profile_selection':journal['profile_selection'],'temporal_support':manifest['temporal_support']});pack_files.append(record(meta_path,pack))
        summary=CaseSummary(id=case_id,title=f'Tropical Pacific · September–November {year}',region_id='tropical-pacific',
           bounds=(float(longitude[0]),float(axes['lat'][0]),float(longitude[-1]),float(axes['lat'][-1])),
           time_start=stamps[0],time_end=stamps[-1],time_count=3,depth_range_m=(5,459),depth_count=28,profile_count=len(profiles),
           variables=['temperature'],source_label='NOAA GODAS monthly potential temperature + Argo')
        representations={'analytical':{'dtype':'little-endian float64','shape':[28,30,140],
              'method':'Native subset without interpolation. Mask before converting float32 Kelvin to float64 Celsius.'},
           'display':{'dtype':'little-endian float32','shape':[28,len(yi),len(xi)],
              'method':'Select every second latitude and every third longitude plus each last coordinate; retain all 28 depths. No gap filling.',
              'latitude_source_indices':yi,'longitude_source_indices':xi,'max_absolute_rounding_error':{'temperature':error},
              'variable_ranges':{'temperature':{'min':float(np.floor(np.nanmin(a))),'max':float(np.ceil(np.nanmax(a)))}}},
           'array_order':'depth, latitude, longitude in C order; longitude changes fastest.',
           'missing':'IEEE NaN in binary; JSON null in API. Missing does not mean zero.',
           'temporal_support':{'kind':'calendar_month_mean','intervals':[[f'{year}-{m:02d}-01T00:00:00Z',f'{year}-{m+1:02d}-01T00:00:00Z'] for m in MONTHS],
              'meaning':'Each interval is start-inclusive/end-exclusive. Timestamp is the first day, not an instantaneous analysis.'},
           'science_compatibility':{'temperature':'potential_temperature','direct_observation_residual':False}}
        samples=[]
        for t in range(3):
            for z,y,xx in [(0,15,0),(15,15,70),(27,15,139)]:
                samples.append({'time_index':t,'time':stamps[t],'depth_index':z,'latitude_index':y,'longitude_index':xx,
                    'depth_m':coordinates.depth_m[z],'latitude':coordinates.latitude[y],'longitude':coordinates.longitude[xx],
                    'values':{'temperature':json_value(a[t,z,y,xx])}})
        case=CaseManifest(case=summary,coordinates=coordinates,display_coordinates=display,variables=[variable],
           sources=[model_provenance([sources[year]]),argo_provenance],profiles=summaries,representations=representations,
           samples=samples,limitations=common_limits,files=pack_files,processing_version=VERSION)
        write_json(pack/'manifest.json',case.model_dump())
        reports.append({'case_id':case_id,'manifest_sha256':hashlib.sha256((pack/'manifest.json').read_bytes()).hexdigest(),
           'pack_bytes':sum(p.stat().st_size for p in pack.rglob('*') if p.is_file()),
           'profiles':[{'id':p.id,'time':p.time,'latitude':p.latitude,'longitude':p.longitude,'eligible_samples':p.eligible_samples} for p in profiles],
           'display_max_rounding_error_c':error})
    report={'method':VERSION,'source_years':YEARS,'native_shape':[3,28,30,240],
       'baseline_counts':manifest['counts'],'field_manifest':record(climate/'field-manifest.json',ROOT),
       'field_pack_bytes':sum(p.stat().st_size for p in climate.rglob('*') if p.is_file()),'cases':reports}
    write_json(ROOT/'docs/evidence/p13-field-preparation.json',report)
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':prepare()
